import os
import re
import glob
import copy
from typing import List
from datetime import datetime
from utils.date_time_utils import *
from consts.sys_consts import *
from utils.json_utils import *
from utils.logging_utils import *
from utils.sys_utils import *
from transformers import GPT2Tokenizer

from langchain_community.document_loaders import (
    PyMuPDFLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
    UnstructuredWordDocumentLoader,
)

from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    MarkdownHeaderTextSplitter,
)
from langchain_core.documents import Document

tokenizer = GPT2Tokenizer.from_pretrained("EleutherAI/gpt-neo-2.7B")

USER_NAME = "deb"
MAX_TOKENS = 1000  # Default value, can be overridden


def set_max_tokens(value):
    """Set the MAX_TOKENS value for document splitting."""
    global MAX_TOKENS
    MAX_TOKENS = value
    log_message('info', f'MAX_TOKENS set to {value}')


def replace_html_tables_with_placeholder(markdown_content, mapping_file_path):
    # Regular expression to find HTML table tags
    table_pattern = re.compile(r'<table.*?>.*?</table>', re.DOTALL)

    # Find all matches of the table pattern in the content
    table_matches = re.finditer(table_pattern, markdown_content)

    # Create a mapping of placeholders to actual tables
    table_mapping = {}
    placeholder_index = 1

    for match in table_matches:
        table_content = match.group(0)
        placeholder = f'__TABLE_PLACEHOLDER_{placeholder_index}__'
        table_mapping[placeholder] = table_content
        placeholder_index += 1

    # Save the mapping to a JSON file
    with open(mapping_file_path, 'w') as mapping_file:
        json.dump(table_mapping, mapping_file, indent=2)

    # Replace tables with placeholders in the Markdown content
    for placeholder, table_content in table_mapping.items():
        markdown_content = markdown_content.replace(table_content, placeholder)

    return markdown_content

def replace_table_placeholders_with_html_in_splits(split, mapping_file_path):
    # Load the mapping from the JSON file
    with open(mapping_file_path, 'r') as mapping_file:
        table_mapping = json.load(mapping_file)

    for placeholder, table_content in table_mapping.items():
        split.page_content = split.page_content.replace(placeholder, table_content)
        text_token_count = get_text_token_count(split.page_content, tokenizer)
        split.metadata["Tokens"] = text_token_count

    return split

def remove_line_with_html_links(markdown_content):
    """
    Remove any line in the Markdown content that contains an HTML <a> link.

    This function scans the text for lines that include an anchor tag
    (e.g., <a href="...">text</a>) and deletes the entire line, including
    the trailing newline, so no blank lines are left behind.

    Parameters
    ----------
    markdown_content : str
        The Markdown text that may contain embedded HTML links.

    Returns
    -------
    str
        The Markdown content with all lines containing HTML <a> tags removed.

    Raises
    ------
    Exception
        Any exception encountered during processing is logged and re-raised.

    Notes
    -----
    - The regex matches:
        .*              → the full line before and after the link
        <a href="...">  → the HTML anchor element
        .*?</a>         → anchor text inside the tag
        (\n|\r\n)?      → optional trailing newline (removed as well)
    """

    try:
        # Remove any line containing an HTML link (<a href="...">...</a>)
        # The entire line is deleted rather than just the link fragment.
        markdown_content = re.sub(
            r'.*<a href=".*?">.*?<\/a>.*(\n|\r\n)?',
            '',
            markdown_content
        )
        return markdown_content

    except Exception as e:
        # Log and re-raise the exception to allow upstream handling
        log_message('error', f'Error in remove_line_with_html_links: {e}')
        raise


def get_text_token_count(text, tokenizer):
    return len(tokenizer(text)["input_ids"])


def get_metadata_token_count(metadata, tokenizer):
    metadata_str = " ".join([f"{key}: {value}" for key, value in metadata.items()])
    return len(tokenizer(metadata_str)["input_ids"])


def split_text_into_chunks_by_sentence(text, max_token_limit, tokenizer):
    log_message("info", "Starting sentence splitting...")

    # Temporarily replace periods within $...$ with a placeholder
    text = re.sub(
        r"(?<!\$)(\$(?:[^\$]*\$\$[^\$]*)*?[^\$]*)(\.)(?![^\$]*\$)",
        r"\1TEMP_DOT\2",
        text,
    )

    text = re.sub(
        r'<img([^>]*)alt=\'([^\']*)\'([^>]*)>',
        lambda match: match.group(0).replace('.', 'TEMP_DOT'),
        text,
    )

    log_message("info", text)
    log_message("info", "\n\n\n\n\n\n\n")
    # Split the text into sentences
    log_message("info", "Splitting text into sentences...")
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())

    # Restore the periods within $...$
    sentences = [re.sub("TEMP_DOT", ".", s) for s in sentences]

    log_message("info", f"Number of sentences found: {len(sentences)}")

    chunks = []
    current_chunk = []
    current_token_count = 0
    last_sentence = str()
    last_sentence_tokens = 0

    for idx, sentence in enumerate(sentences):
        log_message("info", f"Processing sentence {idx+1}...")
        sentence_token_count = len(tokenizer.tokenize(sentence))
        log_message("info", f"Token count for sentence: {sentence_token_count}")

        if current_token_count + sentence_token_count <= max_token_limit:
            log_message("info", "Adding sentence to current chunk.")
            current_chunk.append(sentence)
            current_token_count += sentence_token_count
            log_message("info", "Current chunk token count: " + str(current_token_count))

        else:
            if sentence_token_count <= max_token_limit:
                log_message("info", "Saving current chunk and starting new chunk.")

                chunks.append(" ".join(current_chunk))
                current_chunk = [last_sentence, sentence]

                last_sentence_tokens = len(tokenizer.tokenize(last_sentence))
                last_sentence = sentence
                current_token_count = sentence_token_count + last_sentence_tokens

            else:
                log_message("info",f"Warning: The following sentence exceeds max_token_limit ({max_token_limit}) with {sentence_token_count} tokens:",)
                log_message("info", sentence[:50] + "..." if len(sentence) > 50 else sentence)

                if current_chunk:
                    log_message("info", "Saving current chunk.")
                    chunks.append(" ".join(current_chunk))

                log_message("info", "Adding the long sentence as a separate chunk.")
                chunks.append(sentence)

                current_chunk = []
                current_token_count = 0

        last_sentence = sentence
        last_sentence_tokens = len(tokenizer.tokenize(last_sentence))

    if current_chunk:
        log_message("info", "Saving the final chunk.")
        chunks.append(" ".join(current_chunk))

    log_message("info", "Sentence splitting completed.")
    return chunks, sentences  # Return both chunks and sentences


def split_md_using_MarkdownHeaderTextSplitter(md_file):

    headers_to_split_on = [
    ("#", "Section"),
    ("##", "Subsection"),
    ("###", "Subsubsection"),
    ("####", "Subsubsubsection"),
    ("**", "Emphasis"),]

    # MD splits
    try:
        markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
        with open(md_file, 'r', encoding='utf-8') as f:
            md_document_content = f.read()

    except Exception as e:
        log_message('error', f'Could not initiate Header text Splitter: {e}')
        raise


    # Better to remove the TOC from the MD file
    # Otherwise, the whole TOC will be added to the split
    # In the case, where the splitting is done by sentence-wise,
    # the split will be larger than the max_tokens
    md_document_content = remove_line_with_html_links(md_document_content)
    _, filename_without_extension, _ = extract_filename(md_file)
    md_document_content = replace_html_tables_with_placeholder(md_document_content, f"./{TABLE_DATA_DIR}/{filename_without_extension}.json")

    log_message("info", "Splitting started: Inside split_md_using_MarkdownHeaderTextSplitter...")
    log_message("info", "Splitting file: " + md_file)

    try:
        md_header_splits = markdown_splitter.split_text(md_document_content)
    except Exception as e:
        log_message('error', f'Error in markdown_splitter.split_text operation: {e}')
        raise

    # Initialize a variable to keep track of the split number
    split_index = 1
    new_md_header_splits = []
    # Adding file_name to the metadata of each split
    for original_split_index, split in enumerate(md_header_splits):
        try:
            metadata = split.metadata  # Assume metadata is accessible as a property

            _, filename_without_extension, _ = extract_filename(md_file)

            metadata['File'] = filename_without_extension

            if "Emphasis" not in metadata:
                metadata['Emphasis'] = ""
            else:
                if metadata['Emphasis']:
                    split.page_content = metadata['Emphasis'] + ". " + split.page_content

            if "Subsubsubsection" not in metadata:
                metadata['Subsubsubsection'] = ""
            else:
                if metadata['Subsubsubsection']:
                    split.page_content = metadata['Subsubsubsection'] + ", " + split.page_content

            if "Subsubsection" not in metadata:
                metadata['Subsubsection'] = ""
            else:
                if metadata['Subsubsection']:
                    split.page_content = metadata['Subsubsection'] + ", " + split.page_content

            if "Subsection" not in metadata:
                metadata['Subsection'] = ""
            else:
                if metadata['Subsection']:
                    split.page_content = metadata['Subsection'] + ", " + split.page_content

            if "Section" not in metadata:
                metadata['Section'] = ""
            else:
                if metadata['Section']:
                    split.page_content = metadata['Section'] + ", " + split.page_content

            split.page_content = "Context: " + filename_without_extension + ", " + split.page_content
        except Exception as e:
            log_message('error', f'Error in processing metadata: {e}')
            raise

        try:
            text_token_count = get_text_token_count(split.page_content, tokenizer)
            metadata["Tokens"] = text_token_count
            # page_number is always 1 for MD files
            # since we are unable to map the docx page number to the MD file
            metadata["Page"] = 1  # Add the page number to the metadata
            metadata["Split"] = split_index  # Add the split_index to the metadata
            metadata["Uploaded_Date"] = get_date_time_stamp()  # Add the date_time to the metadata
            metadata["Uploader"] = USER_NAME  # Add the user_name to the metadata
            log_message("info", "")
            log_message("info", "**********************************************")
            log_message("info", f"Original split index: {original_split_index + 1}")
            log_message("info", "**********************************************")
            log_message("info", "Split: " + str(split_index) + " of size: " + str(text_token_count))
            chunk_size = MAX_TOKENS - get_metadata_token_count(metadata, tokenizer)

            if chunk_size <= 0:
                raise ValueError(f"Metadata token count exceeds {MAX_TOKENS}")

        except Exception as e:
            log_message('error', f'Error in processing metadata: {e}')
            raise

        try:
            if text_token_count > chunk_size:
                log_message("info",f"Text token count {text_token_count} exceeds limit:\
                            {MAX_TOKENS}.Splitting text into smaller chunks")
                # split_texts = split_text_into_chunks_by_token(split.page_content, chunk_size, tokenizer)
                split_texts, _ = split_text_into_chunks_by_sentence(
                    split.page_content, chunk_size, tokenizer
                )
                log_message("info", "Created " + str(len(split_texts)) + " chunks")
                log_message("info", "----------------------------------------------")
                for new_split_index, new_text in enumerate(split_texts):
                    try:
                        new_md_split = copy.deepcopy(split)
                        new_md_split.page_content = new_text
                        new_md_split.metadata = metadata.copy()
                        token_count = get_text_token_count(new_text, tokenizer)
                        new_md_split.metadata["Tokens"] = token_count
                        new_md_split.metadata["Split"] = split_index
                        new_md_split = replace_table_placeholders_with_html_in_splits(new_md_split, f"{TABLE_DATA_DIR}/{filename_without_extension}.json")
                        new_md_header_splits.append(new_md_split)
                        log_message("info",f"New split created with split_index: {split_index} and tokens count: {token_count}")
                        split_index += 1
                    except Exception as e:
                        log_message('error', f'Error in processing split out of limit: {e}')
            else:
                log_message("info",f"Text token count {text_token_count} within limit: {MAX_TOKENS}")
                new_md_split = copy.deepcopy(split)
                new_md_split.metadata = metadata.copy()
                new_md_split = replace_table_placeholders_with_html_in_splits(new_md_split, f"{TABLE_DATA_DIR}/{filename_without_extension}.json")
                new_md_header_splits.append(new_md_split)
                log_message("info", f"Split added with split_index: {split_index}")
                split_index += 1

        except Exception as e:
            log_message('error', f'Error in text splitting: {e}')
            raise
    log_message("info", "Splitting completed")
    return new_md_header_splits



class MyMarkdownHeaderTextSplitter:
    def __init__(self, file_path, **args):
        # Initialization code here
        self.file_path = file_path
        pass

    def load(self):
        # Code to perform the actual loading or transformation here
        return split_md_using_MarkdownHeaderTextSplitter(self.file_path)


class MyRecursiveCharacterTextSplitter:
    def __init__(self, documents, chunk_size, overlap_size, **args):
        self.documents = documents
        self.chunk_size = chunk_size
        self.overlap_size = overlap_size

    def load(self):
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.overlap_size,
            length_function=len,
        )
        splits = text_splitter.split_documents(self.documents)
        return splits


LOADER_MAPPING_BASED_ON_LANGCHAIN_LOADER_TYPE = {
    "UnstructuredWordDocumentLoader": {
        "extensions": [".docx", ".doc"],
        "loader": (UnstructuredWordDocumentLoader, {}),
    },
    "MarkdownHeaderAndCharacterSplitter": {
        "extensions": [".md"],
        "loader": [
            (MyMarkdownHeaderTextSplitter, {}),
            (
                MyRecursiveCharacterTextSplitter,
                {"chunk_size": 2000, "overlap_size": 50},
            ),
            # Add more stages to the pipeline as needed
        ],
    },
    "MyMarkdownHeaderTextSplitter": {
        "extensions": [".md"],
        "loader": (MyMarkdownHeaderTextSplitter, {}),
    },
    "UnstructuredMarkdownLoader": {
        "extensions": [".md"],
        "loader": (UnstructuredMarkdownLoader, {}),
    },
    "PyMuPDFLoader": {"extensions": [".pdf"], "loader": (PyMuPDFLoader, {})},
    "TextLoader": {
        "extensions": [".txt"],
        "loader": (TextLoader, {"encoding": "utf8"}),
    },
    # Add more mappings for other file extensions and loaders as needed
}

# Define the mapping of LOADER_TYPE to a three-letter key
LOADER_TYPE_TO_KEY = {
    "UnstructuredWordDocumentLoader": "UWD",
    "MarkdownHeaderAndCharacterSplitter": "MHC",
    "MyMarkdownHeaderTextSplitter": "MMH",
    "UnstructuredMarkdownLoader": "UMD",
    "PyMuPDFLoader": "PMP",
    "TextLoader": "TXT",
}


def select_loader(ext: str, LOADER_TYPE: str):
    for key, loader_info in LOADER_MAPPING_BASED_ON_LANGCHAIN_LOADER_TYPE.items():
        if key == LOADER_TYPE and ext in loader_info["extensions"]:
            return loader_info["loader"]
    raise ValueError(
        f"No loader found for extension: {ext} and loader_name: {LOADER_TYPE}"
    )


def load_single_document_based_on_langchain_loader_type(
    file_path: str, LOADER_TYPE: str
) -> List[Document]:
    log_message("info", f"Loading document using loader type {LOADER_TYPE}")
    ext = "." + file_path.rsplit(".", 1)[-1]
    loaders = select_loader(ext, LOADER_TYPE)
    if isinstance(loaders, list):  # If a pipeline of loaders
        documents = file_path
        for loader_class, loader_args in loaders:
            loader = loader_class(documents, **loader_args)
            documents = loader.load()
        return documents
    else:  # If a single loader
        loader_class, loader_args = loaders
        loader = loader_class(file_path, **loader_args)
        return loader.load()


def load_documents_based_on_langchain_loader_type(
    INGESTION_DIRECTORY,
    LOADER_TYPE,
    save_splits_filewise,
    data_directory,
    ignored_files: List[str] = [],
    progress_callback=None,
) -> List[Document]:
    """
    Loads all documents from the source documents directory, ignoring specified files
    """
    all_files = []
    processed_files_info = []  # This list will hold the information for the JSON file
    for (
        loader_key,
        loader_info,
    ) in LOADER_MAPPING_BASED_ON_LANGCHAIN_LOADER_TYPE.items():
        if LOADER_TYPE == loader_key:
            extensions = loader_info["extensions"]
            for ext in extensions:
                all_files.extend(
                    glob.glob(
                        os.path.join(INGESTION_DIRECTORY, f"**/*{ext}"), recursive=True
                    )
                )
    filtered_files = [
        file_path for file_path in all_files if file_path not in ignored_files
    ]
    results = []
    total_files = len(filtered_files)
    for index, file_path in enumerate(filtered_files):
        ext = "." + file_path.rsplit(".", 1)[-1]
        filename = file_path.split(".")[0].split("\\")[-1]
        docs = load_single_document_based_on_langchain_loader_type(
            file_path, LOADER_TYPE
        )
        date_time = datetime.now()
        formatted_date_time = date_time.strftime("%d-%b-%Y:%I%p:%M:%S")
        if progress_callback:
            progress_callback(index + 1, total_files, file_path)
        if save_splits_filewise:
            file_formatted_date_time = formatted_date_time.replace("-", "_").replace(":", "_")
            splits_file_name = f"splits_{filename}_{file_formatted_date_time}.json"
            save_splits_json_file(data_directory, splits_file_name, docs)
        results.extend(docs)
        # Collecting the information to save to JSON
        date_time = datetime.now()
        formatted_date_time = date_time.strftime("%d-%b-%Y:%I%p:%M:%S")
        processed_files_info.append(
            {"ext": ext, "file_path": file_path, "date_time": formatted_date_time}
        )
    return results, processed_files_info


def process_documents_based_on_langchain_loader_type(
    INGESTION_DIRECTORY,
    LOADER_TYPE,
    data_directory,
    save_splits_filewise,
    ignored_files: List[str] = [],
    progress_callback=None,
) -> List[Document]:
    """
    Load documents and split in chunks
    """
    log_message("info", f"Loading documents from {INGESTION_DIRECTORY}")
    documents, processed_files_info = load_documents_based_on_langchain_loader_type(
        INGESTION_DIRECTORY,
        LOADER_TYPE,
        save_splits_filewise,
        data_directory,
        ignored_files,
        progress_callback=progress_callback,
    )
    return documents, processed_files_info
