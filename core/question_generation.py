"""Synthetic question generation — Phase 2 of the agentic knowledge pipeline.

Cluster the existing document chunks, pull representative excerpts from
each cluster, ask the LLM to produce factoid / conceptual / edge-case
questions about each cluster, and persist them in a SQLite table for
downstream gap probing (Phase 2.5)."""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


QUESTION_TYPES = ("factoid", "conceptual", "edge_case")


@dataclass
class GenerationSummary:
    n_chunks: int
    n_clusters: int
    n_questions: int
    per_cluster: list[dict]
    errors: list[str]


def init_questions_db(db_path: str | Path) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS synthetic_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cluster_id INTEGER NOT NULL,
                question_type TEXT NOT NULL,
                text TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                source_chunk_ids TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                answer_text TEXT,
                answer_confidence REAL,
                answer_missing_info TEXT,
                answered_at TEXT
            )
            """
        )
        # Migration for tables created before answer / gap_id columns existed.
        existing = {r[1] for r in conn.execute("PRAGMA table_info(synthetic_questions)")}
        for col, typ in (
            ("answer_text", "TEXT"),
            ("answer_confidence", "REAL"),
            ("answer_missing_info", "TEXT"),
            ("answered_at", "TEXT"),
            ("gap_id", "INTEGER"),
            ("topic", "TEXT"),
            ("answer_num_text_docs", "INTEGER"),
            ("answer_num_image_docs", "INTEGER"),
            ("purpose", "TEXT"),
            ("answer_source_docs_json", "TEXT"),
        ):
            if col not in existing:
                conn.execute(f"ALTER TABLE synthetic_questions ADD COLUMN {col} {typ}")


def extract_chunks(vdb: Any) -> dict:
    """Pull all chunks + embeddings + metadata from a langchain_chroma vdb."""
    coll = vdb._collection
    raw = coll.get(include=["embeddings", "documents", "metadatas"])
    return {
        "ids": raw.get("ids", []),
        "embeddings": raw.get("embeddings", []),
        "documents": raw.get("documents", []),
        "metadatas": raw.get("metadatas", []),
    }


def choose_n_clusters(n_chunks: int, target_ratio: int = 5, min_k: int = 2, max_k: int = 12) -> int:
    """Pick KMeans k roughly as n_chunks/target_ratio, clamped to
    [min_k, max_k] and never exceeding n_chunks itself."""
    if n_chunks <= 1:
        return 1
    k = max(min_k, n_chunks // target_ratio)
    return min(k, max_k, n_chunks)


def cluster_embeddings(embeddings: list, n_clusters: int) -> tuple:
    """KMeans → (labels, centroids). Trivial single-cluster fallback for
    n_clusters <= 1 or n_samples <= 1."""
    import numpy as np
    arr = np.array(embeddings)
    if n_clusters <= 1 or len(arr) <= 1:
        return [0] * len(arr), arr.mean(axis=0, keepdims=True) if len(arr) else arr
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=n_clusters, n_init=10, random_state=42)
    labels = km.fit_predict(arr)
    return list(labels), km.cluster_centers_


def select_representative_chunks(
    cluster_embeddings: list,
    centroid: Any,
    top_k: int = 3,
) -> list[int]:
    """Return indices (into the cluster's slice) of the top_k chunks closest
    to the cluster centroid (cosine similarity)."""
    import numpy as np
    arr = np.array(cluster_embeddings)
    centroid = np.array(centroid)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    denom = np.linalg.norm(arr, axis=1) * np.linalg.norm(centroid)
    sims = arr @ centroid / np.where(denom == 0, 1, denom)
    order = np.argsort(sims)[::-1][:top_k]
    return order.tolist()


def _build_question_messages(excerpts: str, per_type: int) -> list[dict]:
    system = (
        "You generate evaluation questions about a corporate knowledge base. "
        "Output ONLY a JSON array, no prose, no markdown fences. "
        'Each item: {"type": one of (factoid, conceptual, edge_case), "text": <question>}.'
    )
    user = (
        f"Source excerpts:\n---\n{excerpts}\n---\n\n"
        f"Generate exactly {per_type} factoid questions (what/when/who/how-many), "
        f"{per_type} conceptual questions (why/how/explain), and "
        f"{per_type} edge-case questions (boundaries, contradictions, what-if) "
        f"about these excerpts. Total = {3 * per_type} questions. "
        f"Output a single JSON array of objects."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def parse_question_response(text: str) -> list[dict]:
    """Parse LLM output as a list of {'type': ..., 'text': ...} dicts.
    Tolerates surrounding prose or markdown fences."""
    text = (text or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_ARRAY_RE.search(text)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    if not isinstance(data, list):
        return []
    cleaned: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        t = (item.get("type") or "").strip().lower().replace(" ", "_").replace("-", "_")
        if t not in QUESTION_TYPES:
            t = "factoid"
        q_text = (item.get("text") or "").strip()
        if not q_text:
            continue
        cleaned.append({"type": t, "text": q_text})
    return cleaned


def generate_questions_for_cluster(
    *,
    client: Any,
    model: str,
    excerpts: str,
    per_type: int = 3,
    max_tokens: int = 1500,
    temperature: float = 0.7,
) -> list[dict]:
    """Single LLM call → parsed question list for one cluster's excerpts."""
    from core.llm_client import call_llm
    messages = _build_question_messages(excerpts, per_type)
    text = call_llm(
        client, messages, model,
        max_tokens=max_tokens, temperature=temperature,
    )
    return parse_question_response(text)


def save_questions(
    db_path: str | Path,
    cluster_id: int,
    items: list[dict],
    source_chunk_ids: list[str],
    topic: Optional[str] = None,
) -> int:
    if not items:
        return 0
    init_questions_db(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    src = json.dumps(source_chunk_ids)
    with sqlite3.connect(str(db_path)) as conn:
        conn.executemany(
            "INSERT INTO synthetic_questions (cluster_id, question_type, text, generated_at, source_chunk_ids, status, topic) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            [(cluster_id, it["type"], it["text"], now, src, topic) for it in items],
        )
    return len(items)


PURPOSE_DEMO = "demo"
PURPOSE_GAP_FINDER = "gap_finder"


def save_one_question(
    db_path: str | Path,
    cluster_id: int,
    item: dict,
    source_chunk_ids: list[str],
    topic: Optional[str] = None,
    purpose: str = PURPOSE_DEMO,
) -> int:
    """Single-question insert that returns the new row id."""
    init_questions_db(db_path)
    now = datetime.now().isoformat(timespec="seconds")
    src = json.dumps(source_chunk_ids)
    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.execute(
            "INSERT INTO synthetic_questions (cluster_id, question_type, text, generated_at, source_chunk_ids, status, topic, purpose) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (cluster_id, item["type"], item["text"], now, src, topic, purpose),
        )
        return cur.lastrowid


def _build_one_question_messages(topic: str, excerpts: str, purpose: str = PURPOSE_DEMO) -> list[dict]:
    """Prompt for a SINGLE question. Two modes:

    - `demo`: question is answerable FROM the excerpts; highlights known
      content. Bias toward factoid/conceptual that a new user might ask.
    - `gap_finder`: question PROBES the limits of the excerpts; bias toward
      edge_case / what-if / contradictions / details not specified."""
    system = (
        "You generate evaluation questions about a corporate knowledge base. "
        "Output ONLY a JSON array containing exactly one object. No prose, no markdown fences. "
        'Schema: [{"type": one of (factoid, conceptual, edge_case), "text": <question>}].'
    )
    topic_line = f"Topic: {topic}\n\n" if topic.strip() else ""
    topic_phrase = f"about the topic '{topic}'" if topic.strip() else "about the content in the excerpts"

    if purpose == PURPOSE_GAP_FINDER:
        user = (
            f"{topic_line}"
            f"Source excerpts:\n---\n{excerpts}\n---\n\n"
            f"Generate exactly ONE evaluation question {topic_phrase} that is designed to "
            f"PROBE THE LIMITS of these excerpts. Focus on what is NOT clearly specified, "
            f"edge cases, boundary conditions, contradictions, missing details, or what-if "
            f"scenarios that the source doesn't fully cover. Prefer 'edge_case' type. "
            f"The goal is to surface where the documents fall short — not to ask about "
            f"things already well-explained. Output a single-element JSON array."
        )
    else:
        user = (
            f"{topic_line}"
            f"Source excerpts:\n---\n{excerpts}\n---\n\n"
            f"Generate exactly ONE thoughtful evaluation question {topic_phrase} that is "
            f"clearly ANSWERABLE FROM the excerpts above. Highlight an interesting key "
            f"fact or concept a new user might naturally ask. Prefer 'factoid' or "
            f"'conceptual' type. Do NOT ask about details not present in the excerpts. "
            f"Output a single-element JSON array."
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def answer_with_source(
    *,
    client: Any,
    model: str,
    question_text: str,
    source_text: str,
    system_prompt_template: str,
    content_summary: str = "",
    additional_information: str = "",
    **llm_kwargs: Any,
) -> dict:
    """Answer a question using a specific source_text — bypasses retrieval.
    Used by Auto Q&A so the answer is guaranteed to use the same chunk the
    question was generated from."""
    from core.gap_detection import parse_metadata_trailer
    from core.llm_client import call_llm
    from core.rag import compose_messages

    messages = compose_messages(
        question=question_text,
        system_prompt_template=system_prompt_template,
        source_text=source_text,
        additional_information=additional_information,
        content_summary=content_summary,
    )
    raw = call_llm(client, messages, model, stream=False, **llm_kwargs)
    cleaned, meta = parse_metadata_trailer(raw)
    return {
        "answer": cleaned,
        "confidence": meta.confidence,
        "missing_info": meta.missing_info,
        "num_text_docs": 1,
        "num_image_docs": 0,
        # Caller already has the source — we don't re-emit it here. The UI
        # passes its own source_docs to save_question_answer for persistence.
        "source_docs": [],
    }


def generate_one_question_for_topic(
    *,
    client: Any,
    model: str,
    vdb: Any,
    db_path: str | Path,
    topic: str = "",
    top_k_chunks: int = 5,
    relevance_threshold: float = 0.3,
    excerpt_chars: int = 1500,
    max_tokens: int = 500,
    temperature: float = 0.9,
    purpose: str = PURPOSE_DEMO,
) -> dict:
    """Auto-Q&A entry point: generate ONE question grounded in the corpus.

    If `topic` is provided, validates scope via similarity search and pulls
    the most relevant chunks. If `topic` is empty, samples random chunks from
    BIDA_texts so the system surfaces a question without user guidance.

    Returns dict: {in_scope, question_id, question_text, question_type,
                   source_chunk_ids, max_score, reason?}"""
    docs = []
    max_score = 0.0

    # Auto Q&A pulls exactly 1 chunk (so the answer can be grounded in the
    # same chunk that generated the question — no retrieval flakiness).
    # Gap Finder pulls multiple chunks so the LLM has more context to probe
    # boundaries and missing details from.
    chunk_count = 1 if purpose == PURPOSE_DEMO else top_k_chunks

    if topic and topic.strip():
        in_scope, max_score, docs = is_topic_in_scope(
            topic, vdb, top_k=chunk_count, relevance_threshold=relevance_threshold,
        )
        if not in_scope:
            return {
                "in_scope": False, "question_id": None, "topic": topic,
                "max_score": max_score,
                "reason": (
                    f"'{topic}' doesn't appear to be a BillTrak topic — "
                    f"the BillTrak documents have no closely-related content "
                    f"(max similarity: {max_score:.2f}). Try a different topic."
                ),
            }
        docs = docs[:chunk_count]
    else:
        # No topic: random sample from the corpus so each click surfaces a
        # different angle. Auto Q&A samples 1 chunk; Gap Finder samples more.
        import random
        chunks = extract_chunks(vdb)
        ids, docs_list, metas = chunks["ids"], chunks["documents"], chunks["metadatas"]
        if not ids:
            return {
                "in_scope": False, "question_id": None, "topic": "",
                "reason": "Vectorstore is empty — nothing to generate from.",
            }
        from langchain_core.documents import Document
        sample_size = min(chunk_count, len(ids))
        idxs = random.sample(range(len(ids)), sample_size)
        docs = [
            Document(page_content=docs_list[i], metadata=(metas[i] or {}))
            for i in idxs
        ]

    excerpts = "\n\n---\n\n".join(d.page_content[:excerpt_chars] for d in docs)
    messages = _build_one_question_messages(topic, excerpts, purpose=purpose)

    from core.llm_client import call_llm
    try:
        text = call_llm(
            client, messages, model,
            max_tokens=max_tokens, temperature=temperature,
        )
        items = parse_question_response(text)
    except Exception as e:
        return {
            "in_scope": True, "question_id": None, "topic": topic,
            "reason": f"LLM call failed: {e}",
        }

    if not items:
        return {
            "in_scope": True, "question_id": None, "topic": topic,
            "reason": "LLM returned no parseable question.",
        }

    item = items[0]
    chunk_ids = []
    for d in docs:
        meta = d.metadata or {}
        ident = " · ".join(
            str(meta.get(k)) for k in ("File", "Section", "Subsection", "Split")
            if meta.get(k)
        )
        chunk_ids.append(ident or "?")

    qid = save_one_question(
        db_path, cluster_id=-1, item=item, source_chunk_ids=chunk_ids,
        topic=(topic.strip() or None), purpose=purpose,
    )
    # For Auto Q&A return the source chunk (content + metadata) so the caller
    # can answer directly from it AND persist it as the displayed source.
    source_chunk_content = None
    source_chunk_metadata = None
    if purpose == PURPOSE_DEMO and docs:
        source_chunk_content = docs[0].page_content
        source_chunk_metadata = dict(docs[0].metadata or {})
    return {
        "in_scope": True, "question_id": qid, "topic": topic,
        "question_text": item["text"], "question_type": item["type"],
        "max_score": max_score, "purpose": purpose,
        "source_chunk_content": source_chunk_content,
        "source_chunk_metadata": source_chunk_metadata,
    }


def is_topic_in_scope(
    topic: str,
    vdb: Any,
    top_k: int = 5,
    relevance_threshold: float = 0.3,
) -> tuple[bool, float, list]:
    """Return (in_scope, max_score, top_docs). Uses vector similarity over the
    main vdb — if no chunk scores above the threshold for this topic, treat it
    as out-of-scope."""
    if not topic or not topic.strip():
        return False, 0.0, []
    try:
        results = vdb.similarity_search_with_relevance_scores(topic, k=top_k)
    except Exception:
        return False, 0.0, []
    if not results:
        return False, 0.0, []
    max_score = results[0][1]
    return max_score >= relevance_threshold, max_score, [d for d, _ in results]


def _build_topic_question_messages(topic: str, excerpts: str, per_type: int) -> list[dict]:
    system = (
        "You generate evaluation questions about a corporate knowledge base. "
        "Output ONLY a JSON array, no prose, no markdown fences. "
        'Each item: {"type": one of (factoid, conceptual, edge_case), "text": <question>}.'
    )
    user = (
        f"Topic: {topic}\n\n"
        f"Source excerpts:\n---\n{excerpts}\n---\n\n"
        f"Generate questions ABOUT THE TOPIC '{topic}' using ONLY information that can be supported by the excerpts above. "
        f"Do not invent facts. If an excerpt doesn't relate to the topic, ignore it.\n\n"
        f"Generate exactly {per_type} factoid questions (what/when/who/how-many), "
        f"{per_type} conceptual questions (why/how/explain), and "
        f"{per_type} edge-case questions (boundaries, contradictions, what-if). "
        f"Total = {3 * per_type} questions. Output a single JSON array of objects."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def generate_questions_for_topic(
    *,
    client: Any,
    model: str,
    vdb: Any,
    db_path: str | Path,
    topic: str,
    per_type: int = 3,
    top_k_chunks: int = 5,
    relevance_threshold: float = 0.3,
    excerpt_chars: int = 1500,
    max_tokens: int = 1500,
    temperature: float = 0.7,
) -> dict:
    """User-facing entry point: given a free-text topic, validate scope via
    vector similarity against the main corpus, then generate questions about
    that topic from the matching chunks. Returns a dict summary."""
    if not topic or not topic.strip():
        return {
            "in_scope": False, "n_questions": 0, "topic": topic,
            "reason": "Please enter a topic.",
            "max_score": 0.0,
        }

    in_scope, max_score, docs = is_topic_in_scope(
        topic, vdb, top_k=top_k_chunks, relevance_threshold=relevance_threshold,
    )
    if not in_scope:
        return {
            "in_scope": False, "n_questions": 0, "topic": topic,
            "max_score": max_score,
            "reason": (
                f"'{topic}' doesn't appear to be a BillTrak topic — "
                f"the BillTrak documents have no closely-related content "
                f"(max similarity score: {max_score:.2f}). Try a different "
                f"topic or rephrase."
            ),
        }

    from core.llm_client import call_llm
    excerpts = "\n\n---\n\n".join(d.page_content[:excerpt_chars] for d in docs)
    messages = _build_topic_question_messages(topic, excerpts, per_type)
    try:
        text = call_llm(
            client, messages, model,
            max_tokens=max_tokens, temperature=temperature,
        )
        items = parse_question_response(text)
    except Exception as e:
        return {
            "in_scope": True, "n_questions": 0, "topic": topic,
            "max_score": max_score,
            "reason": f"LLM call failed: {e}",
        }

    if not items:
        return {
            "in_scope": True, "n_questions": 0, "topic": topic,
            "max_score": max_score,
            "reason": "LLM returned no parseable questions.",
        }

    # Identifier per source chunk — combine the most distinctive metadata fields
    # we know exist on BIDA_texts so the audit row points back at a real chunk.
    chunk_ids = []
    for d in docs:
        meta = d.metadata or {}
        ident = " · ".join(
            str(meta.get(k)) for k in ("File", "Section", "Subsection", "Split")
            if meta.get(k)
        )
        chunk_ids.append(ident or "?")

    n_saved = save_questions(
        db_path, cluster_id=-1, items=items, source_chunk_ids=chunk_ids, topic=topic.strip(),
    )
    return {
        "in_scope": True, "n_questions": n_saved, "topic": topic,
        "max_score": max_score,
    }


def list_synthetic_questions(
    db_path: str | Path,
    status: Optional[str] = None,
    limit: int = 200,
) -> list[dict]:
    init_questions_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        if status:
            rows = conn.execute(
                "SELECT * FROM synthetic_questions WHERE status = ? ORDER BY id DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM synthetic_questions ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def delete_all_synthetic_questions(db_path: str | Path) -> int:
    init_questions_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.execute("DELETE FROM synthetic_questions")
        return cur.rowcount


def get_synthetic_question(db_path: str | Path, question_id: int) -> Optional[dict]:
    init_questions_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM synthetic_questions WHERE id = ?", (question_id,)
        ).fetchone()
        return dict(row) if row else None


def save_question_answer(
    db_path: str | Path,
    question_id: int,
    answer_text: str,
    confidence: Optional[float],
    missing_info: Optional[str],
    num_text_docs: Optional[int] = None,
    num_image_docs: Optional[int] = None,
    source_docs_json: Optional[str] = None,
) -> bool:
    init_questions_db(db_path)
    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.execute(
            """
            UPDATE synthetic_questions
            SET answer_text = ?,
                answer_confidence = ?,
                answer_missing_info = ?,
                answered_at = ?,
                answer_num_text_docs = ?,
                answer_num_image_docs = ?,
                answer_source_docs_json = ?,
                status = 'answered'
            WHERE id = ?
            """,
            (
                answer_text,
                confidence,
                missing_info,
                datetime.now().isoformat(timespec="seconds"),
                num_text_docs,
                num_image_docs,
                source_docs_json,
                question_id,
            ),
        )
        return cur.rowcount > 0


def save_answer_and_record_gap(
    db_path: str | Path,
    question_id: int,
    answer: str,
    confidence: Optional[float],
    missing_info: Optional[str],
    num_text_docs: int,
    num_image_docs: int = 0,
    user_name: Optional[str] = None,
    model: Optional[str] = None,
    source_docs_json: Optional[str] = None,
) -> Optional[int]:
    """Cache the answer + classify as gap. If is_gap and no gap row is already
    linked to this synth question, create one in `gaps` and link via
    synthetic_questions.gap_id. Returns the linked gap_id (existing or new),
    or None if not a gap."""
    from core.gap_detection import GapMetadata, is_gap, record_gap

    save_question_answer(
        db_path, question_id, answer, confidence, missing_info,
        num_text_docs=num_text_docs, num_image_docs=num_image_docs,
        source_docs_json=source_docs_json,
    )
    meta = GapMetadata(confidence=confidence, missing_info=missing_info)
    if not is_gap(meta, num_text_docs, num_image_docs):
        return None

    row = get_synthetic_question(db_path, question_id)
    if not row:
        return None
    existing = row.get("gap_id")
    if existing:
        return existing

    gid = record_gap(
        db_path,
        question=row["text"],
        answer=answer,
        metadata=meta,
        num_text_docs=num_text_docs,
        num_image_docs=num_image_docs,
        user_name=user_name,
        model=model,
    )
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE synthetic_questions SET gap_id = ? WHERE id = ?",
            (gid, question_id),
        )
    return gid


def answer_synthetic_question(
    *,
    client: Any,
    model: str,
    embeddings: Any,
    vdb: Any,
    system_prompt_template: str,
    question_text: str,
    content_summary: str = "",
    validated_vdb: Any = None,
    image_vdb: Any = None,
    bm25_index: Any = None,
    bm25_corpus_docs: Any = None,
    reranker_model: Any = None,
    **llm_kwargs: Any,
) -> dict:
    """Run one synthetic question through retrieve → compose → call_llm
    (non-streaming). Returns dict with clean answer text + parsed gap metadata
    + retrieved-doc counts. Caller persists via save_question_answer."""
    from core.gap_detection import GapMetadata, is_gap, parse_metadata_trailer
    from core.rag import answer_question

    result = answer_question(
        question_text,
        client=client, model=model,
        embeddings=embeddings, vdb=vdb,
        system_prompt_template=system_prompt_template,
        content_summary=content_summary,
        validated_vdb=validated_vdb,
        image_vdb=image_vdb,
        bm25_index=bm25_index,
        bm25_corpus_docs=bm25_corpus_docs,
        reranker_model=reranker_model,
        stream=False,
        **llm_kwargs,
    )
    cleaned, metadata = parse_metadata_trailer(result.text)
    n_text = len(result.retrieved.text_docs)
    n_image = len(result.retrieved.image_docs)
    source_docs = [
        {"page_content": d.page_content, "metadata": dict(d.metadata or {})}
        for d in result.retrieved.text_docs
    ]
    return {
        "answer": cleaned,
        "confidence": metadata.confidence,
        "missing_info": metadata.missing_info,
        "num_text_docs": n_text,
        "num_image_docs": n_image,
        "is_gap": is_gap(metadata, n_text, n_image),
        "source_docs": source_docs,
    }


def generate_and_save_all(
    *,
    client: Any,
    model: str,
    vdb: Any,
    db_path: str | Path,
    n_clusters: Optional[int] = None,
    per_type: int = 3,
    representative_chunks: int = 3,
    excerpt_chars: int = 1500,
) -> GenerationSummary:
    """End-to-end: extract → cluster → per-cluster generate → save."""
    chunks = extract_chunks(vdb)
    ids, embs, docs = chunks["ids"], chunks["embeddings"], chunks["documents"]
    n_chunks = len(ids)
    if n_chunks == 0:
        return GenerationSummary(0, 0, 0, [], ["no chunks in vdb"])

    if n_clusters is None:
        n_clusters = choose_n_clusters(n_chunks)
    # Clamp to chunk count — sklearn KMeans rejects n_clusters > n_samples.
    if n_clusters > n_chunks:
        n_clusters = n_chunks
    labels, centroids = cluster_embeddings(embs, n_clusters)

    total_q = 0
    per_cluster: list[dict] = []
    errors: list[str] = []

    for cid in range(n_clusters):
        cluster_idxs = [i for i, lbl in enumerate(labels) if lbl == cid]
        if not cluster_idxs:
            continue
        cluster_ids = [ids[i] for i in cluster_idxs]
        cluster_embs = [embs[i] for i in cluster_idxs]
        cluster_docs = [docs[i] for i in cluster_idxs]

        rep_local = select_representative_chunks(cluster_embs, centroids[cid], representative_chunks)
        rep_doc_ids = [cluster_ids[i] for i in rep_local]
        rep_docs = [cluster_docs[i] for i in rep_local]

        excerpts = "\n\n---\n\n".join(d[:excerpt_chars] for d in rep_docs)
        try:
            items = generate_questions_for_cluster(
                client=client, model=model, excerpts=excerpts, per_type=per_type,
            )
        except Exception as e:
            errors.append(f"cluster {cid}: {e}")
            continue

        if items:
            n_saved = save_questions(db_path, cid, items, rep_doc_ids)
            total_q += n_saved
            per_cluster.append({"cluster_id": cid, "n_questions": n_saved})

    return GenerationSummary(n_chunks, n_clusters, total_q, per_cluster, errors)
