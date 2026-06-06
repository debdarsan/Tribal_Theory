"""Quiz module — Phase 5 of the agentic knowledge pipeline.

Tests users on generated/validated knowledge. Each question is presented as
MULTIPLE CHOICE: the cached canonical answer is the correct option and the
LLM generates plausible distractors (generate_mcq_options); the user picks one
and it is graded by exact match. Attempts are logged in `quiz_attempts` so
per-user stats and high-miss-rate questions can later feed back into the
gap-detection loop. (grade_answer remains for the legacy free-text path.)"""
from __future__ import annotations

import json
import random
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def init_quiz_db(db_path: str | Path) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quiz_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL,
                kb_doc_id TEXT,
                question_text TEXT NOT NULL,
                canonical_answer TEXT,
                user_answer TEXT,
                is_correct INTEGER,
                llm_feedback TEXT,
                attempted_at TEXT NOT NULL
            )
            """
        )


def _split_validated_content(page_content: str) -> tuple[str, str]:
    """Split a BIDA_validated page_content of form 'Question: ...\\nAnswer: ...'
    into (question, answer). Falls back to ('', page_content) if no split."""
    if "Answer:" not in page_content:
        return "", page_content.strip()
    q_part, a_part = page_content.split("Answer:", 1)
    q_part = re.sub(r"^Question:\s*", "", q_part, flags=re.IGNORECASE).strip()
    return q_part, a_part.strip()


def list_validated_quiz_items(validated_vdb: Any) -> list[dict]:
    """Pull every doc from BIDA_validated as {id, question, canonical_answer,
    metadata}. Useful when you also want HITL-approved content in the quiz."""
    if validated_vdb is None:
        return []
    try:
        raw = validated_vdb._collection.get(include=["documents", "metadatas"])
    except Exception:
        return []
    ids = raw.get("ids") or []
    docs = raw.get("documents") or []
    metas = raw.get("metadatas") or []
    items = []
    for _id, doc, meta in zip(ids, docs, metas):
        q, a = _split_validated_content(doc or "")
        if not q or not a:
            continue
        items.append({
            "id": _id,
            "question": q,
            "canonical_answer": a,
            "metadata": dict(meta or {}),
        })
    return items


def list_synth_quiz_items(db_path: str | Path) -> list[dict]:
    """Pull synthetic_questions rows that have a cached answer. These are
    questions generated from the document vectorstore (BIDA_texts) via the
    Auto Q&A / Gap Finder flows. Each row's `answer_text` is the canonical
    answer for grading."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT id, text, answer_text, topic, purpose, question_type
                FROM synthetic_questions
                WHERE answer_text IS NOT NULL AND answer_text != ''
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    items = []
    for r in rows:
        items.append({
            "id": f"synth_{r['id']}",
            "question": r["text"],
            "canonical_answer": r["answer_text"],
            "metadata": {
                "topic": r["topic"],
                "purpose": r["purpose"],
                "question_type": r["question_type"],
                "source": "synthetic_questions",
            },
        })
    return items


def list_quiz_items(
    db_path: str | Path,
    validated_vdb: Any = None,
    include_validated: bool = False,
) -> list[dict]:
    """Default quiz pool: pre-generated synthetic_questions (drawn from the
    document vectorstore). Optionally augment with HITL-validated entries
    when include_validated=True."""
    items = list_synth_quiz_items(db_path)
    if include_validated and validated_vdb is not None:
        items.extend(list_validated_quiz_items(validated_vdb))
    return items


def pick_next_question(
    items: list[dict],
    exclude_ids: Optional[set] = None,
) -> Optional[dict]:
    """Pick a random validated question not in exclude_ids. Returns None if
    no items are eligible."""
    exclude_ids = exclude_ids or set()
    pool = [it for it in items if it["id"] not in exclude_ids]
    if not pool:
        return None
    return random.choice(pool)


def grade_answer(
    *,
    client: Any,
    model: str,
    question: str,
    canonical_answer: str,
    user_answer: str,
) -> dict:
    """LLM-grade a user answer against the canonical answer. Returns:
        {is_correct: bool, feedback: str}
    Tolerant of paraphrasing — focuses on whether key facts are present."""
    from core.llm_client import call_llm
    if not (user_answer or "").strip():
        return {"is_correct": False, "feedback": "No answer provided."}

    system = (
        "You grade short user answers against a canonical answer about BillTrak. "
        "Output ONLY a JSON object with two keys: "
        '{"is_correct": true|false, "feedback": "<one short sentence>"}. '
        "The user answer is correct if it captures the key fact(s) of the canonical "
        "answer, even if paraphrased. Partial answers that miss key facts are wrong. "
        "Wrong-but-related answers are wrong. Off-topic is wrong."
    )
    user = (
        f"Question: {question}\n\n"
        f"Canonical answer: {canonical_answer}\n\n"
        f"User answer: {user_answer}\n\n"
        f"Grade the user answer. JSON only."
    )
    try:
        text = call_llm(
            client,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            model,
            max_tokens=200,
            temperature=0.0,
        )
    except Exception as e:
        return {"is_correct": False, "feedback": f"Could not grade: {e}"}

    return _parse_grade(text)


_JSON_OBJ_RE = re.compile(r"\{.*?\}", re.DOTALL)


def _parse_grade(text: str) -> dict:
    """Tolerant parser for the grade JSON — falls back to a refusal."""
    text = (text or "").strip()
    candidates = [text]
    m = _JSON_OBJ_RE.search(text)
    if m and m.group(0) != text:
        candidates.append(m.group(0))
    for c in candidates:
        try:
            data = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "is_correct" in data:
            return {
                "is_correct": bool(data.get("is_correct")),
                "feedback": str(data.get("feedback") or "").strip(),
            }
    return {"is_correct": False, "feedback": "Could not interpret grading response."}


def _parse_distractors(text: str) -> list:
    """Extract a list of distractor strings from an LLM response."""
    text = (text or "").strip()
    candidates = [text]
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m and m.group(0) != text:
        candidates.append(m.group(0))
    for c in candidates:
        try:
            data = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("distractors"), list):
            return [str(x).strip() for x in data["distractors"] if str(x).strip()]
        if isinstance(data, list):
            return [str(x).strip() for x in data if str(x).strip()]
    return []


def _parse_mcq(text: str) -> dict:
    """Parse {"correct": "...", "distractors": [...]} from an LLM response.
    Returns {"correct": str, "distractors": [str, ...]} (either may be empty)."""
    text = (text or "").strip()
    candidates = [text]
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m and m.group(0) != text:
        candidates.append(m.group(0))
    for c in candidates:
        try:
            data = json.loads(c)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            correct = str(data.get("correct") or "").strip()
            distractors = [
                str(x).strip() for x in (data.get("distractors") or []) if str(x).strip()
            ]
            return {"correct": correct, "distractors": distractors}
    return {"correct": "", "distractors": []}


def _shorten_answer(s: str, max_words: int = 14) -> str:
    """Shorten a long answer to a brief option: first sentence, capped to
    max_words. Used as a fallback when the LLM doesn't supply a short option."""
    text = " ".join((s or "").split())
    if not text:
        return text
    for sep in (". ", "? ", "! "):
        idx = text.find(sep)
        if 0 < idx < len(text) - 1:
            text = text[: idx + 1]
            break
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words]) + "…"
    return text


def generate_mcq_options(
    *,
    client: Any,
    model: str,
    question: str,
    correct_answer: str,
    n_distractors: int = 3,
) -> dict:
    """Build SHORT multiple-choice options for a question. The canonical answer
    is often a full paragraph, so we ask the LLM for a short version of the
    correct answer plus short, plausible-but-wrong distractors, then shuffle.
    Returns:
        {"options": [<n+1 short strings, shuffled>], "correct_index": int}
    Grading stays correct because the caller compares the chosen index to
    correct_index (the full canonical answer is shown separately on a miss).
    Falls back to a shortened canonical answer + generic distractors if the
    LLM call fails."""
    from core.llm_client import call_llm
    correct_full = (correct_answer or "").strip()
    system = (
        "You write options for a multiple-choice quiz about BillTrak. Given a "
        "question and its full correct answer, produce (1) a SHORT version of the "
        "correct answer and (2) short, plausible-but-WRONG distractors that are "
        "topically related but factually incorrect. EVERY option must be a brief "
        "phrase or single short clause (at most ~12 words) — never a full "
        "paragraph. Keep all options similar in length and style, mutually "
        "distinct, and make the distractors NOT paraphrases of the correct answer. "
        'Output ONLY JSON: {"correct": "<short>", "distractors": ["<short>", ...]}.'
    )
    user = (
        f"Question: {question}\n"
        f"Full correct answer: {correct_full}\n"
        f"Give a short correct option and exactly {n_distractors} short incorrect "
        f"options. JSON only."
    )
    correct_short = ""
    distractors = []
    try:
        text = call_llm(
            client,
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            model,
            max_tokens=400,
            temperature=0.7,
        )
        parsed = _parse_mcq(text)
        correct_short = parsed["correct"]
        distractors = parsed["distractors"]
    except Exception:
        correct_short = ""
        distractors = []

    # Displayed correct option: the LLM's short version, else a shortened form of
    # the canonical answer (so we never show a full paragraph as an option).
    correct = correct_short or _shorten_answer(correct_full)

    seen = {correct.lower()}
    clean = []
    for d in distractors:
        if d and d.lower() not in seen:
            clean.append(d)
            seen.add(d.lower())
    _fillers = ["None of the above", "Not applicable", "Information not available",
                "This is not described in the manuals"]
    fi = 0
    while len(clean) < n_distractors and fi < len(_fillers):
        f = _fillers[fi]; fi += 1
        if f.lower() not in seen:
            clean.append(f); seen.add(f.lower())

    options = clean[:n_distractors] + [correct]
    random.shuffle(options)
    return {"options": options, "correct_index": options.index(correct)}


def record_attempt(
    db_path: str | Path,
    *,
    user_name: str,
    kb_doc_id: Optional[str],
    question_text: str,
    canonical_answer: Optional[str],
    user_answer: Optional[str],
    is_correct: bool,
    llm_feedback: Optional[str],
) -> int:
    init_quiz_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.execute(
            """
            INSERT INTO quiz_attempts
                (user_name, kb_doc_id, question_text, canonical_answer,
                 user_answer, is_correct, llm_feedback, attempted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_name,
                kb_doc_id,
                question_text,
                canonical_answer,
                user_answer,
                int(bool(is_correct)),
                llm_feedback,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        return cur.lastrowid


def get_user_stats(db_path: str | Path, user_name: str) -> dict:
    """Return {total, correct, accuracy} for a user. accuracy is 0..1 or None."""
    init_quiz_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) AS correct
            FROM quiz_attempts WHERE user_name = ?
            """,
            (user_name,),
        ).fetchone()
    total = row[0] or 0
    correct = row[1] or 0
    accuracy = (correct / total) if total else None
    return {"total": total, "correct": correct, "accuracy": accuracy}


def list_recent_attempts(
    db_path: str | Path, user_name: str, limit: int = 20,
) -> list[dict]:
    init_quiz_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM quiz_attempts WHERE user_name = ? ORDER BY id DESC LIMIT ?",
            (user_name, limit),
        ).fetchall()
        return [dict(r) for r in rows]
