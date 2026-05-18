from rank_bm25 import BM25Okapi
from langchain_core.documents import Document
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import string
import os
import pickle
from utils.logging_utils import log_message

# Cache stopwords and punctuation at module level (avoids rebuilding per call)
_STOP_WORDS = set(stopwords.words('english'))
_PUNCTUATION = set(string.punctuation)

BM25_TEXT_INDEX_FILE = "bm25_text_index.pkl"
BM25_IMAGE_INDEX_FILE = "bm25_image_index.pkl"


def tokenize_for_bm25(text):
    """Lowercase, tokenize, remove stop words and punctuation."""
    tokens = word_tokenize(text.lower())
    return [t for t in tokens if t not in _STOP_WORDS and t not in _PUNCTUATION]


def build_bm25_index(chroma_collection):
    """Fetch all docs from ChromaDB, build BM25Okapi index.

    Returns (bm25_index, corpus_docs) where corpus_docs is a list of
    LangChain Document objects preserving page_content + metadata.
    """
    result = chroma_collection.get(include=["documents", "metadatas"])
    documents = result["documents"]
    metadatas = result["metadatas"]

    corpus_docs = []
    tokenized_corpus = []

    for doc_text, meta in zip(documents, metadatas):
        corpus_docs.append(Document(page_content=doc_text, metadata=meta))
        tokenized_corpus.append(tokenize_for_bm25(doc_text))

    bm25_index = BM25Okapi(tokenized_corpus)
    log_message('info', f"BM25 index built with {len(corpus_docs)} documents")
    return bm25_index, corpus_docs


def build_bm25_image_index(image_collection):
    """Build BM25 index for images using combined context text.

    Tokenizes preceding_text + qualitative_ocr + following_text so that
    keyword queries match the surrounding business terminology, not just
    the generic UI description stored in page_content.

    Returns (bm25_index, corpus_docs).
    """
    result = image_collection.get(include=["documents", "metadatas"])
    documents = result["documents"]
    metadatas = result["metadatas"]

    corpus_docs = []
    tokenized_corpus = []

    for doc_text, meta in zip(documents, metadatas):
        corpus_docs.append(Document(page_content=doc_text, metadata=meta))
        combined = " ".join(filter(None, [
            meta.get("preceding_text", ""),
            doc_text,
            meta.get("following_text", ""),
        ]))
        tokenized_corpus.append(tokenize_for_bm25(combined))

    bm25_index = BM25Okapi(tokenized_corpus)
    log_message('info', f"BM25 image index built with {len(corpus_docs)} documents")
    return bm25_index, corpus_docs


def bm25_retrieve(bm25_index, corpus_docs, query, top_k=4):
    """Score every document against the query and return the top_k results."""
    tokenized_query = tokenize_for_bm25(query)
    scores = bm25_index.get_scores(tokenized_query)

    # Pair scores with indices, filter zeros, sort descending
    scored = [(i, s) for i, s in enumerate(scores) if s > 0]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:top_k]

    results = []
    for i, s in top:
        doc = Document(page_content=corpus_docs[i].page_content,
                       metadata={**corpus_docs[i].metadata, 'bm25_score': s})
        results.append(doc)
    return results


def save_bm25_indexes(persist_dir, bm25_index, corpus_docs, bm25_image_index, image_corpus_docs):
    """Pickle BM25 indexes to disk inside the vectorstore directory."""
    os.makedirs(persist_dir, exist_ok=True)

    text_path = os.path.join(persist_dir, BM25_TEXT_INDEX_FILE)
    with open(text_path, 'wb') as f:
        pickle.dump((bm25_index, corpus_docs), f)
    log_message('info', f"BM25 text index saved to {text_path}")

    if bm25_image_index is not None:
        image_path = os.path.join(persist_dir, BM25_IMAGE_INDEX_FILE)
        with open(image_path, 'wb') as f:
            pickle.dump((bm25_image_index, image_corpus_docs), f)
        log_message('info', f"BM25 image index saved to {image_path}")


def load_bm25_indexes(persist_dir):
    """Load pickled BM25 indexes from disk.

    Returns (bm25_index, corpus_docs, bm25_image_index, image_corpus_docs).
    Any pair that doesn't exist on disk is returned as (None, None).
    """
    bm25_index, corpus_docs = None, None
    bm25_image_index, image_corpus_docs = None, None

    text_path = os.path.join(persist_dir, BM25_TEXT_INDEX_FILE)
    if os.path.exists(text_path):
        with open(text_path, 'rb') as f:
            bm25_index, corpus_docs = pickle.load(f)
        log_message('info', f"BM25 text index loaded from {text_path} ({len(corpus_docs)} docs)")

    image_path = os.path.join(persist_dir, BM25_IMAGE_INDEX_FILE)
    if os.path.exists(image_path):
        with open(image_path, 'rb') as f:
            bm25_image_index, image_corpus_docs = pickle.load(f)
        log_message('info', f"BM25 image index loaded from {image_path} ({len(image_corpus_docs)} docs)")

    return bm25_index, corpus_docs, bm25_image_index, image_corpus_docs
