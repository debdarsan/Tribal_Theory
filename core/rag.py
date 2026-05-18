from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Sequence

from langchain_core.documents import Document
from openai import OpenAI

from core.llm_client import call_llm
from utils.query_vectorstore_utils import (
    return_docs_from_both_collections_parallel,
    return_docs_from_vectorstore_parallel,
)


@dataclass
class Retrieved:
    text_docs: list[Document]
    image_docs: list[Document] = field(default_factory=list)

    @property
    def all_docs(self) -> list[Document]:
        return self.text_docs + self.image_docs


@dataclass
class Answer:
    text: str
    retrieved: Retrieved
    model: str


def _query_validated(query: str, validated_vdb: Any, top_k: int) -> list[Document]:
    """Run a small similarity search against the HITL-validated collection
    and tag each result so the LLM can give it more weight."""
    if validated_vdb is None:
        return []
    try:
        results = validated_vdb.similarity_search_with_relevance_scores(query, k=top_k)
    except Exception:
        return []
    docs: list[Document] = []
    for doc, score in results:
        doc.metadata = {
            **(doc.metadata or {}),
            "retrieval_score": float(score),
            "generation_method": "validated_similarity",
            "source": doc.metadata.get("source", "hitl_validated"),
        }
        docs.append(doc)
    return docs


def retrieve(
    query: str,
    *,
    embeddings: Any,
    vdb: Any,
    image_vdb: Any = None,
    bm25_index: Any = None,
    bm25_corpus_docs: Any = None,
    bm25_image_index: Any = None,
    bm25_image_corpus_docs: Any = None,
    reranker_model: Any = None,
    validated_vdb: Any = None,
    validated_top_k: int = 3,
    validated_score_threshold: float = 0.7,
) -> Retrieved:
    # Probe the validated KB first. Return ALL validated entries that beat
    # the threshold — multiple approved answers for similar questions should
    # all surface so the LLM can synthesize them. Manual chunks are skipped
    # entirely when at least one validated entry matches strongly.
    validated_docs = _query_validated(query, validated_vdb, validated_top_k)
    if validated_docs:
        above = [d for d in validated_docs if d.metadata.get("retrieval_score", 0) >= validated_score_threshold]
        if above:
            return Retrieved(text_docs=above, image_docs=[])

    if image_vdb is not None:
        text_docs, image_docs = return_docs_from_both_collections_parallel(
            query,
            embeddings,
            vdb,
            image_vdb,
            bm25_index=bm25_index,
            bm25_corpus_docs=bm25_corpus_docs,
            bm25_image_index=bm25_image_index,
            bm25_image_corpus_docs=bm25_image_corpus_docs,
            reranker_model=reranker_model,
        )
    else:
        text_docs = return_docs_from_vectorstore_parallel(
            query,
            embeddings,
            vdb,
            bm25_index=bm25_index,
            bm25_corpus_docs=bm25_corpus_docs,
            reranker_model=reranker_model,
        )
        image_docs = []

    # Lower-score validated hits get prepended as context but don't override
    # the manual chunks — they're informative but not authoritative.
    if validated_docs:
        text_docs = validated_docs + text_docs

    return Retrieved(text_docs=text_docs, image_docs=image_docs)


def _default_source_text(text_docs: Sequence[Document], image_docs: Sequence[Document]) -> str:
    return "\n\n".join(d.page_content for d in list(text_docs) + list(image_docs))


def compose_messages(
    *,
    question: str,
    system_prompt_template: str,
    source_text: str,
    additional_information: str = "",
    chat_history: Sequence[tuple[str, str]] = (),
    content_summary: str = "",
) -> list[dict[str, str]]:
    chat_history_str = "\n".join(
        f"{str(role).capitalize()}: {text}" for role, text in chat_history
    )
    system_content = system_prompt_template.format(
        question=question,
        content_summary=content_summary,
        additional_information=additional_information,
        chat_history=chat_history_str,
        source_text=source_text,
    ) + "\nAnswer:"
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": question},
    ]


def answer_question(
    query: str,
    *,
    client: OpenAI,
    model: str,
    embeddings: Any,
    vdb: Any,
    system_prompt_template: str,
    image_vdb: Any = None,
    bm25_index: Any = None,
    bm25_corpus_docs: Any = None,
    bm25_image_index: Any = None,
    bm25_image_corpus_docs: Any = None,
    reranker_model: Any = None,
    validated_vdb: Any = None,
    validated_top_k: int = 3,
    validated_score_threshold: float = 0.7,
    chat_history: Sequence[tuple[str, str]] = (),
    additional_information: str = "",
    content_summary: str = "",
    source_text_formatter: Callable[[Sequence[Document], Sequence[Document]], str] | None = None,
    stream: bool = False,
    **llm_kwargs: Any,
) -> Answer | tuple[Iterator[str], Retrieved]:
    retrieved = retrieve(
        query,
        embeddings=embeddings,
        vdb=vdb,
        image_vdb=image_vdb,
        bm25_index=bm25_index,
        bm25_corpus_docs=bm25_corpus_docs,
        bm25_image_index=bm25_image_index,
        bm25_image_corpus_docs=bm25_image_corpus_docs,
        reranker_model=reranker_model,
        validated_vdb=validated_vdb,
        validated_top_k=validated_top_k,
        validated_score_threshold=validated_score_threshold,
    )

    formatter = source_text_formatter or _default_source_text
    source_text = formatter(retrieved.text_docs, retrieved.image_docs)

    messages = compose_messages(
        question=query,
        system_prompt_template=system_prompt_template,
        source_text=source_text,
        additional_information=additional_information,
        chat_history=chat_history,
        content_summary=content_summary,
    )

    if stream:
        chunks = call_llm(client, messages, model, stream=True, **llm_kwargs)
        return chunks, retrieved

    text = call_llm(client, messages, model, stream=False, **llm_kwargs)
    return Answer(text=text, retrieved=retrieved, model=model)
