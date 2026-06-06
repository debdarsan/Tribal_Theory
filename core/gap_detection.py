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
            "assigned_to",
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
    assigned_to: Optional[str] = None,
) -> bool:
    """Store a user-supplied answer against an existing gap row. `assigned_to`
    is the User ID of the superuser the submitter assigned to review it; the
    HITL queue routes the item to that reviewer only. Returns True if a row
    was updated, False if gap_id doesn't exist."""
    init_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.execute(
            "UPDATE gaps SET user_input = ?, user_input_at = ?, user_input_by = ?, assigned_to = ? WHERE id = ?",
            (
                text,
                datetime.now().isoformat(timespec='seconds'),
                user_name,
                assigned_to,
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


def list_pending_reviews(
    db_path: str | Path,
    limit: int = 50,
    assigned_to: Optional[str] = None,
) -> list[dict]:
    """Return gaps awaiting reviewer decision (user contributed, not yet
    decided). When `assigned_to` is given, restrict to items the submitter
    assigned to that reviewer (matched on the assignee's User ID)."""
    init_db(db_path)
    where = [
        "user_input IS NOT NULL",
        "user_input != ''",
        "(reviewer_decision IS NULL OR reviewer_decision = '')",
    ]
    params: list = []
    if assigned_to is not None:
        where.append("assigned_to = ?")
        params.append(assigned_to)
    params.append(limit)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT * FROM gaps
            WHERE {' AND '.join(where)}
            ORDER BY id DESC
            LIMIT ?
            """,
            tuple(params),
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


# ---------------------------------------------------------------------------
# Validated-KB management (list / edit / delete already-injected knowledge)
# ---------------------------------------------------------------------------

def _split_qa(content: str) -> tuple[str, str]:
    """Split a stored validated doc ('Question: ...\\nAnswer: ...') into
    (question, answer). Falls back to ('', content) if not in that shape."""
    if content.startswith("Question:") and "Answer:" in content:
        q_part, a_part = content.split("Answer:", 1)
        question = q_part[len("Question:"):].strip()
        return question, a_part.strip()
    return "", content.strip()


def list_validated_entries(vstore: Any, search: Optional[str] = None) -> list[dict]:
    """Return every entry in the validated Chroma collection as dicts with
    keys: id, question, answer, content, metadata. `search` (case-insensitive
    substring) filters across question + answer. Newest-committed first when
    the gap_id metadata allows ordering, else by id."""
    raw = vstore.get(include=["documents", "metadatas"])
    ids = raw.get("ids") or []
    docs = raw.get("documents") or []
    metas = raw.get("metadatas") or []

    entries: list[dict] = []
    for doc_id, content, meta in zip(ids, docs, metas):
        meta = meta or {}
        question, answer = _split_qa(content or "")
        if not question:
            question = str(meta.get("question") or "")
        entries.append({
            "id": doc_id,
            "question": question,
            "answer": answer,
            "content": content or "",
            "metadata": meta,
        })

    if search:
        needle = search.lower().strip()
        entries = [
            e for e in entries
            if needle in e["question"].lower() or needle in e["answer"].lower()
        ]

    # Newest first: gap_id is a monotonic int; fall back to doc id string.
    def _sort_key(e: dict):
        gid = e["metadata"].get("gap_id")
        try:
            return (1, int(gid))
        except (TypeError, ValueError):
            return (0, 0)

    entries.sort(key=_sort_key, reverse=True)
    return entries


def update_validated_entry(
    vstore: Any,
    *,
    doc_id: str,
    new_answer: str,
    new_question: Optional[str] = None,
    db_path: str | Path | None = None,
) -> str:
    """Re-embed and overwrite an existing validated entry's text. Preserves the
    original metadata (updating `question` if changed). When `db_path` and the
    entry's `gap_id` metadata are available, mirrors the new answer into the
    gaps row's `reviewer_edited_text` for audit consistency. Returns doc_id."""
    if not new_answer.strip():
        raise ValueError("new_answer is empty")

    existing = vstore.get(ids=[doc_id], include=["documents", "metadatas"])
    metas = existing.get("metadatas") or []
    docs = existing.get("documents") or []
    if not docs:
        raise ValueError(f"validated entry {doc_id!r} not found")
    meta = dict(metas[0] or {})
    old_question, _ = _split_qa(docs[0] or "")
    question = (new_question if new_question is not None else None) \
        or old_question or str(meta.get("question") or "")

    meta["question"] = question[:500]
    content = f"Question: {question}\nAnswer: {new_answer.strip()}"

    try:
        vstore.delete(ids=[doc_id])
    except Exception:
        pass
    vstore.add_texts([content], metadatas=[meta], ids=[doc_id])

    gap_id = meta.get("gap_id")
    if db_path is not None and gap_id is not None:
        try:
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute(
                    "UPDATE gaps SET reviewer_edited_text = ? WHERE id = ?",
                    (new_answer.strip(), int(gap_id)),
                )
        except Exception:
            pass
    return doc_id


def delete_validated_entry(
    vstore: Any,
    *,
    doc_id: str,
    db_path: str | Path | None = None,
) -> bool:
    """Remove an entry from the validated Chroma collection. When `db_path` is
    given, also clears the originating gaps row's KB-commit markers
    (`committed_to_kb_at`, `kb_doc_id`) so it no longer counts as injected.
    Returns True if the Chroma delete was issued."""
    try:
        vstore.delete(ids=[doc_id])
    except Exception:
        return False
    if db_path is not None:
        try:
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute(
                    "UPDATE gaps SET committed_to_kb_at = NULL, kb_doc_id = NULL "
                    "WHERE kb_doc_id = ?",
                    (doc_id,),
                )
        except Exception:
            pass
    return True
