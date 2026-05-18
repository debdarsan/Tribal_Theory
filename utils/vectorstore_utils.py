import os
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_chroma import Chroma
import chromadb
from chromadb import Settings
from consts.sys_consts import *
from consts.vdb_consts import *
from utils.logging_utils import *
from utils.json_utils import *
import pandas as pd
import uuid

MAX_TOKENS_PER_BATCH = 300000  # Default value, can be overridden


def set_max_tokens_per_batch(value):
    """Set the MAX_TOKENS_PER_BATCH value for embedding batches."""
    global MAX_TOKENS_PER_BATCH
    MAX_TOKENS_PER_BATCH = value
    log_message('info', f'MAX_TOKENS_PER_BATCH set to {value}')


def does_chroma_vectorstore_exist(vdb) -> bool:
    """
    Checks if Chroma vectorstore exists
    """
    record_count = vdb._collection.count()
    if record_count > 0:
        return True
    return False


def define_embeddings(EMBEDDINGS_MODEL_NAME):
    """
    Instantiate embedding model based on the model name.
    Supports OpenAI and HuggingFace embeddings.
    """
    embeddings = None
    try:
        match EMBEDDINGS_MODEL_NAME:
            case "OpenAIEmbeddings":
                embeddings = OpenAIEmbeddings()
                log_message("info", f"Instatiating Embedding Model {EMBEDDINGS_MODEL_NAME}.")
            case "all-MiniLM-L6-v2":
                embeddings = HuggingFaceEmbeddings(model_name=EMBEDDINGS_MODEL_NAME)
                log_message("info", f"def define_embeddings(EMBEDDINGS_MODEL_NAME): \
                            Instatiating Embedding Model {EMBEDDINGS_MODEL_NAME}.")
            case _default:
                log_message("info", f"def define_embeddings(EMBEDDINGS_MODEL_NAME):\
                             Embedding Model {EMBEDDINGS_MODEL_NAME} not supported!",)
        return embeddings
    except Exception as e:
        log_message("error", f"def define_embeddings(EMBEDDINGS_MODEL_NAME): Error {e}!")
        raise


def add_docs_to_chroma_vdb(vdb, embeddings, PERSIST_VECTORDB_DIR, CHROMA_SETTINGS, chroma_client, docs, existing_ids, collection_name=None):
    """
    Add documents to Chroma VDB with batching support based on token counts.

    A unique UUID is generated for each document by using the uuid.uuid5() function,
    which creates a UUID using the SHA-1 hash of a namespace identifier and a name
    string (in this case, the content of the document).

    This approach is more practical than generating IDs using URLs or other document metadata,
    as it directly prevents the addition of duplicate documents based on content rather than
    relying on metadata or manual checks.

    Args:
        collection_name: Optional name for the collection. If None, uses TEXT_COLLECTION_NAME.
    """
    if collection_name is None:
        collection_name = TEXT_COLLECTION_NAME
    added_new_docs_count = 0

    try:
        # Create a list of unique ids for each document based on the content
        ids = [str(uuid.uuid5(uuid.NAMESPACE_DNS, doc.page_content)) for doc in docs]
        unique_ids = list(set(ids))  # Remove duplicates to maintain unique IDs

    except Exception as e:
        log_message("error", f"An error occurred in generating unique ids: {e}")
        raise

    # Ensure that only docs that correspond to unique ids are kept and that
    # only one of the duplicate ids is kept
    # The if condition in the list comprehension checks whether the ID of the
    # current document exists in the seen_ids set:
    # > If it doesn't exist, this implies the document is unique. It gets added to
    # seen_ids using seen_ids.add(id), and the document gets included in unique_docs.
    # > If it does exist, the document is a duplicate and gets ignored.
    # The "or True" at the end is necessary to always return a 'true'' value to the
    # if condition, because seen_ids.add(id) returns None (which is 'false')
    # even when an element is successfully added.

    unique_docs = []

    for doc, id in zip(docs, ids):
        if id not in existing_ids:
            existing_ids.append(id)  # Use append for list instead of add
            unique_docs.append(doc)  # Add unique doc to the list

    if unique_docs == []:
        return vdb, existing_ids, added_new_docs_count, 0

    else:
        # Batch documents based on token count to avoid exceeding limits
        global MAX_TOKENS_PER_BATCH
        batches = []
        batch_docs = []
        token_sum = 0

        for doc in unique_docs:
            doc_tokens = doc.metadata.get("Tokens", 0)

            if doc_tokens > 0 and token_sum + doc_tokens > MAX_TOKENS_PER_BATCH:
                if batch_docs:
                    batches.append(batch_docs)
                # Start a new batch
                batch_docs = [doc]
                token_sum = doc_tokens
            else:
                batch_docs.append(doc)
                token_sum += doc_tokens

        # Add last batch
        if batch_docs:
            batches.append(batch_docs)

        try:
            unique_id_pointer = 0
            for i, batch in enumerate(batches):
                if i == 0:
                    unique_id_pointer = len(batch)
                    vdb = Chroma.from_documents(
                        batch,
                        embeddings,
                        ids=unique_ids[0:unique_id_pointer],
                        collection_name=collection_name,
                        persist_directory=PERSIST_VECTORDB_DIR,
                        client_settings=CHROMA_SETTINGS,
                        client=chroma_client,
                    )
                    added_new_docs_count += len(batch)
                    record_count = vdb._collection.count()
                    log_message("info", f"Added {len(batch)} documents to the Chroma vectorstore.")
                    log_message("info", f"Current record count in Chroma vectorstore: {record_count}.")
                else:
                    unique_id_pointer += len(batch)
                    vdb.add_documents(
                        batch,
                        ids=unique_ids[unique_id_pointer - len(batch):unique_id_pointer],
                        persist_directory=PERSIST_VECTORDB_DIR,
                        client_settings=CHROMA_SETTINGS,
                        client=chroma_client,
                    )
                    added_new_docs_count += len(batch)
                    record_count = vdb._collection.count()
                    log_message("info", f"Added {len(batch)} documents to the Chroma vectorstore.")
                    log_message("info", f"Current record count in Chroma vectorstore: {record_count}.")

            return vdb, existing_ids, added_new_docs_count, record_count

        except Exception as e:
            log_message("error", f"An error occurred in the Chroma client initiation: {e}")
            raise


def convert_collection_to_dataframe(collection):
    """
    Convert a Chroma collection to a pandas DataFrame.
    Assuming collection is a dictionary with keys 'ids', 'embeddings', and 'documents'.
    """
    try:
        data = collection.get(include=["documents", "metadatas", "embeddings"])
        df = pd.DataFrame(
            {
                "IDs": collection["ids"],
                "Documents": collection["documents"],
                "Metadata": collection["metadatas"],  # This is a dictionary of metadata
                "Embeddings": collection["embeddings"],
            }
        )
        return df

    except Exception as e:
        log_message("error", f"An error occurred in processing the collection: {e}")
        raise


def create_vectorstore(VECTORSTORE_TYPE, PERSIST_VECTORDB_DIR, docs, embeddings, creation_mode, text_collection_name=None):
    """
    Create a vectorstore of the specified type (FAISS or Chroma).

    Args:
        VECTORSTORE_TYPE: Type of vectorstore ("Chroma" or "FAISS")
        PERSIST_VECTORDB_DIR: Directory to persist the vectorstore
        docs: List of documents to add
        embeddings: Embedding model to use
        creation_mode: "Reset" to clear and recreate, "Append" to add to existing
        text_collection_name: Name for the text collection (defaults to TEXT_COLLECTION_NAME)

    Returns:
        vdb: The vectorstore object
        collection: The Chroma collection (None for FAISS)
        existing_ids: List of existing document IDs
        record_count: Number of records in the vectorstore
        rejected_docs_count: Number of duplicate documents rejected
    """
    # Use default collection name if not provided
    if text_collection_name is None:
        text_collection_name = TEXT_COLLECTION_NAME
    vdb = None
    collection = None
    record_count = 0
    rejected_docs_count = 0
    # define an empty list of ids
    existing_ids = []

    match VECTORSTORE_TYPE:
        case "FAISS":
            # The ability to add documents to an existing FAISS db is not provided
            # This can be implemented by using the following code:
            # faiss_vdb1.merge_from(faiss_vdb2)
            try:
                vdb = FAISS.from_documents(docs, embeddings)
                # Check if the directory exists, create it if it doesn't
                if not os.path.exists(PERSIST_VECTORDB_DIR):
                    os.makedirs(PERSIST_VECTORDB_DIR)
                vdb.save_local(PERSIST_VECTORDB_DIR, VECTORSTORE_NAME)
                # Get the record count of the FAISS index
                record_count = vdb.index.ntotal
                log_message("info", "FAISS vectorstore created with record count: " + str(record_count))
            except Exception as e:
                log_message("error", f"Creating FAISS vectorstore failed: {e}!")
                raise

        case "Chroma":
            try:
                log_message("info", f"Inside create_vectorstore.... About to create Chroma vectorstore.",)
                # Define the Chroma settings
                CHROMA_SETTINGS = Settings(
                    persist_directory=PERSIST_VECTORDB_DIR,
                    # Prevent anonymous data collection by Chroma
                    anonymized_telemetry=False,
                )
                chroma_client = chromadb.PersistentClient(
                    settings=CHROMA_SETTINGS,
                    path=PERSIST_VECTORDB_DIR,
                )
                # define Chroma Vector DB
                vdb = Chroma(
                    collection_name=text_collection_name,
                    persist_directory=PERSIST_VECTORDB_DIR,
                    embedding_function=embeddings,
                    client_settings=CHROMA_SETTINGS,
                    client=chroma_client,
                )
                if does_chroma_vectorstore_exist(vdb):
                    log_message("info", f"... Existing VDB at directory: {PERSIST_VECTORDB_DIR}")
                    log_message("info", f"Instantiating Chroma Vector DB... ")
                    log_message("info", f"... Existing VDB at directory: {PERSIST_VECTORDB_DIR}, record count: {vdb._collection.count()}",)
                    if creation_mode == "Reset":
                        log_message("info", f"Resetting Chroma vectorstore at directory: {PERSIST_VECTORDB_DIR}")
                        chroma_client.delete_collection(vdb._collection.name)
                        vdb_status_str = "R E S E T"
                    else:
                        # Collect all the document ids from the existing Chroma VDB
                        existing_ids = [str(id) for id in vdb._collection.get()["ids"]]
                        vdb_status_str = "E X I S T I N G"
                else:
                    log_message("info", f"... Empty VDB at directory: {PERSIST_VECTORDB_DIR}, record count: {vdb._collection.count()}",)
                    vdb_status_str = "N E W"

                input_doc_count = len(docs)
                log_message("info", f"Attempting to add {input_doc_count} documents to the '{vdb_status_str}' VDB. May take a minute...",)
                (vdb, existing_ids, added_new_docs_count, record_count) = add_docs_to_chroma_vdb(
                    vdb, embeddings, PERSIST_VECTORDB_DIR, CHROMA_SETTINGS, chroma_client, docs, existing_ids,
                    collection_name=text_collection_name
                )

                rejected_docs_count = input_doc_count - added_new_docs_count
                if added_new_docs_count > 0:
                    log_message("info", f"... Added {added_new_docs_count} 'N E W' docs to '{vdb_status_str}'\
                                 Chroma VDB at directory: {PERSIST_VECTORDB_DIR}, record count: {vdb._collection.count()}",)
                else:
                    log_message("info", f"... No new docs added to '{vdb_status_str}' Chroma VDB at directory:\
                                 {PERSIST_VECTORDB_DIR}, record count: {vdb._collection.count()}",)

                log_message("info", f"... Rejected {rejected_docs_count} 'D U P L I C A T E' docs",)

                # Change the default collection name 'langchain' to the configured VECTORSTORE_NAME
                if vdb._LANGCHAIN_DEFAULT_COLLECTION_NAME != VECTORSTORE_NAME:
                    vdb._LANGCHAIN_DEFAULT_COLLECTION_NAME = VECTORSTORE_NAME

                collection = vdb._collection
                log_message("info", f"Inside create_vectorstore.... Chroma vectorstore created.")
            except Exception as e:
                log_message("error", f"Creating Chroma vectorstore failed: {e}!")
                raise

        case _default:
            log_message("info", f"Vectorstore {VECTORSTORE_TYPE} is not supported!")
            exit

    return vdb, collection, existing_ids, record_count, rejected_docs_count


def load_vectorstore(VECTORSTORE_TYPE, PERSIST_VECTORDB_DIR, embeddings):
    """
    Load an existing vectorstore of the specified type (FAISS or Chroma).
    
    Returns:
        vdb: The vectorstore object
        collection: The Chroma collection (None for FAISS)
        existing_ids: List of existing document IDs
        record_count: Number of records in the vectorstore
    """
    vdb = None
    collection = None
    record_count = 0
    # define an empty list of ids
    existing_ids = []

    match VECTORSTORE_TYPE:
        case "FAISS":
            try:
                log_message("info", f"Loading Vectorstore (type: {VECTORSTORE_TYPE}) from file {VECTORSTORE_NAME}.")
                vdb = FAISS.load_local(
                    PERSIST_VECTORDB_DIR, embeddings, VECTORSTORE_NAME
                )
                record_count = vdb.index.ntotal

            except Exception as e:
                log_message("error", f"Loading Vectorstore (type: {VECTORSTORE_TYPE}) error: {e}!")
                raise

        case "Chroma":
            # Define the Chroma settings
            CHROMA_SETTINGS = Settings(
                persist_directory=PERSIST_VECTORDB_DIR,
                # Prevent anonymous data collection by Chroma
                anonymized_telemetry=False,
            )
            chroma_client = chromadb.PersistentClient(
                settings=CHROMA_SETTINGS, path=PERSIST_VECTORDB_DIR
            )
            vdb = Chroma(
                collection_name=TEXT_COLLECTION_NAME,
                persist_directory=PERSIST_VECTORDB_DIR,
                embedding_function=embeddings,
                client_settings=CHROMA_SETTINGS,
                client=chroma_client,
            )
            try:
                log_message("info", "Checking if Chroma Vector DB exists... ")
                if does_chroma_vectorstore_exist(vdb):
                    # Update and store locally vectorstore
                    log_message("info", f"... Existing VDB at directory: {PERSIST_VECTORDB_DIR}")
                    existing_ids = [str(id) for id in vdb._collection.get()["ids"]]
                    log_message("info", f"... Existing VDB at directory: {PERSIST_VECTORDB_DIR}, record count: {vdb._collection.count()}",)
                    collection = vdb._collection
                    record_count = vdb._collection.count()
                    log_message("info", f"Inside load_vectorstore: Chroma vectorstore_obj._collection.count(): {record_count}.",)
                else:
                    log_message("info", f"... New Chroma VDB is to be created at directory: {PERSIST_VECTORDB_DIR}",)
            except Exception as e:
                log_message("error", f"Loading Vectorstore (type: {VECTORSTORE_TYPE}) error: {e}!",)
                raise

        case _:
            log_message("info", f"Vectorstore {VECTORSTORE_TYPE} not supported!")
            raise ValueError(f"Vectorstore {VECTORSTORE_TYPE} not supported!")

    return vdb, collection, existing_ids, record_count


def create_image_collection(persist_dir, image_metadata_list, embeddings, creation_mode, image_collection_name=None,
                            use_summaries_for_search=False):
    """
    Create or update the image collection with enhanced ALT text documents.

    Args:
        persist_dir: Directory to persist the Chroma database
        image_metadata_list: List of image metadata dictionaries with enhanced_alt_text
        embeddings: Embedding model to use
        creation_mode: "Reset" to clear and recreate, "Append" to add to existing
        image_collection_name: Name for the image collection (defaults to IMAGE_COLLECTION_NAME)
        use_summaries_for_search: If True and summaries exist in metadata, build page_content
            from preceding_summary + qualitative_ocr + following_summary for embeddings.
            When False (default), uses raw preceding_text + qualitative_ocr + following_text.
            Metadata always stores raw preceding_text and following_text for display.

    Returns:
        image_vdb: The Chroma vectorstore for images
        image_collection: The underlying Chroma collection
        record_count: Number of records in the collection
    """
    from langchain_core.documents import Document

    # Use default collection name if not provided
    if image_collection_name is None:
        image_collection_name = IMAGE_COLLECTION_NAME

    if not image_metadata_list:
        log_message("warning", "No image metadata provided for image collection.")
        return None, None, 0

    log_message("info", f"Creating image collection with {len(image_metadata_list)} images...")

    try:
        # Define Chroma settings
        CHROMA_SETTINGS = Settings(
            persist_directory=persist_dir,
            anonymized_telemetry=False,
        )

        chroma_client = chromadb.PersistentClient(
            settings=CHROMA_SETTINGS,
            path=persist_dir,
        )

        # Check if image collection exists
        existing_collections = chroma_client.list_collections()

        if image_collection_name in existing_collections:
            if creation_mode == "Reset":
                log_message("info", f"Resetting image collection: {image_collection_name}")
                chroma_client.delete_collection(image_collection_name)
            else:
                log_message("info", f"Appending to existing image collection: {image_collection_name}")

        # Create Document objects from image metadata
        # page_content uses summaries or raw text depending on use_summaries_for_search
        # Raw text always kept in metadata for display
        documents = []
        for img_meta in image_metadata_list:
            # Determine which text to use for page_content (search embeddings)
            if use_summaries_for_search and "preceding_summary" in img_meta and "following_summary" in img_meta:
                page_content = " ".join(filter(None, [
                    img_meta.get("preceding_summary", ""),
                    img_meta.get("qualitative_ocr", ""),
                    img_meta.get("following_summary", ""),
                ]))
            else:
                page_content = " ".join(filter(None, [
                    img_meta.get("preceding_text", ""),
                    img_meta.get("qualitative_ocr", ""),
                    img_meta.get("following_text", ""),
                ]))
            doc = Document(
                page_content=page_content,
                metadata={
                    "static_url": img_meta.get("static_url", ""),
                    "source_doc": img_meta.get("source_doc", ""),
                    "position": img_meta.get("position", 0),
                    "qualitative_ocr": img_meta.get("qualitative_ocr", ""),
                    "preceding_text": img_meta.get("preceding_text", ""),  # Raw text for display
                    "following_text": img_meta.get("following_text", ""),  # Raw text for display
                    "image_path": img_meta.get("image_path", ""),
                    "collection_type": "image"  # Mark as image collection document
                }
            )
            documents.append(doc)

        # Generate unique IDs based on content
        ids = [str(uuid.uuid5(uuid.NAMESPACE_DNS, doc.page_content)) for doc in documents]

        # Create the image collection
        image_vdb = Chroma.from_documents(
            documents,
            embeddings,
            ids=ids,
            collection_name=image_collection_name,
            persist_directory=persist_dir,
            client_settings=CHROMA_SETTINGS,
            client=chroma_client,
        )

        image_collection = image_vdb._collection
        record_count = image_collection.count()

        log_message("info", f"Image collection created with {record_count} records.")

        return image_vdb, image_collection, record_count

    except Exception as e:
        log_message("error", f"Error creating image collection: {e}")
        raise


def load_image_collection(persist_dir, embeddings):
    """
    Load the existing image collection for querying.

    Args:
        persist_dir: Directory where Chroma database is persisted
        embeddings: Embedding model to use

    Returns:
        image_vdb: The Chroma vectorstore for images (or None if not found)
        image_collection: The underlying Chroma collection (or None if not found)
        record_count: Number of records in the collection
    """
    try:
        CHROMA_SETTINGS = Settings(
            persist_directory=persist_dir,
            anonymized_telemetry=False,
        )

        chroma_client = chromadb.PersistentClient(
            settings=CHROMA_SETTINGS,
            path=persist_dir,
        )

        # Check if image collection exists
        existing_collections = chroma_client.list_collections()

        if IMAGE_COLLECTION_NAME not in existing_collections:
            log_message("warning", f"Image collection '{IMAGE_COLLECTION_NAME}' not found.")
            return None, None, 0

        # Load the image collection
        image_vdb = Chroma(
            collection_name=IMAGE_COLLECTION_NAME,
            persist_directory=persist_dir,
            embedding_function=embeddings,
            client_settings=CHROMA_SETTINGS,
            client=chroma_client,
        )

        image_collection = image_vdb._collection
        record_count = image_collection.count()

        log_message("info", f"Loaded image collection with {record_count} records.")

        return image_vdb, image_collection, record_count

    except Exception as e:
        log_message("error", f"Error loading image collection: {e}")
        return None, None, 0


def load_text_collection(persist_dir, embeddings):
    """
    Load the text collection (main document collection) for querying.
    This is a wrapper around the existing load_vectorstore for consistency.

    Args:
        persist_dir: Directory where Chroma database is persisted
        embeddings: Embedding model to use

    Returns:
        text_vdb: The Chroma vectorstore for text
        text_collection: The underlying Chroma collection
        existing_ids: List of existing document IDs
        record_count: Number of records in the collection
    """
    return load_vectorstore("Chroma", persist_dir, embeddings)
