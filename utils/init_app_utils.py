from dotenv import load_dotenv
from openai import OpenAI
from pymongo import MongoClient
import streamlit as st
import time
import pickle
import pandas as pd
from pathlib import Path
import streamlit_authenticator as stauth
from sentence_transformers import SentenceTransformer
from vars.s_state import *
from utils.logging_utils import *
from utils.vectorstore_utils import define_embeddings, load_vectorstore, load_image_collection
from utils.json_utils import *
import traceback
import torch

# Load environment variables from a .env file (if present).
# Retrieve the OpenAI API key from the environment variables and store it in the OPENAI_API_KEY variable.
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Function to read roles and usernames from an Excel file
def read_users_from_excel(file_path):
    df = pd.read_excel(file_path)
    roles = df['Role'].tolist()
    usernames = df['User ID'].tolist()
    full_names = df['Full Name'].tolist()  # Add this line to read full names
    profile_images = df['Profile Image'].tolist()  # Add this line to read profile images
    return roles, usernames, full_names, profile_images  # Return full names as well

def init_authentication():
    excel_file_path = Path("users.xlsx")  # Update this path
    roles, usernames, full_names, profile_images = read_users_from_excel(excel_file_path)

    # load hashed passwords
    file_path = Path(__file__).parent.parent / "auth.pkl"
    with file_path.open("rb") as file:
        secret_passwords = pickle.load(file)

    # Create a dictionary mapping usernames to full names
    username_to_fullname = dict(zip(usernames, full_names))
    # Create a dictionary mapping usernames to profile images
    username_to_profile_image = dict(zip(usernames, profile_images))
    
    try:
        ss["auth_object"] = stauth.Authenticate(full_names, usernames, secret_passwords, "ASSETDA", "assetcookie", cookie_expiry_days=30)
        print("Authentication object created successfully.", ss["auth_object"])
    except Exception as e:
        st.error("Failed to initialize authentication object.")
        print("Error initializing authentication object:")
        print(traceback.format_exc())
    
    with st.sidebar:
        if ss["auth_object"] != None:
            try:
                _ , ss.authentication_status, ss["user_name"] = ss["auth_object"].login("Login", "sidebar")
                if ss.authentication_status:
                    user_index = usernames.index(ss["user_name"])
                    ss["role"] = roles[user_index]
                if ss["authentication_status"]:
                    ss["full_name"] = username_to_fullname.get(ss["user_name"], "Unknown")
                    ss["profile_image"] = username_to_profile_image.get(ss["user_name"], None)
            except Exception as e:
                st.error("An error occurred during login.")
                print("Error during login:")
                print(traceback.format_exc())
        else:
            st.error("Authentication object could not be created. Please check your stauth.Authenticate parameters.")
            print("error")

        if ss.authentication_status == False:
            st.error("Username/password is incorrect")
    return ss.authentication_status

def init_app_settings(silent=True):
    try:
        # Set up all the directories first
        ss._QA_DIRECTORY = set_chat_related_directories()
        # Debug info
        log_message("info", f"Initialized Directories.")
        if not silent:
            st.toast("Initialized Directories")
            time.sleep(0.1)
    except Exception as e:
        log_message("error", f"Initialization of directories failed: {e}!")
        st.error("Failed initializing directories")
        st.stop()
        
    try:
        # Not used now
        # ss.qa_chat_model = initialize_llm_ex(ss.llm_provider_name, ss.__qa_model_name, ss.__temperature, ss.__max_tokens, ss.__top_p, ss.__presence_penalty, ss.__frequency_penalty, ss.verbose, ss.streaming)
        ss.qa_model = OpenAI()
        # Debug info
        #log_message('info', f"Initialized LLM ({ss.__qa_model_name}).")
        log_message('info', "Using OpenAI().")
        if not silent:
            #st.toast(f"Initialized LLM ({ss.__qa_model_name}).")
            st.toast(f"Initialized OpenAI().")
            time.sleep(0.1)
    except Exception as e:
        #log_message('error', f"Initialization of LLM ({ss.__qa_model_name}) failed: {e}!")
        log_message('error', f"Initialization of OpenAI() failed: {e}!")
        #st.error("Failed initializing LLM")
        st.error("Failed initializing OpenAI()")
        # ss.qa_chat_model = None
        ss.qa_model = None
        st.stop()
        
    try:
        ss.embeddings = define_embeddings(ss.embedding_model_name)
        # Debug info
        log_message('info', f"Initialized Embedding Model ({ss.embedding_model_name}).")
        if not silent:
            st.toast(f"Initialized Embedding ({ss.__qa_model_name}).")
            time.sleep(0.1)
    except Exception as e:
        log_message('error', f"Initialization of embedding model ({ss.embedding_model_name}) failed: {e}!")
        st.error("Failed defining embeddings")
        ss.embeddings = None
        st.stop()
        
    try:
        ss.vectorstore_obj, ss.chroma_collection, ss.existing_ids, ss._vectorstore_record_count = load_vectorstore(ss.vectorstore_type_name, ss.persist_vectordb_dir, ss.embeddings)
        if ss._vectorstore_record_count > 0:
            ss.accept_questions = True
        # Debug info
        log_message('info', f"Loaded Vector DB ({ss.vectorstore_type_name}).")
        log_message('info', f"{ss.vectorstore_type_name} record count: {ss._vectorstore_record_count}.")
        if not silent:
            st.toast(f"{ss.vectorstore_type_name} record count: {ss._vectorstore_record_count}.")
            time.sleep(0.1)
    except Exception as e:
        log_message('error', f"Loading Vectorstore ({ss.vectorstore_type_name}) failed: {e}!")
        st.error("Failed loading vectorstore")
        ss.vectorstore_obj = None
        ss.chroma_collection = None
        ss.existing_ids = []
        ss._vectorstore_record_count = 0
        st.stop()

    # Load the HITL-validated collection that the gap-input review loop
    # commits approved knowledge into. Reuse the SAME chromadb client and
    # settings as the main vdb — chromadb errors if a single path is opened
    # with two different client configs. Set to None on any failure so the
    # main retrieval path falls back cleanly.
    try:
        from langchain_chroma import Chroma
        from core.gap_detection import VALIDATED_COLLECTION_NAME
        ss.validated_vdb = Chroma(
            collection_name=VALIDATED_COLLECTION_NAME,
            embedding_function=ss.embeddings,
            client=ss.vectorstore_obj._client,
            client_settings=ss.vectorstore_obj._client_settings,
        )
        try:
            _validated_count = ss.validated_vdb._collection.count()
        except Exception:
            _validated_count = 0
        log_message('info', f"Loaded validated collection ({VALIDATED_COLLECTION_NAME}) with {_validated_count} records.")
    except Exception as e:
        log_message('warning', f"Could not open validated collection (will fall back to doc-only retrieval): {e}")
        ss.validated_vdb = None

    # Load BM25 indexes from pickled files (built during ChromaDB creation)
    try:
        from utils.bm25_utils import load_bm25_indexes, build_bm25_index, build_bm25_image_index
        ss.bm25_index, ss.bm25_corpus_docs, ss.bm25_image_index, ss.bm25_image_corpus_docs = load_bm25_indexes(ss.persist_vectordb_dir)

        if ss.bm25_index is not None:
            log_message('info', "BM25 text index loaded from disk.")
            if not silent:
                st.toast("BM25 text index loaded from disk.")
                time.sleep(0.1)
        else:
            # Fallback: build from ChromaDB if pickle not found
            log_message('info', "BM25 text pickle not found, building from ChromaDB...")
            ss.bm25_index, ss.bm25_corpus_docs = build_bm25_index(ss.chroma_collection)
            log_message('info', "BM25 text index built from ChromaDB.")
            if not silent:
                st.toast("BM25 text index built from ChromaDB.")
                time.sleep(0.1)
    except Exception as e:
        log_message('error', f"Loading/building BM25 text index failed: {e}!")
        ss.bm25_index = None
        ss.bm25_corpus_docs = None
        ss.bm25_image_index = None
        ss.bm25_image_corpus_docs = None

    # Load image collection (if exists)
    try:
        ss.image_vdb, ss.image_collection, ss._image_collection_record_count = load_image_collection(
            ss.persist_vectordb_dir, ss.embeddings
        )
        if ss._image_collection_record_count > 0:
            log_message('info', f"Loaded Image Collection with {ss._image_collection_record_count} records.")
            if not silent:
                st.toast(f"Image collection record count: {ss._image_collection_record_count}.")
                time.sleep(0.1)
        else:
            log_message('info', "No image collection found or empty.")
            ss.image_vdb = None
            ss.image_collection = None
    except Exception as e:
        log_message('warning', f"Loading Image Collection failed: {e}")
        ss.image_vdb = None
        ss.image_collection = None
        ss._image_collection_record_count = 0

    # BM25 image index: already loaded from pickle above; fallback if needed
    if ss.bm25_image_index is not None:
        log_message('info', "BM25 image index loaded from disk.")
        if not silent:
            st.toast("BM25 image index loaded from disk.")
            time.sleep(0.1)
    elif getattr(ss, 'image_collection', None) is not None:
        try:
            from utils.bm25_utils import build_bm25_image_index
            ss.bm25_image_index, ss.bm25_image_corpus_docs = build_bm25_image_index(ss.image_collection)
            log_message('info', "BM25 image index built from ChromaDB.")
            if not silent:
                st.toast("BM25 image index built from ChromaDB.")
                time.sleep(0.1)
        except Exception as e:
            log_message('error', f"Building BM25 image index failed: {e}!")
            ss.bm25_image_index = None
            ss.bm25_image_corpus_docs = None
    else:
        ss.bm25_image_index = None
        ss.bm25_image_corpus_docs = None

    ss.app_initialized = True    
#-----------------
# Not used anymore
#-----------------
   
    # try:
    #     ss.conversation_chain_obj = initialize_conversation_chain(ss.qa_chat_model, ss.vectorstore_obj, ss.langchain_chain_name, \
    #                                                               ss.chain_type_name, ss.return_source_docs, ss.num_docs_returned_by_chain, [])
    #     # Debug info
    #     log_message('info', f"Initialized Conversation Chain ({ss.langchain_chain_name}).")
    #     if not silent:
    #         st.toast(f"Initialized Conversation Chain ({ss.langchain_chain_name}).")
    #         time.sleep(0.1)
    # except Exception as e:
    #     log_message('error', f"Initialization of conversation chain ({ss.langchain_chain_name}) failed: {e}!")
    #     st.error("Failed initializing conversation chain: {e}")
    #     st.stop()
        
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model_name = 'sentence-transformers/all-MiniLM-L6-v2'

    try:
        # Pass device directly to constructor to avoid meta tensor copy errors
        # in sentence-transformers 4.x with PyTorch 2.10+
        ss.sentence_transformer_model = SentenceTransformer(model_name, device=device)

        log_message('info', "Initialized SentenceTransformer Model.")

        if not silent:
            st.toast("Initialized SentenceTransformer.")
            time.sleep(0.1)

    except Exception as e:
        log_message('error', f"Initialization of SentenceTransformer failed: {e}!")
        ss.sentence_transformer_model = None
        st.error(f"Failed initializing SentenceTransformer: {e}")
        st.stop()

    # Cross-encoder reranker (CPU — no GPU on BIDA server)
    try:
        from utils.rerank_utils import load_reranker
        from consts.consts import reranker_model_name
        ss.reranker_model = load_reranker(reranker_model_name, device='cpu')
        if ss.reranker_model is not None:
            log_message('info', f"Initialized Reranker ({reranker_model_name}).")
            if not silent:
                st.toast(f"Initialized Reranker ({reranker_model_name.split('/')[-1]}).")
                time.sleep(0.1)
        else:
            log_message('warning', "Reranker unavailable; falling back to fused-score dedup.")
    except Exception as e:
        log_message('error', f"Initialization of reranker failed: {e}!")
        ss.reranker_model = None

#-----------------
# Not used now
#-----------------

    # try:
    #     ss.mongo_client = MongoClient("mongodb://localhost:27017/")
    #     # Debug info
    #     log_message('info', "Initialized Mongo Client.")
    #     if not silent:
    #         st.toast("Initialized Mongo Client.")
    #         time.sleep(0.1)
    # except Exception as e:
    #     log_message('error', f"Initialization of Mongo Client failed: {e}!")
    #     st.error("Failed initializing Mongo Client: {e}")
    #     st.stop()

def init_session_states_and_app_silent():
    
    initialize_session_states()
    init_authentication()
    init_app_settings(silent=True)