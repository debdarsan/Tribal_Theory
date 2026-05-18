from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import spacy
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import Normalizer
from vars.s_state import *
import re

def summarize_based_on_question(question, answer, summarize_factor = 3):
    # Split answer into sentences
    sentences = re.split(r"(?<=[.!?])\s+(?!\s*<img\b)", answer.strip())
    num_sentences = int(len(sentences)/summarize_factor + 1)

    # Encode question and sentences
    question_embedding = ss.sentence_transformer_model.encode([question])
    sentence_embeddings = ss.sentence_transformer_model.encode(sentences)

    # Calculate cosine similarity
    similarities = cosine_similarity(question_embedding, sentence_embeddings)

    # Get indices of sentences with highest similarity scores
    top_indices = np.argsort(similarities[0])[::-1][:num_sentences]

    # Extract the corresponding sentences
    summary_sentences = [sentences[idx] for idx in sorted(top_indices)]
    
    return ' '.join(summary_sentences)

def preprocess_text_for_placeholders(text):
    text = re.sub(r'\$.*?\$', 'LATEXPLACEHOLDER', text)
    text = re.sub(r'<img .*?>', 'IMAGEPLACEHOLDER', text)
    return text

def postprocess_answer_with_placeholders(answer, original_text):
    latex_matches = re.findall(r'\$.*?\$', original_text)
    image_matches = re.findall(r'<img .*?>', original_text)
    for placeholder, replacement in zip(['LATEXPLACEHOLDER', 'IMAGEPLACEHOLDER'], [latex_matches, image_matches]):
        for match in replacement:
            answer = answer.replace(placeholder, match, 1)
    return answer

def answer_finder_with_media(question, text_chunks, nlp, n_components=100):
    concatenated_answers = ""
    for text in text_chunks:
        text_preprocessed = preprocess_text_for_placeholders(text)
        
        # Find the answer from each chunk
        answer = sophisticated_answer_finder_with_media(question, text_preprocessed, nlp, n_components)
        concatenated_answers += " " + answer

    # Optionally, generate a final answer from the concatenated answers
    final_answer_preprocessed = preprocess_text_for_placeholders(concatenated_answers)
    final_answer = sophisticated_answer_finder_with_media(question, final_answer_preprocessed, nlp, n_components)
    
    # Post-process to include LaTeX and images
    final_answer_with_media = postprocess_answer_with_placeholders(final_answer, concatenated_answers)
    
    return final_answer_with_media

def sophisticated_answer_finder_with_media(question, text, nlp, n_components=100):
    # Split the document into sentences
    doc = nlp(text)
    sentences = [sent.text for sent in doc.sents]

    # Include the question for vectorization
    sentences_with_question = [question] + sentences

    # Vectorize sentences using TF-IDF
    vectorizer = TfidfVectorizer(stop_words='english', min_df=1, max_df=0.7)
    X = vectorizer.fit_transform(sentences_with_question)

    # Dynamically adjust the number of components for SVD
    n_components = min(n_components, X.shape[1] - 1)

    # Apply LSA
    svd = TruncatedSVD(n_components=n_components)
    normalizer = Normalizer(copy=False)
    lsa = make_pipeline(svd, normalizer)

    X_lsa = lsa.fit_transform(X)

    # Calculate cosine similarity with epsilon to avoid division by zero
    epsilon = 1e-10
    question_vector = X_lsa[0]
    norms = np.linalg.norm(X_lsa[1:], axis=1) * np.linalg.norm(question_vector) + epsilon
    similarities = np.dot(X_lsa[1:], question_vector) / norms
    max_index = np.argmax(similarities)

    # Retrieve the original sentence with placeholders
    return sentences[max_index]

# # Load the English model
# nlp = spacy.load("en_core_web_sm")

# # Example usage
# text_chunks = [
#     "Here is a formula $E=mc^2$ and an image <img src='image.jpg'>.",
#     "Another important equation is $F=ma$."
# ]
# question = "What are the formulas?"

# final_answer = answer_finder_with_media(question, text_chunks, nlp)
# print(final_answer)
