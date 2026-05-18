from sentence_transformers import CrossEncoder
from utils.logging_utils import log_message


def load_reranker(model_name, device='cpu'):
    """Load a CrossEncoder reranker model. Returns None on failure."""
    try:
        model = CrossEncoder(model_name, device=device)
        log_message('info', f"Reranker loaded: {model_name} on {device}")
        return model
    except Exception as e:
        log_message('error', f"Failed to load reranker {model_name}: {e}")
        return None


def rerank(reranker_model, query, docs, top_k):
    """Score (query, doc.page_content) pairs with a cross-encoder.

    Overwrites doc.metadata['retrieval_score'] with the unified cross-encoder
    score so downstream code has a single comparable scale. Returns the top_k
    docs sorted by score desc. If reranker_model is None or docs is empty,
    falls back to returning docs[:top_k] unchanged.
    """
    if reranker_model is None or not docs:
        return docs[:top_k]

    pairs = [(query, d.page_content) for d in docs]
    scores = reranker_model.predict(pairs)
    scored = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)

    ranked = []
    for doc, score in scored[:top_k]:
        doc.metadata['retrieval_score'] = float(score)
        doc.metadata['reranked'] = True
        ranked.append(doc)

    if ranked:
        top_score = scored[0][1]
        bottom_kept = scored[min(top_k, len(scored)) - 1][1]
        log_message(
            'info',
            f"Reranked {len(docs)} -> {len(ranked)} "
            f"(top: {top_score:.3f}, bottom kept: {bottom_kept:.3f})"
        )
    return ranked
