import streamlit as st
from utils.json_utils import *
from utils.logging_utils import *
from utils.sys_utils import *

ss = st.session_state

def initialize_session_states():
    
    try:
        log_message("info", f"Loading session state from session_state.json")
        load_session_state(ss, json_file_name='settings.json')
        
    except Exception as e:
        log_message("info", f"session_state.json not found. Initializing session state.")

    # auth
    if "role" not in ss:
        ss.role = ""
    if "user_name" not in ss:
        ss.user_name = ""
    if "full_name" not in ss:
        ss.full_name = ""
    if "auth_object" not in ss:
        ss.auth_object = None
    if "authentication_status" not in ss:
        ss.authentication_status = None
   
    # UI
    if "custom_page_settings_applied" not in ss:
        ss.custom_page_settings_applied = False
    if "accept_questions" not in ss:
        ss.accept_questions = False
    if "show_appraisal_widgets" not in ss:
        ss.show_appraisal_widgets = False
    if "filter_appraised" not in ss:
        ss.filter_appraised = False

    # Color settings (__ prefix for auto-save to settings.json)
    from consts.consts import COLOR_ELEMENT_DEFAULTS
    for _key, _default in COLOR_ELEMENT_DEFAULTS.items():
        if _key not in ss:
            ss[_key] = _default

    # LLM, Embedding and Vectorestore
    if "llm_provider_name" not in ss:
        ss.llm_provider_name = "OpenAI"
    if "token_limit" not in ss:
        ss.token_limit = 4096
    if "__qa_model_name" not in ss:
        ss.__qa_model_name = "gpt-5.4"
    if "qa_model" not in ss:
        ss.qa_model = None
    if "embedding_model_name" not in ss:
        ss.embedding_model_name = "OpenAIEmbeddings"
    if "splis_generated" not in ss:
        ss.splits_generated = False
    if "vectorstore_type_name" not in ss:
        ss.vectorstore_type_name = "Chroma"  # "FAISS" #"Chroma"
    if "persist_vectordb_dir" not in ss:
        ss.persist_vectordb_dir = ss.vectorstore_type_name + "_VectorStore"
    if "vector_dimension" not in ss:
        ss.vector_dimension = 0
    if "vectorstore_creation_mode" not in ss:
        ss.vectorstore_creation_mode = "Reset"
    if "_vectorstore_record_count" not in ss:
        ss._vectorstore_record_count = 0

    # Conversation Chain
    if "verbose" not in ss:
        ss.verbose = False
        
    if "__enable_qa_emailing" not in ss:
        ss.__qa_emailing_enabled = False
    if "__qa_history_enabled" not in ss:
        ss.__qa_history_enabled = False
    if "__summarize_chat_history" not in ss:
        ss.__summarize_chat_history = True

    if "__max_tokens" not in ss:
        ss.__max_tokens = 1000
    if "__n" not in ss:
        ss.__n = 1
    if "__stop" not in ss:
        ss.__stop = None
    if "__temperature" not in ss:
        ss.__temperature = 0.2
    if "__top_p" not in ss:
        ss.__top_p = 0.1
    if "__frequency_penalty" not in ss:
        ss.__frequency_penalty = 0.1
    if "__presence_penalty" not in ss:
        ss.__presence_penalty = 0.1
    if "__streaming" not in ss:
        ss.__streaming = True
    if "__max_tokens_chat_history" not in ss:
        ss.__max_tokens_chat_history = 1000 
        
    if "langchain_chain_name" not in ss:
        ss.langchain_chain_name = "ConversationalRetrievalChain"

    if "chain_type_name" not in ss:
        ss.chain_type_name = "stuff"
    if "prompt_template" not in ss:
        ss.prompt_template = "Default"
    
    # Chatbot
    if "user_prompt" not in ss:
        ss.user_prompt = ""
    if "retrun_source_docs" not in ss:
        ss.return_source_docs = True
    if "num_docs_returned_by_chain" not in ss:
        ss.num_docs_returned_by_chain = 2

    # auto qa generation
    if "auto_qa_gen_scheme_name" not in ss:
        ss.auto_qa_gen_scheme_name = "ENTIRE_SPLIT"
    if "_autoqa_output_filename" not in ss:
        ss._autoqa_output_filename = ""
    if "temperature_auto_qa" not in ss:
        ss.temperature_auto_qa = 0.3
    if "max_tokens_auto_qa" not in ss:
        ss.max_tokens_auto_qa = 3000

    # embeddings
    if "embeddings" not in ss:
        ss.embeddings = None

    # vector store
    if "vectorstore_obj" not in ss:
        ss.vectorstore_obj = None
    if "existing_ids" not in ss:
        ss.existing_ids = []
    if "chroma_collection" not in ss:
        ss.chroma_collection = None
    # Image collection for enhanced ALT text
    if "image_vdb" not in ss:
        ss.image_vdb = None
    if "image_collection" not in ss:
        ss.image_collection = None
    if "_image_collection_record_count" not in ss:
        ss._image_collection_record_count = 0
    # qa model
    if "qa_chat_model" not in ss:
        ss.qa_chat_model = None
    if "sentence_transformer_model" not in ss:
        ss.sentence_transformer_model = None
    if "reranker_model" not in ss:
        ss.reranker_model = None

    if "mongo_client" not in ss:
        ss.mongo_client = None
        
    # chatbot
    if "_user_prompt" not in ss:
        ss._user_prompt = ""
    if "qa_history" not in ss:
        ss.qa_history = {
            "historical_prompts": [],
            "historical_responses": [],
        }
    if "chat_history" not in ss:
        ss.chat_history = []
    if "conversation_chain_obj" not in ss:
        ss.conversation_chain_obj = None
    if "_qa_filename" not in ss:
        ss._qa_filename = ""
    if 'zip_requested' not in ss:
        ss.zip_requested = False
    if 'user_chat_history_names' not in ss:
        ss.user_chat_history_names = []
    if '__summarize_chat_history' not in ss:
        ss.__summarize_chat_history = True
