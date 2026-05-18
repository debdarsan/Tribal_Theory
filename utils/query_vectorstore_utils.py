import os
import re
from langchain_core.documents import Document
from utils.sys_utils import *
from utils.json_utils import *
from utils.vectorstore_utils import *
from vars.s_state import *
from utils.stopwatch_utils import *
from consts.consts import *
from utils.bm25_utils import bm25_retrieve
import concurrent.futures

metadata_field_order = ['File', 'Section', 'Subsection', 'Subsubsection', 'Emphasis', 'Split', 'Tokens', 'Date', 'User']


def consolidate_docs(all_docs, docs, generation_method):
    existing_splits = set(doc.metadata.get('Split', '') for doc in all_docs)
    new_doc_added = False
    for doc in docs:
        if 'Split' in doc.metadata:
            split_value = doc.metadata['Split']
            if split_value in existing_splits:
                existing_doc = next((d for d in all_docs if d.metadata.get('Split') == split_value), None)
                if existing_doc:
                    existing_doc.metadata['generation_method'] += f", {generation_method}"
                continue  # Skip the document if the split value already exists
            existing_splits.add(split_value)
        doc.metadata['generation_method'] = generation_method
        all_docs.append(doc)
        new_doc_added = True
    return all_docs, new_doc_added


def rank_and_dedup_text_docs(all_docs):
    """Sort text docs by retrieval_score descending, dedup by Split keeping highest score.
    Preserves generation_method annotations from all methods that found the same Split.
    Used as a fallback when no reranker model is available."""
    # Sort by score descending
    all_docs.sort(key=lambda d: d.metadata.get('retrieval_score', 0), reverse=True)

    seen_splits = {}  # Split -> doc
    ranked = []
    for doc in all_docs:
        split_value = doc.metadata.get('Split', '')
        if split_value and split_value in seen_splits:
            # Same Split found by multiple methods — append method name
            existing = seen_splits[split_value]
            new_method = doc.metadata.get('generation_method', '')
            if new_method and new_method not in existing.metadata.get('generation_method', ''):
                existing.metadata['generation_method'] += f", {new_method}"
        else:
            if split_value:
                seen_splits[split_value] = doc
            ranked.append(doc)
    return ranked


def dedup_and_rerank_text_docs(all_docs, query, reranker_model, top_k):
    """First-seen dedup by Split, then cross-encoder rerank, return top_k.
    Falls back to rank_and_dedup_text_docs() when reranker_model is None."""
    if reranker_model is None:
        return rank_and_dedup_text_docs(all_docs)[:top_k]

    seen_splits = set()
    deduped = []
    for doc in all_docs:
        split_value = doc.metadata.get('Split', '')
        if split_value and split_value in seen_splits:
            existing = next((d for d in deduped if d.metadata.get('Split') == split_value), None)
            if existing:
                new_method = doc.metadata.get('generation_method', '')
                if new_method and new_method not in existing.metadata.get('generation_method', ''):
                    existing.metadata['generation_method'] += f", {new_method}"
            continue
        if split_value:
            seen_splits.add(split_value)
        deduped.append(doc)

    from utils.rerank_utils import rerank
    return rerank(reranker_model, query, deduped, top_k)


def retrive_docs_langchain(question, embeddings, vdb, option):
    docs = []
    query_embeddings = embeddings.embed_documents([question])
    if option == 'similarity_search':
        # Use scored variant — returns list of (Document, relevance_score)
        results = vdb.similarity_search_with_relevance_scores(question, k=num_docs_returned_by_chain)
        for doc, score in results:
            doc.metadata['retrieval_score'] = score
            docs.append(doc)
    elif option == 'similarity_search_by_vectors':
        docs = vdb.similarity_search_by_vector(query_embeddings, k=num_docs_returned_by_chain, num_docs_fetch_and_feed_to_llm=10)
        # Position-based scores (no scored variant available)
        for i, doc in enumerate(docs):
            doc.metadata['retrieval_score'] = (len(docs) - i) / len(docs) if docs else 0
    elif option == 'max_marginal_relevance_search':
        docs = vdb.max_marginal_relevance_search(question, k=num_docs_returned_by_chain, num_docs_fetch_and_feed_to_llm=10)
        # Position-based scores (MMR re-ranks for diversity, no scores returned)
        for i, doc in enumerate(docs):
            doc.metadata['retrieval_score'] = (len(docs) - i) / len(docs) if docs else 0
    elif option == 'max_marginal_relevance_search_by_vectors':
        docs = vdb.max_marginal_relevance_search_by_vector(query_embeddings, k=num_docs_returned_by_chain, num_docs_fetch_and_feed_to_llm=10)
        for i, doc in enumerate(docs):
            doc.metadata['retrieval_score'] = (len(docs) - i) / len(docs) if docs else 0
    return docs


def retrieve_documents_by_bm25(question, bm25_index, corpus_docs, top_k=bm25_top_k):
    """Retrieve documents using BM25 keyword scoring.
    Normalizes BM25 scores to 0-1 range for cross-method ranking."""
    if bm25_index is None or corpus_docs is None:
        return []
    docs = bm25_retrieve(bm25_index, corpus_docs, question, top_k)
    max_score = max((d.metadata.get('bm25_score', 0) for d in docs), default=1.0)
    for doc in docs:
        raw = doc.metadata.pop('bm25_score', 0)
        doc.metadata['retrieval_score'] = raw / max_score if max_score > 0 else 0
    return docs


# List of document retrieval methods
doc_retrieval_methods = [
    'similarity_search',
    # 'similarity_search_by_vectors',
    'max_marginal_relevance_search',
    # 'max_marginal_relevance_search_by_vectors'
    'bm25_search',
]

# Mapping of method names to their respective function objects and parameters
method_to_function_mapping = {
    'similarity_search': (retrive_docs_langchain, 'similarity_search'),
    'similarity_search_by_vectors': (retrive_docs_langchain, 'similarity_search_by_vectors'),
    'max_marginal_relevance_search': (retrive_docs_langchain, 'max_marginal_relevance_search'),
    'max_marginal_relevance_search_by_vectors': (retrive_docs_langchain, 'max_marginal_relevance_search_by_vectors'),
    'bm25_search': (retrieve_documents_by_bm25, None),
}


def return_docs_from_vectorstore_parallel(question, embeddings, vdb, bm25_index=None, bm25_corpus_docs=None, reranker_model=None, rerank_top_k_val=rerank_top_k, use_process_pool=False):
    all_docs = []

    # Choose the executor based on the use_process_pool flag
    Executor = concurrent.futures.ProcessPoolExecutor if use_process_pool else concurrent.futures.ThreadPoolExecutor

    with Executor() as executor:
        future_to_method = {}

        for method in doc_retrieval_methods:
            func, param = method_to_function_mapping[method]

            if func == retrieve_documents_by_bm25:
                future = executor.submit(func, question, bm25_index, bm25_corpus_docs)
            elif func == retrive_docs_langchain:
                future = executor.submit(func, question, embeddings, vdb, param)
            else:
                continue

            future_to_method[future] = method

        for future in concurrent.futures.as_completed(future_to_method):
            method = future_to_method[future]
            try:
                docs = future.result()
                for doc in docs:
                    doc.metadata['generation_method'] = method
                all_docs.extend(docs)
                log_message('info', f"[yellow]{method}: {len(docs)} docs retrieved[/yellow]")
            except Exception as exc:
                log_message('error', f"[red]{method}: generated an exception: {exc}[/red]")

    # Dedup by Split, then cross-encoder rerank (falls back to score-fusion dedup if no reranker)
    all_docs = dedup_and_rerank_text_docs(all_docs, question, reranker_model, rerank_top_k_val)
    log_message('info', f"After dedup + rerank: {len(all_docs)} text docs")
    return all_docs


def retrieve_from_image_collection(question, embeddings, image_vdb, top_k=3):
    """
    Query the image collection for relevant screenshots with relevance scores.

    Args:
        question: User's question
        embeddings: Embedding model
        image_vdb: The image collection vectorstore
        top_k: Number of results to return

    Returns:
        List of Document objects with retrieval_score in metadata
    """
    if image_vdb is None:
        return []

    try:
        results = image_vdb.similarity_search_with_relevance_scores(question, k=top_k)
        docs = []
        for doc, score in results:
            doc.metadata['collection_type'] = 'image'
            doc.metadata['retrieval_score'] = score
            docs.append(doc)
        log_message('info', f"Retrieved {len(docs)} images from image collection (scores: {[f'{s:.3f}' for _, s in results]})")
        return docs
    except Exception as e:
        log_message('error', f"Error retrieving from image collection: {e}")
        return []


def retrieve_from_image_collection_bm25(question, bm25_image_index, bm25_image_corpus_docs, top_k=bm25_top_k):
    """Retrieve images using BM25 over combined context text (preceding + OCR + following).
    Normalizes BM25 scores to 0-1 range for cross-method ranking."""
    if bm25_image_index is None or bm25_image_corpus_docs is None:
        return []
    docs = bm25_retrieve(bm25_image_index, bm25_image_corpus_docs, question, top_k)
    # Normalize raw BM25 scores to 0-1
    max_score = max((d.metadata.get('bm25_score', 0) for d in docs), default=1.0)
    scores_log = []
    for doc in docs:
        raw = doc.metadata.pop('bm25_score', 0)
        normalized = raw / max_score if max_score > 0 else 0
        doc.metadata['collection_type'] = 'image'
        doc.metadata['retrieval_score'] = normalized
        scores_log.append(f"{normalized:.3f}")
    log_message('info', f"BM25 image search retrieved {len(docs)} images (scores: {scores_log})")
    return docs


def return_docs_from_both_collections_parallel(
    question,
    embeddings,
    vdb,
    image_vdb=None,
    text_top_k=3,
    image_top_k=3,
    bm25_index=None,
    bm25_corpus_docs=None,
    bm25_image_index=None,
    bm25_image_corpus_docs=None,
    reranker_model=None,
    rerank_top_k_val=rerank_top_k,
    use_process_pool=False
):
    """
    Query both text and image collections in parallel.

    Args:
        question: User's question
        embeddings: Embedding model
        vdb: Text collection vectorstore
        image_vdb: Image collection vectorstore (optional)
        text_top_k: Number of text results per method
        image_top_k: Number of image results
        use_process_pool: Whether to use process pool instead of thread pool

    Returns:
        Tuple of (text_docs, image_docs)
    """
    text_docs = []
    image_docs = []

    # Choose executor
    Executor = concurrent.futures.ProcessPoolExecutor if use_process_pool else concurrent.futures.ThreadPoolExecutor

    with Executor() as executor:
        futures = {}

        # Submit text retrieval tasks
        for method in doc_retrieval_methods:
            func, param = method_to_function_mapping[method]

            if func == retrieve_documents_by_bm25:
                future = executor.submit(func, question, bm25_index, bm25_corpus_docs)
            elif func == retrive_docs_langchain:
                future = executor.submit(func, question, embeddings, vdb, param)
            else:
                continue

            futures[future] = ('text', method)

        # Submit image retrieval task
        if image_vdb is not None:
            future = executor.submit(retrieve_from_image_collection, question, embeddings, image_vdb, image_top_k)
            futures[future] = ('image', 'image_similarity_search')

        # Submit BM25 image retrieval task
        if bm25_image_index is not None:
            future = executor.submit(retrieve_from_image_collection_bm25, question, bm25_image_index, bm25_image_corpus_docs)
            futures[future] = ('image', 'image_bm25_search')

        # Collect results
        for future in concurrent.futures.as_completed(futures):
            collection_type, method = futures[future]
            try:
                docs = future.result()
                if collection_type == 'text':
                    for doc in docs:
                        doc.metadata['generation_method'] = method
                    text_docs.extend(docs)
                    log_message('info', f"[text] {method}: {len(docs)} retrieved")
                else:
                    image_docs.extend(docs)
                    log_message('info', f"[image] {method}: {len(docs)} retrieved")
            except Exception as exc:
                log_message('error', f"{collection_type} - {method}: Exception: {exc}")

    # Dedup by Split, then cross-encoder rerank (falls back to score-fusion dedup if no reranker)
    text_docs = dedup_and_rerank_text_docs(text_docs, question, reranker_model, rerank_top_k_val)
    for doc in text_docs:
        if 'collection_type' not in doc.metadata:
            doc.metadata['collection_type'] = 'text'

    # Rank image results by retrieval_score, dedup by static_url keeping highest score, take top_k
    image_docs.sort(key=lambda d: d.metadata.get('retrieval_score', 0), reverse=True)
    seen_urls = set()
    ranked_image_docs = []
    for doc in image_docs:
        url = doc.metadata.get('static_url', '')
        if url not in seen_urls:
            seen_urls.add(url)
            ranked_image_docs.append(doc)
    image_docs = ranked_image_docs[:image_top_k]

    # Filter images below score threshold
    pre_filter_count = len(image_docs)
    image_docs = [d for d in image_docs if d.metadata.get('retrieval_score', 0) >= image_score_threshold]
    if pre_filter_count > len(image_docs):
        log_message('info', f"Score threshold ({image_score_threshold}): filtered {pre_filter_count - len(image_docs)} low-score images")

    # Cross-collection dedup: remove images already embedded in text chunks
    text_image_urls = set()
    img_pattern = re.compile(r"<img\s+src='(\./app/static/[^']+)'")
    for doc in text_docs:
        for match in img_pattern.finditer(doc.page_content):
            text_image_urls.add(match.group(1))
    if text_image_urls:
        pre_dedup_count = len(image_docs)
        image_docs = [d for d in image_docs if d.metadata.get('static_url', '') not in text_image_urls]
        removed = pre_dedup_count - len(image_docs)
        if removed:
            log_message('info', f"Cross-collection dedup: removed {removed} images already in text sources")

    log_message('info', f"Total results: {len(text_docs)} text docs, {len(image_docs)} image docs")
    return text_docs, image_docs


def combine_text_and_image_docs(text_docs, image_docs):
    """
    Combine text and image documents into a single list with clear separation.

    Args:
        text_docs: List of text Document objects
        image_docs: List of image Document objects

    Returns:
        Combined list with text docs first, then image docs
    """
    return text_docs + image_docs
