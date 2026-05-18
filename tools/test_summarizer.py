from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import re

# Function to summarize an answer based on a question
def summarize_based_on_question(question, answer, summarize_factor = 9):
    # Split answer into sentences
    sentences = re.split(r"(?<=[.!?])\s+(?!\s*<img\b)", answer.strip())
        
    num_sentences = int(len(sentences)/summarize_factor + 1)

    # Load a pre-trained sentence transformer model
    model = SentenceTransformer('all-MiniLM-L6-v2')

    # Encode question and sentences
    question_embedding = model.encode([question])
    sentence_embeddings = model.encode(sentences)

    # Calculate cosine similarity
    similarities = cosine_similarity(question_embedding, sentence_embeddings)

    # Get indices of sentences with highest similarity scores
    top_indices = np.argsort(similarities[0])[::-1][:num_sentences]

    # Extract the corresponding sentences
    summary_sentences = [sentences[idx] for idx in sorted(top_indices)]
    
    return ' '.join(summary_sentences)

# Example question and answer
question = "Explain power iterations and its process in maximum detail, along with images"
answer = "Power Iterations is a process used in the ASSET Suite's NR Static Simulations and LTE Static Simulations to assign a set of link powers that satisfy the SINR (Signal-to-Interference-plus-Noise Ratio) requirements of randomly spread terminals. The main goal of this process is to provide measures of system load for a particular distribution of terminals by calculating uplink and downlink transmission powers for all the links in the system.\n\nThe process begins by placing the system in the state of an unloaded network. This is done by setting all link powers to zero and making all resources available at the cells. The link powers in the system are then calculated iteratively by repeatedly cycling through the list of randomly spread terminals and applying specific logic to each terminal.\n\nHere is the detailed process:\n\n1. If a terminal is already 'connected', it is 'disconnected' as follows:\n   - Zero the UL (Uplink) & DL (Downlink) powers for the terminal.\n   - Zero the cell resources used by the terminal.\n   - Recalculate the UL interference on all cells (because the UL power for the terminal has been zeroed).\n   - Recalculate the total DL power on all cells (because the DL powers for the terminal have been zeroed).\n   - Recalculate resources available on all cells (because the terminal has released resources).\n\n2. The system then tries to 'connect' the terminal to the network in the most favourable way possible. This may be different from how it was previously 'connected'. For example, it might be preferable to use a different carrier if interference has increased since the last time the terminal was evaluated.\n\n3. If a connection is possible, then 'connect' the terminal as follows:\n   - Set the UL and DL powers for the terminal.\n   - Set the cell resources used by the terminal.\n   - Recalculate the UL interference on all cells (because the UL power for the terminal has been set).\n   - Recalculate the total DL power on all cells (because the DL powers for the terminal have been set).\n   - Recalculate resources available on all cells (because the terminal has consumed resources).\n\nThis process is repeated several times through the list of terminals until a stable set of link powers emerge. After the first cycle, most 'connected' terminals underachieve their SINR requirements because they see no interference and so have their link powers set to low values. However, successive cycles through the terminal list produce increasingly accurate pictures of network interference. After a few cycles, practically all the 'connected' terminals have link powers that achieve the SINR requirements, and the system interference no longer changes significantly.\n\nThe power iterations have converged to produce a plausible picture of served and failed terminals in the network. The following image illustrates how a snapshot converges with successive cycles through the terminal list:\n\n<img src='./app/static/NR Static Simulations V2023 Q2/NR Static Simulations V2023 Q2_img6.png' alt='The power iterations have converged to produce a plausible picture of served and failed terminals in the network.' height=300>\n\nA good practical measure of convergence is to examine how the interference changes between cycles. This is considerably faster than measuring the distribution of achieved $SINR$ values."

# Summarize the answer based on the question
summary = summarize_based_on_question(question, answer)
print(summary)