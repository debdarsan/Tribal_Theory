import json
import os
from langchain_core.documents import Document
from typing import Iterable
from utils.sys_utils import *
from utils.logging_utils import *


def update_dict(d, u):
    """
    Recursively updates a dictionary with another dictionary.
    
    Args:
        d: The dictionary to update
        u: The dictionary with updates
    
    Returns:
        dict: The updated dictionary
    """
    for k, v in u.items():
        if isinstance(v, dict):
            d[k] = update_dict(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def save_splits_json_file(DIRECTORY, json_file_name, splits, update=False):
    """
    Saves document splits to a JSON file.
    
    Args:
        DIRECTORY: Directory path for the output file
        json_file_name: Name of the JSON file
        splits: List of Document objects to save
        update: If True, merge with existing data (avoiding duplicates)
    """
    try:
        doc_dicts = [{key: value for key, value in doc.__dict__.items()} for doc in splits]

        if not json_file_name.endswith(".json"):
            json_file_name += ".json"
        if update:
            existing_data = load_json_file(DIRECTORY, json_file_name)
            if existing_data:
                existing_data_set = {json.dumps(d) for d in existing_data}
                doc_dicts_set = {json.dumps(d) for d in doc_dicts}

                unique_elements_set = doc_dicts_set - existing_data_set
                unique_elements = [json.loads(s) for s in unique_elements_set]

                existing_data.extend(unique_elements)
                doc_dicts = existing_data

        with open(DIRECTORY + json_file_name, 'w', encoding='utf8') as f:
            json.dump(doc_dicts, f, indent=4)
    except Exception as e:
        log_message('error', f'Error saving splits to JSON file: {e}')
        raise


def load_splits_json_file(DIRECTORY, json_file_name):
    """
    Loads document splits from a JSON file.
    
    Args:
        DIRECTORY: Directory path containing the JSON file
        json_file_name: Name of the JSON file
    
    Returns:
        list: List of Document objects
    """
    try:
        # Load splits from JSON
        if not json_file_name.endswith(".json"):
            json_file_name += ".json"
        with open(DIRECTORY + "/" + json_file_name, 'r', encoding='utf8') as f:
            loaded_doc_dicts = json.load(f)

        # Convert dictionaries to Document objects
        loaded_splits = [Document(**doc_dict) for doc_dict in loaded_doc_dicts]
        return loaded_splits
    except Exception as e:
        log_message('error', f'Error loading splits from JSON file: {e}')
        raise


def save_docs_to_jsonl(array: Iterable[Document], dir, file_name) -> str:
    """
    Saves an iterable of Document objects to a JSONL file.
    
    Args:
        array: Iterable of Document objects
        dir: Directory path for the output file
        file_name: Name of the JSONL file
    
    Returns:
        str: Path to the saved file
    """
    file_name = sanitize_filename(file_name)
    if not file_name.endswith('.jsonl'):
        file_name = file_name + '.jsonl'
    file_path = os.path.join(dir, file_name)
    with open(file_path, 'w') as jsonl_file:
        for doc in array:
            jsonl_file.write(doc.json() + '\n')
    return file_path


def read_docs_from_jsonl(dir, file_name) -> Iterable[Document]:
    """
    Reads Document objects from a JSONL file.
    
    Args:
        dir: Directory path containing the JSONL file
        file_name: Name of the JSONL file
    
    Returns:
        list: List of Document objects
    """
    array = []
    file_name = sanitize_filename(file_name)
    if not file_name.endswith('.jsonl'):
        file_name = file_name + '.jsonl'
    file_path = os.path.join(dir, file_name)
    with open(file_path, 'r') as jsonl_file:
        for line in jsonl_file:
            data = json.loads(line)
            obj = Document(**data)
            array.append(obj)
    return array


def concatenate_docs_page_contents(docs):
    """
    Concatenates the page_content of multiple documents into a single string.
    
    Args:
        docs: List of Document objects
    
    Returns:
        str: Concatenated content with double newlines between documents
    """
    relevant_content = ''
    if docs:
        for doc in docs:
            relevant_content = f"{relevant_content}\n\n{doc.page_content}" if relevant_content else doc.page_content
    return relevant_content


def save_json_file(DIRECTORY, json_file_name, data):
    """
    Saves data to a JSON file.
    
    Args:
        DIRECTORY: Directory path for the output file
        json_file_name: Name of the JSON file
        data: Data to save (must be JSON serializable)
    """
    try:
        # Save data to JSON
        if not json_file_name.endswith(".json"):
            json_file_name += ".json"
        if not DIRECTORY.endswith(os.sep):
            DIRECTORY += os.sep
        with open(DIRECTORY + json_file_name, 'w', encoding='utf8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        log_message('error', f'Error saving data to JSON file: {e}')
        raise


def load_json_file(DIRECTORY, json_file_name):
    """
    Loads data from a JSON file.
    
    Given directory and the json file name (with or without .json extension),
    loads the json file and returns the loaded dictionary (or raises exception if file not found).
    
    Args:
        DIRECTORY: Directory path containing the JSON file
        json_file_name: Name of the JSON file
    
    Returns:
        dict/list: Loaded JSON data
    """
    try:
        if not json_file_name.endswith(".json"):
            json_file_name += ".json"
        with open(DIRECTORY + os.sep + json_file_name, "r", encoding="utf8") as f:
            return json.load(f)
    except Exception as e:
        log_message('error', f"Error Loading JSON {json_file_name}: {e}")
        raise


def load_session_state(ss, json_file_name='session_state.json'):
    """
    Loads session state from a JSON file into a session state object.
    
    Args:
        ss: Session state object (dict-like) to populate
        json_file_name: Name of the JSON file containing saved state
    
    Returns:
        bool: True if loaded successfully
    """
    try:
        with open(json_file_name, 'r') as f:
            saved_state = json.load(f)
    except Exception as e:
        log_message('error', f'Error: {e} - while reading JSON file: {json_file_name}')
        saved_state = {}
        raise

    if saved_state != {}:
        log_message('info', f"Loaded session state from {json_file_name}")
        try:
            # Initialize session state with saved values
            for key, value in saved_state.items():
                ss[key] = value
        except Exception as e:
            log_message('error', f'Error: {e} - while loading session state from JSON file: {json_file_name}')
            raise
    return True  # Return True if no exceptions were raised


def serialize_document(doc):
    """
    Serializes a Document object to a dictionary.
    
    Args:
        doc: Document object or dictionary
    
    Returns:
        dict: Serialized document with page_content and metadata
    """
    if isinstance(doc, Document):
        # Assuming Document has attributes like 'page_content' and 'metadata'
        return {"page_content": doc.page_content, "metadata": doc.metadata}
    else:
        # If it's already a dictionary or a basic data type, return as is
        return doc


def deserialize_document(doc_dict):
    """
    Deserializes a dictionary back to a Document object.
    
    Args:
        doc_dict: Dictionary with page_content and metadata keys
    
    Returns:
        Document: Reconstructed Document object
    """
    return Document(page_content=doc_dict["page_content"], metadata=doc_dict["metadata"])


def save_qa_history(DIRECTORY, json_file_name, qa_history):
    """
    Saves QA history to a JSON file, serializing Document objects.
    
    Args:
        DIRECTORY: Directory path for the output file
        json_file_name: Name of the JSON file
        qa_history: Dictionary with historical_prompts and historical_responses
    """
    try:
        # Convert Document objects in historical_responses to dictionaries
        historical_responses_serializable = []
        for response in qa_history["historical_responses"]:
            if "source_documents" in response:
                serialized_docs = [serialize_document(doc) for doc in response["source_documents"]]
                response = response.copy()  # Create a copy to modify
                response["source_documents"] = serialized_docs
            historical_responses_serializable.append(response)

        qa_history_serializable = {
            "historical_prompts": qa_history["historical_prompts"],
            "historical_responses": historical_responses_serializable
        }
        if not json_file_name.endswith(".json"):
            json_file_name += ".json"
        with open(DIRECTORY + os.sep + json_file_name, 'w', encoding='utf8') as file:
            json.dump(qa_history_serializable, file, indent=4)
        log_message("info", f"QA history saved successfully to: {json_file_name}")
    except Exception as e:
        log_message("info", f"Error saving QA history to: {json_file_name} {e}")


def load_qa_history(DIRECTORY, json_file_name):
    """
    Loads QA history from a JSON file, deserializing Document objects.
    
    Args:
        DIRECTORY: Directory path containing the JSON file
        json_file_name: Name of the JSON file
    
    Returns:
        dict: QA history with historical_prompts and historical_responses,
              or empty structure if file not found
    """
    try:
        if not json_file_name.endswith(".json"):
            json_file_name += ".json"
        with open(DIRECTORY + os.sep + json_file_name, 'r', encoding='utf8') as file:
            qa_history = json.load(file)
        # Convert dictionaries back to Document objects in historical_responses

        for response in qa_history["historical_responses"]:
            if response["greet_flag"] == False:
                if "source_documents" in response:
                    deserialized_docs = [deserialize_document(doc) for doc in response["source_documents"]]
                    response["source_documents"] = deserialized_docs

        formatted_qa_history = [tuple(qa_block) for qa_block in qa_history["historical_responses"][0]["chat_history"]
                                if qa_history["historical_responses"][0]["greet_flag"]]

        qa_history["historical_responses"][0]["chat_history"] = formatted_qa_history
        return qa_history

    except FileNotFoundError:
        log_message("info", f"No existing QA history found at {DIRECTORY + os.sep + json_file_name}. Returning empty.")
        return {"historical_prompts": [], "historical_responses": []}
    except Exception as e:
        log_message("info", f"Error loading QA history from: {json_file_name} {e}")
        return None
