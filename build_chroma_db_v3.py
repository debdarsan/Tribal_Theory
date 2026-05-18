import streamlit as st
import os
import shutil
import sys
import json
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

# Set page config first
st.set_page_config(
    page_title="BIDA Chroma DB Builder",
    page_icon=None,
    layout="wide"
)

# ── Summarization Flags ──────────────────────────────────────────────────────
# SUMMARIZE_PRE_FOL_TEXTS_BIDA_TEXT:
#   When True, GPT-4o summarizes preceding/following text for the enhanced_alt_text
#   stored in <img alt='...'> in BIDA_texts.
#   When False (default), raw preceding/following text is used (current behavior).
#
# SUMMARIZE_PRE_FOL_TEXTS_BIDA_IMAGE:
#   When True, GPT-4o summarizes preceding/following text for page_content
#   (search embeddings) in BIDA_images. Metadata always keeps raw text for display.
#   When False (default), raw preceding/following text is used for page_content.
# ──────────────────────────────────────────────────────────────────────────────
SUMMARIZE_PRE_FOL_TEXTS_BIDA_TEXT = False
SUMMARIZE_PRE_FOL_TEXTS_BIDA_IMAGE = False

# Settings file path
SETTINGS_FILE = "chroma_db_settings.json"

# Default settings
DEFAULT_SETTINGS = {
    "text_collection_name": "BIDA_texts",
    "image_collection_name": "BIDA_images",
    "document_source_folder": "DocumentSource",
    "chroma_db_directory": "Chroma_VectorStore",
    "loader_type": "MyMarkdownHeaderTextSplitter",
    "vectorstore_type": "Chroma",
    "embedding_model": "OpenAIEmbeddings",
    "creation_mode": "Reset",
    "correct_formatting": True,
    "process_image": True,
    "format_toc": True,
    "use_enhanced_alt_text": True,
    "max_tokens": 1000,
    "max_tokens_per_batch": 300000,
    "max_image_height": 300,
    "ignore_image_size_kb": 10,
    "summarize_pre_fol_texts_bida_text": False,
    "summarize_pre_fol_texts_bida_image": False
}


def load_settings():
    """Load settings from JSON file, return defaults if file doesn't exist."""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                # Merge with defaults to handle any missing keys
                return {**DEFAULT_SETTINGS, **settings}
    except Exception as e:
        st.warning(f"Could not load settings: {e}. Using defaults.")
    return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    """Save settings to JSON file."""
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4)
        return True
    except Exception as e:
        st.error(f"Could not save settings: {e}")
        return False


# Force reimport of critical modules to ensure fresh code is loaded
# This is necessary when source files are modified while Streamlit is running
import importlib
import sys

def force_reimport_modules():
    """Force reimport of critical modules to pick up any source code changes."""
    modules_to_reload = [
        'utils.vectorstore_utils',
        'utils.docx2md_utils',
        'utils.vision_utils',
        'utils.loader_utils',
        'utils.alt_text_utils',
    ]
    for mod_name in modules_to_reload:
        if mod_name in sys.modules:
            try:
                importlib.reload(sys.modules[mod_name])
            except Exception:
                pass  # Ignore reload errors

# Force reimport on module load
force_reimport_modules()

# Import application modules
from utils.docx2md_utils import docx2md, generate_alt_text, generate_enhanced_alt_text
from utils.loader_utils import process_documents_based_on_langchain_loader_type, set_max_tokens
from utils.vectorstore_utils import define_embeddings, create_vectorstore, set_max_tokens_per_batch, create_image_collection
from utils.logging_utils import log_message
from utils.bm25_utils import build_bm25_index, build_bm25_image_index, save_bm25_indexes
from utils.json_utils import save_splits_json_file, load_splits_json_file
from utils.sys_utils import set_directories
from utils.acronym_utils import process_acronyms_from_folder
from utils.vision_utils import VisionMetrics
# Note: CHROMADB_DIR is now read from settings (chroma_db_directory)
from consts.conv_consts import set_max_image_height, set_ignore_image_size_kb
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# List of directories to delete when RESET_OUTPUT_DIRS is True
DIRS_TO_DELETE = [
    "Acronyms",
    "Chroma_VectorStore",
    "Conversion",
    "data",
    "Debug",
    "Ingestion",
    "static",
    "table_data",
    "text_block_data"
]

def reset_output_directories(dirs_to_delete, status_placeholder):
    """Delete output directories to start fresh"""
    import time
    import gc

    messages = []
    for d in dirs_to_delete:
        if os.path.isdir(d):
            # Try up to 3 times with delay for locked files
            for attempt in range(3):
                try:
                    gc.collect()  # Force garbage collection to release file handles
                    shutil.rmtree(d)
                    messages.append(f"[OK] Deleted directory: {d}")
                    break
                except PermissionError as e:
                    if attempt < 2:
                        time.sleep(1)  # Wait 1 second before retry
                    else:
                        messages.append(f"[FAIL] Failed to delete {d}: {e} (close other Python processes)")
                except Exception as e:
                    messages.append(f"[FAIL] Failed to delete {d}: {e}")
                    break
        else:
            messages.append(f"[SKIP] Directory not found (skipped): {d}")
    return messages

def delete_pycache_folders():
    """Recursively delete all __pycache__ folders"""
    messages = []
    for root, dirs, files in os.walk(".", topdown=False):
        for name in dirs:
            if name == "__pycache__":
                path = os.path.join(root, name)
                try:
                    shutil.rmtree(path)
                    messages.append(f"[OK] Deleted __pycache__: {path}")
                except Exception as e:
                    messages.append(f"[FAIL] Failed to delete {path}: {e}")
    return messages

def get_docx_files(folder):
    """Get list of .docx files in the folder"""
    if not os.path.exists(folder):
        return []
    return [f for f in os.listdir(folder) if f.endswith('.docx')]


def write_execution_log(logs, log_file="execution_log.txt"):
    """Write execution logs to a file (rewrite mode)"""
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            for log_entry in logs:
                f.write(log_entry + "\n")
        return True
    except Exception as e:
        print(f"Failed to write log file: {e}")
        return False

def main():
    st.title("BIDA Chroma DB Builder")
    st.markdown("---")

    # Load settings from file
    settings = load_settings()

    # Sidebar for configuration
    with st.sidebar:
        st.header("Configuration")

        st.subheader("Build Mode")
        build_mode_options = ["Reset", "Append"]
        build_mode = st.selectbox("Mode",
                                  options=build_mode_options,
                                  index=build_mode_options.index(settings.get("build_mode", "Reset")),
                                  help="Reset: Delete all output directories and create fresh VectorDB. Append: Keep existing data and add new documents only.")

        # Derive flags from build_mode
        reset_output_dirs = (build_mode == "Reset")
        creation_mode = build_mode  # Pass same value to vectorstore creation

        st.markdown("---")
        st.subheader("Process Options")
        run_docx2md = st.checkbox("Run DOCX to MD Conversion", value=True,
                                  help="Convert .docx files to markdown and generate alt text")
        extract_acronyms = st.checkbox("Extract Acronyms", value=True,
                                       help="Extract acronyms and their meanings to BIDA-Acronyms.csv")
        generate_splits = st.checkbox("Generate Splits", value=True,
                                      help="Generate document splits for vectorization")
        generate_vdb = st.checkbox("Generate VectorDB", value=True,
                                   help="Create/update the Chroma vector database")

        st.markdown("---")
        st.subheader("Collection Names")
        text_collection_name = st.text_input("Text Collection Name",
                                              value=settings.get("text_collection_name", "BIDA_texts"),
                                              help="Name for the text/document collection in ChromaDB")
        image_collection_name = st.text_input("Image Collection Name",
                                               value=settings.get("image_collection_name", "BIDA_images"),
                                               help="Name for the image collection in ChromaDB")

        st.markdown("---")
        st.subheader("Directories")

        chroma_db_directory = st.text_input("ChromaDB Directory",
                                            value=settings.get("chroma_db_directory", "Chroma_VectorStore"),
                                            help="Directory to store the ChromaDB vector database")
        docx_folder = st.text_input("Document Source Folder",
                                    value=settings.get("document_source_folder", "DocumentSource"))

        loader_options = ["MyMarkdownHeaderTextSplitter", "UnstructuredMarkdownLoader"]
        loader_type = st.selectbox("Loader Type",
                                   options=loader_options,
                                   index=loader_options.index(settings.get("loader_type", "MyMarkdownHeaderTextSplitter")))

        vectorstore_options = ["Chroma", "FAISS"]
        vectorstore_type = st.selectbox("VectorStore Type",
                                        options=vectorstore_options,
                                        index=vectorstore_options.index(settings.get("vectorstore_type", "Chroma")))

        embedding_options = ["OpenAIEmbeddings"]
        embedding_model = st.selectbox("Embedding Model",
                                       options=embedding_options,
                                       index=embedding_options.index(settings.get("embedding_model", "OpenAIEmbeddings")))

        st.markdown("---")
        st.subheader("Formatting Options")
        correct_formatting = st.checkbox("Correct Formatting",
                                         value=settings.get("correct_formatting", True))
        process_image = st.checkbox("Process Images",
                                    value=settings.get("process_image", True))
        format_toc = st.checkbox("Format TOC",
                                 value=settings.get("format_toc", True))
        use_enhanced_alt_text = st.checkbox("Enhanced ALT Text (GPT-4o Vision)",
                                            value=settings.get("use_enhanced_alt_text", True),
                                            help="Use GPT-4o Vision for qualitative OCR on screenshots. Creates separate image collection.")

        st.markdown("---")
        st.subheader("Summarization Options")
        summarize_bida_text = st.checkbox("Summarize for BIDA_texts",
                                          value=settings.get("summarize_pre_fol_texts_bida_text", SUMMARIZE_PRE_FOL_TEXTS_BIDA_TEXT),
                                          help="When enabled, GPT-4o summarizes preceding/following text for the enhanced_alt_text in <img alt='...'> (BIDA_texts). When disabled, raw text is used.")
        summarize_bida_image = st.checkbox("Summarize for BIDA_images",
                                           value=settings.get("summarize_pre_fol_texts_bida_image", SUMMARIZE_PRE_FOL_TEXTS_BIDA_IMAGE),
                                           help="When enabled, GPT-4o summarizes preceding/following text for page_content (search embeddings) in BIDA_images. Metadata always keeps raw text for display.")

        st.markdown("---")
        st.subheader("Processing Parameters")
        max_tokens = st.number_input("Max Tokens per Split",
                                     value=settings.get("max_tokens", 1000),
                                     min_value=100, max_value=5000, step=100,
                                     help="Maximum tokens per document split")
        max_tokens_per_batch = st.number_input("Max Tokens per Batch",
                                               value=settings.get("max_tokens_per_batch", 300000),
                                               min_value=10000, max_value=1000000, step=10000,
                                               help="Maximum tokens per embedding batch")
        max_image_height = st.number_input("Max Image Height (px)",
                                           value=settings.get("max_image_height", 300),
                                           min_value=100, max_value=1000, step=50,
                                           help="Maximum image height in pixels")
        ignore_image_size_kb = st.number_input("Ignore Image Size (KB)",
                                               value=settings.get("ignore_image_size_kb", 10),
                                               min_value=1, max_value=100, step=1,
                                               help="Skip images smaller than this size")

    # Main content area
    col1, col2 = st.columns([2, 1])

    with col1:
        st.header("Source Documents")
        docx_files = get_docx_files(docx_folder)

        if docx_files:
            st.success(f"Found {len(docx_files)} .docx file(s) in '{docx_folder}'")
            with st.expander("View files", expanded=True):
                for f in docx_files:
                    st.write(f"- {f}")
        else:
            st.warning(f"No .docx files found in '{docx_folder}'. Please add documents to process.")

    with col2:
        st.header("Status")

        # Check OpenAI API Key
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            st.success("OpenAI API Key loaded")
        else:
            st.error("OpenAI API Key not found in .env")

        # Check if VectorDB exists
        if os.path.exists(chroma_db_directory):
            st.info(f"Existing VectorDB found at '{chroma_db_directory}'")
        else:
            st.info("No existing VectorDB")

    st.markdown("---")

    # Process summary
    st.header("Process Summary")

    # Show build mode
    if build_mode == "Reset":
        st.info("**Mode: RESET** - All output directories will be deleted. Fresh VectorDB will be created.")
    else:
        st.info("**Mode: APPEND** - Existing data preserved. Only new documents will be added to VectorDB.")

    # Show summarization flags
    if summarize_bida_text or summarize_bida_image:
        summ_parts = []
        if summarize_bida_text:
            summ_parts.append("BIDA_texts (alt text)")
        if summarize_bida_image:
            summ_parts.append("BIDA_images (search embeddings)")
        st.info(f"**Summarization enabled for:** {', '.join(summ_parts)}")

    process_steps = []
    step_num = 1
    if reset_output_dirs:
        process_steps.append(f"{step_num}. Reset output directories")
        step_num += 1
    if run_docx2md:
        process_steps.append(f"{step_num}. Convert DOCX to Markdown & generate alt text")
        step_num += 1
    if extract_acronyms:
        process_steps.append(f"{step_num}. Extract acronyms to CSV")
        step_num += 1
    if generate_splits:
        process_steps.append(f"{step_num}. Generate document splits")
        step_num += 1
    if generate_vdb:
        process_steps.append(f"{step_num}. Build Chroma VectorDB ({build_mode} mode)")
        step_num += 1
        process_steps.append(f"{step_num}. Build BM25 indexes")
        step_num += 1

    if process_steps:
        for step in process_steps:
            st.write(step)
    else:
        st.warning("No process steps selected!")

    st.markdown("---")

    # Run button
    if st.button("Build Chroma DB", type="primary", use_container_width=True):
        if not docx_files and run_docx2md:
            st.error("No .docx files to process!")
            return

        if not api_key and generate_vdb:
            st.error("OpenAI API Key required for VectorDB generation!")
            return

        # Save current settings to file before building
        current_settings = {
            "text_collection_name": text_collection_name,
            "image_collection_name": image_collection_name,
            "document_source_folder": docx_folder,
            "chroma_db_directory": chroma_db_directory,
            "loader_type": loader_type,
            "vectorstore_type": vectorstore_type,
            "embedding_model": embedding_model,
            "creation_mode": creation_mode,
            "correct_formatting": correct_formatting,
            "process_image": process_image,
            "format_toc": format_toc,
            "use_enhanced_alt_text": use_enhanced_alt_text,
            "max_tokens": max_tokens,
            "max_tokens_per_batch": max_tokens_per_batch,
            "max_image_height": max_image_height,
            "ignore_image_size_kb": ignore_image_size_kb,
            "summarize_pre_fol_texts_bida_text": summarize_bida_text,
            "summarize_pre_fol_texts_bida_image": summarize_bida_image
        }
        save_settings(current_settings)

        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        log_container = st.container()

        # generate_vdb counts as 2 steps: VDB build + BM25 index build
        total_steps = sum([reset_output_dirs, run_docx2md, extract_acronyms, generate_splits]) + (2 if generate_vdb else 0)
        current_step = 0

        with log_container:
            st.subheader("Execution Log")
            log_area = st.empty()
            logs = []
            acronym_count = 0  # Initialize acronym count

            try:
                # Log build mode
                logs.append(f"### Build Mode: {build_mode.upper()}")
                if build_mode == "Reset":
                    logs.append("All output directories will be deleted. Fresh VectorDB will be created.")
                else:
                    logs.append("Existing data preserved. Only new documents will be added.")
                log_area.markdown("\n\n".join(logs))

                # Log summarization settings
                logs.append(f"[OK] Summarization: BIDA_texts={summarize_bida_text}, BIDA_images={summarize_bida_image}")

                # Set processing parameters from UI
                set_max_tokens(max_tokens)
                set_max_tokens_per_batch(max_tokens_per_batch)
                set_max_image_height(max_image_height)
                set_ignore_image_size_kb(ignore_image_size_kb)
                logs.append(f"[OK] Parameters set: max_tokens={max_tokens}, max_tokens_per_batch={max_tokens_per_batch}, max_image_height={max_image_height}, ignore_image_size_kb={ignore_image_size_kb}")
                log_area.markdown("\n\n".join(logs))

                # Step 1: Reset directories
                if reset_output_dirs:
                    status_text.text("Resetting output directories...")
                    logs.append("### Step 1: Reset Output Directories")

                    reset_msgs = reset_output_directories(DIRS_TO_DELETE, status_text)
                    logs.extend(reset_msgs)

                    pycache_msgs = delete_pycache_folders()
                    logs.extend(pycache_msgs)

                    logs.append("[OK] Directory cleanup completed")
                    log_area.markdown("\n\n".join(logs))

                    current_step += 1
                    progress_bar.progress(current_step / total_steps)

                # Initialize directories
                status_text.text("Initializing directories...")
                (
                    DOC_SOURCE_DIRECTORY,
                    CONVERSION_DIRECTORY,
                    INGESTION_DIRECTORY,
                    DEBUG_DIRECTORY,
                    DATA_DIRECTORY,
                    TABLE_DATA_DIRECTORY,
                ) = set_directories()
                logs.append("[OK] Directories initialized")
                log_area.markdown("\n\n".join(logs))

                # Step 2: DOCX to MD conversion
                all_image_metadata = []  # Collect image metadata for image collection
                accumulated_vision_metrics = VisionMetrics()  # Track total API usage

                if run_docx2md:
                    status_text.text("Converting documents...")
                    logs.append("### Step 2: DOCX to Markdown Conversion")

                    for idx, filename in enumerate(docx_files):
                        logs.append(f"Processing: {filename} ...")
                        log_area.markdown("\n\n".join(logs))

                        complete_docx_path = os.path.join(docx_folder, filename)
                        markdown_content, markdown_output_file_name = docx2md(
                            DEBUG_DIRECTORY,
                            CONVERSION_DIRECTORY,
                            INGESTION_DIRECTORY,
                            correct_formatting,
                            process_image,
                            format_toc,
                            complete_docx_path,
                            is_temp_file=False,
                        )

                        # Use enhanced or standard alt text generation
                        if use_enhanced_alt_text:
                            logs[-1] = f"Processing (enhanced ALT): {filename} ..."
                            log_area.markdown("\n\n".join(logs))
                            source_doc_name = os.path.splitext(filename)[0]

                            # Create a progress callback to update the UI with metrics
                            image_progress_placeholder = st.empty()
                            metrics_placeholder = st.empty()

                            def update_image_progress(total, processed, current_name, metrics):
                                if total > 0:
                                    image_progress_placeholder.text(
                                        f"   GPT-4o Vision: {processed}/{total} images processed"
                                        + (f" - Current: {current_name}" if current_name and processed < total else "")
                                    )
                                    if metrics and metrics.total_tokens > 0:
                                        metrics_placeholder.text(
                                            f"   Tokens: {metrics.total_tokens:,} | Time: {metrics.total_time_seconds:.1f}s | Cost: ${metrics.estimated_cost:.4f}"
                                        )

                            updated_markdown_content, image_metadata_list, doc_metrics = generate_enhanced_alt_text(
                                markdown_content, markdown_output_file_name, source_doc_name,
                                progress_callback=update_image_progress,
                                summarize_for_bida_text=summarize_bida_text,
                                summarize_for_bida_image=summarize_bida_image
                            )

                            # Clear the progress placeholders after completion
                            image_progress_placeholder.empty()
                            metrics_placeholder.empty()

                            # Accumulate metrics across all documents
                            accumulated_vision_metrics.total_input_tokens += doc_metrics.total_input_tokens
                            accumulated_vision_metrics.total_output_tokens += doc_metrics.total_output_tokens
                            accumulated_vision_metrics.total_time_seconds += doc_metrics.total_time_seconds
                            accumulated_vision_metrics.api_calls += doc_metrics.api_calls
                            accumulated_vision_metrics.images_processed += doc_metrics.images_processed

                            all_image_metadata.extend(image_metadata_list)
                            logs[-1] = f"[OK] Converted (enhanced): {filename} - {len(image_metadata_list)} images processed"
                        else:
                            updated_markdown_content = generate_alt_text(markdown_content, markdown_output_file_name)
                            logs[-1] = f"[OK] Converted: {filename}"

                        log_area.markdown("\n\n".join(logs))

                    logs.append("[OK] Document conversion completed")
                    if use_enhanced_alt_text:
                        logs.append(f"   Total images processed with GPT-4o Vision: {len(all_image_metadata)}")
                        logs.append(f"   **GPT-4o Vision API Usage:**")
                        logs.append(f"   - Total Time: {accumulated_vision_metrics.total_time_seconds:.1f} seconds")
                        logs.append(f"   - Total Tokens: {accumulated_vision_metrics.total_tokens:,} (Input: {accumulated_vision_metrics.total_input_tokens:,}, Output: {accumulated_vision_metrics.total_output_tokens:,})")
                        logs.append(f"   - API Calls: {accumulated_vision_metrics.api_calls}")
                        logs.append(f"   - Estimated Cost: ${accumulated_vision_metrics.estimated_cost:.4f}")
                    log_area.markdown("\n\n".join(logs))

                    current_step += 1
                    progress_bar.progress(current_step / total_steps)

                # Step: Extract acronyms
                if extract_acronyms:
                    status_text.text("Extracting acronyms...")
                    logs.append("### Extract Acronyms")
                    log_area.markdown("\n\n".join(logs))

                    # Use Acronyms folder for output, reset based on reset_output_dirs flag
                    output_dir = os.path.join(os.getcwd(), "Acronyms")
                    os.makedirs(output_dir, exist_ok=True)

                    # Extract from markdown files in Ingestion directory
                    acronym_csv_path, acronym_count = process_acronyms_from_folder(
                        INGESTION_DIRECTORY,
                        output_dir,
                        reset=reset_output_dirs
                    )

                    if acronym_csv_path:
                        logs.append(f"   Found {acronym_count} acronyms")
                        logs.append(f"   Saved to: {acronym_csv_path}")
                    else:
                        logs.append("   No acronyms found")

                    logs.append("[OK] Acronym extraction completed")
                    log_area.markdown("\n\n".join(logs))

                    current_step += 1
                    progress_bar.progress(current_step / total_steps)

                # Step: Generate splits
                if generate_splits:
                    status_text.text("Generating splits...")
                    logs.append("### Step 3: Generate Document Splits")
                    log_area.markdown("\n\n".join(logs))

                    splits, processed_files_info = process_documents_based_on_langchain_loader_type(
                        INGESTION_DIRECTORY,
                        loader_type,
                        ignored_files=[],
                        save_splits_filewise=True,
                        data_directory=DATA_DIRECTORY
                    )

                    logs.append(f"   Generated {len(splits)} document splits")
                    save_splits_json_file(DATA_DIRECTORY, "splits", splits)
                    logs.append(f"   Saved splits to: {DATA_DIRECTORY}splits.json")
                    logs.append("[OK] Split generation completed")
                    log_area.markdown("\n\n".join(logs))

                    current_step += 1
                    progress_bar.progress(current_step / total_steps)

                # Step 4: Generate VectorDB
                if generate_vdb:
                    status_text.text("Building VectorDB...")
                    logs.append("### Step 4: Build Chroma VectorDB")
                    log_area.markdown("\n\n".join(logs))

                    splits = load_splits_json_file(DATA_DIRECTORY, "splits")
                    logs.append(f"   Loaded {len(splits)} splits from JSON")

                    embeddings = define_embeddings(embedding_model)
                    logs.append(f"   Loaded {embedding_model} embedding model")
                    log_area.markdown("\n\n".join(logs))

                    persist_vectordb_dir = chroma_db_directory
                    vectorstore_obj, chroma_collection, existing_ids, _vectorstore_record_count, rejected_record_count = create_vectorstore(
                        vectorstore_type,
                        persist_vectordb_dir,
                        splits,
                        embeddings,
                        creation_mode,
                        text_collection_name=text_collection_name
                    )

                    logs.append(f"   VectorDB created at: {persist_vectordb_dir}")
                    logs.append(f"   Total records: {_vectorstore_record_count}")
                    logs.append(f"   Rejected duplicates: {rejected_record_count}")
                    logs.append("[OK] VectorDB build completed")
                    log_area.markdown("\n\n".join(logs))

                    # Create image collection if enhanced alt text was used
                    if use_enhanced_alt_text and all_image_metadata:
                        logs.append("### Step 5: Build Image Collection")
                        log_area.markdown("\n\n".join(logs))

                        image_vdb, image_collection, image_record_count = create_image_collection(
                            persist_vectordb_dir,
                            all_image_metadata,
                            embeddings,
                            creation_mode,
                            image_collection_name=image_collection_name,
                            use_summaries_for_search=summarize_bida_image
                        )

                        logs.append(f"   Image collection created at: {persist_vectordb_dir}")
                        logs.append(f"   Image records: {image_record_count}")
                        if summarize_bida_image:
                            logs.append("   Image page_content: using summarized text for search embeddings")
                        else:
                            logs.append("   Image page_content: using raw text for search embeddings")
                        logs.append("[OK] Image collection build completed")
                        log_area.markdown("\n\n".join(logs))

                    # Step 6: Build and persist BM25 indexes
                    logs.append("### Step 6: Build BM25 Indexes")
                    log_area.markdown("\n\n".join(logs))

                    bm25_index, bm25_corpus_docs = build_bm25_index(chroma_collection)
                    logs.append(f"   BM25 text index built ({len(bm25_corpus_docs)} documents)")
                    log_area.markdown("\n\n".join(logs))

                    bm25_image_index, bm25_image_corpus_docs = None, None
                    if use_enhanced_alt_text and all_image_metadata:
                        bm25_image_index, bm25_image_corpus_docs = build_bm25_image_index(image_collection)
                        logs.append(f"   BM25 image index built ({len(bm25_image_corpus_docs)} documents)")
                        log_area.markdown("\n\n".join(logs))

                    save_bm25_indexes(persist_vectordb_dir, bm25_index, bm25_corpus_docs, bm25_image_index, bm25_image_corpus_docs)
                    logs.append("[OK] BM25 indexes saved to disk")
                    log_area.markdown("\n\n".join(logs))

                    current_step += 1
                    progress_bar.progress(current_step / total_steps)

                # Completion
                progress_bar.progress(1.0)
                status_text.text("Build completed successfully!")
                st.success("Chroma DB build completed successfully!")

                # Write execution log to file
                logs.append("[OK] Build completed successfully")
                write_execution_log(logs)
                logs.append(f"[OK] Execution log saved to: execution_log.txt")
                log_area.markdown("\n\n".join(logs))

                # Show summary
                st.subheader("Build Summary")
                summary_col1, summary_col2, summary_col3, summary_col4, summary_col5, summary_col6 = st.columns(6)
                with summary_col1:
                    st.metric("Documents Processed", len(docx_files) if run_docx2md else 0)
                with summary_col2:
                    if extract_acronyms:
                        st.metric("Acronyms Extracted", acronym_count)
                with summary_col3:
                    if generate_splits:
                        st.metric("Splits Generated", len(splits))
                with summary_col4:
                    if generate_vdb:
                        st.metric("VectorDB Records", _vectorstore_record_count)
                with summary_col5:
                    if use_enhanced_alt_text and all_image_metadata:
                        st.metric("Image Records", len(all_image_metadata))
                with summary_col6:
                    if use_enhanced_alt_text and accumulated_vision_metrics.api_calls > 0:
                        st.metric("Vision API Cost", f"${accumulated_vision_metrics.estimated_cost:.4f}")

            except Exception as e:
                st.error(f"Error during build: {str(e)}")
                logs.append(f"[ERROR]: {str(e)}")
                write_execution_log(logs)
                log_area.markdown("\n\n".join(logs))
                raise e

if __name__ == "__main__":
    main()
