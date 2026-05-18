from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


METADATA_MARKER = "[[META]]"

_CONFIDENCE_RE = re.compile(r"CONFIDENCE\s*:\s*([01](?:\.\d+)?)", re.IGNORECASE)
_MISSING_RE = re.compile(
    r"MISSING_INFO\s*:\s*(.+?)\s*\Z", re.IGNORECASE | re.DOTALL
)


@dataclass
class GapMetadata:
    confidence: Optional[float] = None
    missing_info: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        return self.confidence is None and self.missing_info is None


def parse_metadata_trailer(text: str) -> tuple[str, GapMetadata]:
    """Find the LAST [[META]] block in `text`, strip it, return (clean_text, metadata).
    If no marker is present, return (text, GapMetadata())."""
    marker_idx = text.rfind(METADATA_MARKER)
    if marker_idx == -1:
        return text, GapMetadata()

    cleaned = text[:marker_idx].rstrip()
    trailer = text[marker_idx + len(METADATA_MARKER):]

    confidence: Optional[float] = None
    conf_match = _CONFIDENCE_RE.search(trailer)
    if conf_match:
        try:
            confidence = max(0.0, min(1.0, float(conf_match.group(1))))
        except ValueError:
            confidence = None

    missing_info: Optional[str] = None
    missing_match = _MISSING_RE.search(trailer)
    if missing_match:
        missing_raw = missing_match.group(1).strip()
        # Strip out a CONFIDENCE line if it appears AFTER MISSING_INFO (rare LLM ordering)
        missing_raw = _CONFIDENCE_RE.sub("", missing_raw).strip()
        if missing_raw and missing_raw.upper() != "NONE":
            missing_info = missing_raw

    return cleaned, GapMetadata(confidence=confidence, missing_info=missing_info)


def is_gap(
    metadata: GapMetadata,
    num_text_docs: int,
    num_image_docs: int = 0,
    confidence_threshold: float = 0.5,
) -> bool:
    """Decide whether this Q&A represents a knowledge gap worth flagging."""
    if num_text_docs == 0 and num_image_docs == 0:
        return True
    if metadata.confidence is not None and metadata.confidence < confidence_threshold:
        return True
    if metadata.missing_info:
        return True
    return False


def init_db(db_path: str | Path) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gaps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_name TEXT,
                model TEXT,
                question TEXT NOT NULL,
                answer TEXT,
                confidence REAL,
                missing_info TEXT,
                num_text_docs INTEGER,
                num_image_docs INTEGER,
                is_gap INTEGER NOT NULL,
                user_input TEXT,
                user_input_at TEXT,
                user_input_by TEXT
            )
            """
        )
        # Migration for DBs created before user_input + reviewer columns existed.
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(gaps)")}
        for col in (
            "user_input", "user_input_at", "user_input_by",
            "reviewer_decision", "reviewer_name", "reviewed_at",
            "reviewer_edited_text", "reviewer_comment",
            "committed_to_kb_at", "kb_doc_id",
        ):
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE gaps ADD COLUMN {col} TEXT")


def record_gap(
    db_path: str | Path,
    *,
    question: str,
    answer: str,
    metadata: GapMetadata,
    num_text_docs: int,
    num_image_docs: int = 0,
    user_name: Optional[str] = None,
    model: Optional[str] = None,
    confidence_threshold: float = 0.5,
) -> int:
    """Insert one row into the gaps table. Returns the new row id."""
    init_db(db_path)
    gap_flag = is_gap(metadata, num_text_docs, num_image_docs, confidence_threshold)
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.execute(
            """
            INSERT INTO gaps (
                timestamp, user_name, model, question, answer,
                confidence, missing_info, num_text_docs, num_image_docs, is_gap
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec='seconds'),
                user_name,
                model,
                question,
                answer,
                metadata.confidence,
                metadata.missing_info,
                num_text_docs,
                num_image_docs,
                int(gap_flag),
            ),
        )
        return cursor.lastrowid


def record_user_input(
    db_path: str | Path,
    gap_id: int,
    text: str,
    user_name: Optional[str] = None,
) -> bool:
    """Store a user-supplied answer against an existing gap row. Returns True
    if a row was updated, False if gap_id doesn't exist."""
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.execute(
            "UPDATE gaps SET user_input = ?, user_input_at = ?, user_input_by = ? WHERE id = ?",
            (
                text,
                datetime.now().isoformat(timespec='seconds'),
                user_name,
                gap_id,
            ),
        )
        return cursor.rowcount > 0


def get_gap(db_path: str | Path, gap_id: int) -> Optional[dict]:
    """Return a single gap row as a dict, or None if not found."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM gaps WHERE id = ?", (gap_id,)).fetchone()
        return dict(row) if row else None


def list_pending_reviews(db_path: str | Path, limit: int = 50) -> list[dict]:
    """Return gaps awaiting reviewer decision (user contributed, not yet decided)."""
    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM gaps
            WHERE user_input IS NOT NULL
              AND user_input != ''
              AND (reviewer_decision IS NULL OR reviewer_decision = '')
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


_VALID_DECISIONS = {"approved", "rejected"}


VALIDATED_COLLECTION_NAME = "BIDA_validated"


def commit_approved_to_validated(
    *,
    chroma_dir: str | Path,
    embeddings: Any,
    db_path: str | Path,
    gap_id: int,
    collection_name: str = VALIDATED_COLLECTION_NAME,
    chroma_client: Any = None,
    chroma_client_settings: Any = None,
) -> str:
    """Embed and write an approved gap's (question, final_answer) pair to the
    expert-validated Chroma collection. Marks the gaps row with
    committed_to_kb_at + kb_doc_id. Idempotent: re-committing the same gap
    overwrites the existing doc.

    Pass `chroma_client` (and optionally `chroma_client_settings`) when the
    caller is the live Streamlit app — chromadb errors if the same path is
    opened with two different client configs. Standalone scripts can omit
    both and chroma_dir alone is used to create a fresh client.

    Returns the Chroma doc id added."""
    from langchain_chroma import Chroma

    init_db(db_path)
    row = get_gap(db_path, gap_id)
    if not row:
        raise ValueError(f"gap_id {gap_id} not found")
    if row.get("reviewer_decision") != "approved":
        raise ValueError(f"gap_id {gap_id} is not approved (decision={row.get('reviewer_decision')!r})")

    final_answer = row.get("reviewer_edited_text") or row.get("user_input") or ""
    if not final_answer.strip():
        raise ValueError(f"gap_id {gap_id} has no answer text to commit")

    question = row["question"]
    content = f"Question: {question}\nAnswer: {final_answer}"
    doc_id = f"hitl_{gap_id}"
    meta = {
        "source": "hitl_validated",
        "gap_id": gap_id,
        "question": question[:500],
        "original_contributor": row.get("user_input_by") or "",
        "reviewer": row.get("reviewer_name") or "",
        "reviewed_at": row.get("reviewed_at") or "",
    }

    chroma_kwargs: dict = {
        "collection_name": collection_name,
        "embedding_function": embeddings,
    }
    if chroma_client is not None:
        chroma_kwargs["client"] = chroma_client
        if chroma_client_settings is not None:
            chroma_kwargs["client_settings"] = chroma_client_settings
    else:
        chroma_kwargs["persist_directory"] = str(chroma_dir)
    vstore = Chroma(**chroma_kwargs)
    # Delete first so the upsert behavior is deterministic regardless of langchain_chroma version
    try:
        vstore.delete(ids=[doc_id])
    except Exception:
        pass
    vstore.add_texts([content], metadatas=[meta], ids=[doc_id])

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE gaps SET committed_to_kb_at = ?, kb_doc_id = ? WHERE id = ?",
            (datetime.now().isoformat(timespec='seconds'), doc_id, gap_id),
        )

    return doc_id


def record_review_decision(
    db_path: str | Path,
    gap_id: int,
    decision: str,
    reviewer_name: Optional[str] = None,
    edited_text: Optional[str] = None,
    comment: Optional[str] = None,
) -> bool:
    """Mark a gap reviewed. decision must be 'approved' or 'rejected'.
    If edited_text is provided, it overrides the user_input as the final
    approved text but the original user_input is preserved untouched.
    Returns True if a row was updated."""
    if decision not in _VALID_DECISIONS:
        raise ValueError(f"decision must be one of {_VALID_DECISIONS}, got {decision!r}")
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.execute(
            """
            UPDATE gaps
            SET reviewer_decision = ?,
                reviewer_name = ?,
                reviewed_at = ?,
                reviewer_edited_text = ?,
                reviewer_comment = ?
            WHERE id = ?
            """,
            (
                decision,
                reviewer_name,
                datetime.now().isoformat(timespec='seconds'),
                edited_text,
                comment,
                gap_id,
            ),
        )
        return cursor.rowcount > 0
