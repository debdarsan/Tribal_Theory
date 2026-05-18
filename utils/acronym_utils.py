import re
import os
import csv
import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient
from utils.logging_utils import log_message
from consts.consts import ACRONYM_CSV

ACRONYM_CSV_FILE = "BIDA-Acronyms.csv"


def get_acronyms(source_text):
    """
    Finds acronyms in text - words that are 2+ uppercase letters.
    Returns a list of unique acronyms found in the source text.
    """
    if source_text:
        # Regex to find acronyms (Assuming acronyms are all caps, at least 2 letters)
        acronyms = re.findall(r'\b[A-Z]{2,}\b', source_text)
        return list(set(acronyms))
    return []


def find_acronyms_in_text(text):
    """
    Finds acronyms in text - words that are 2+ uppercase letters.
    Returns a set of unique acronyms.
    """
    pattern = r'\b([A-Z]{2,})\b'
    matches = re.findall(pattern, text)
    return set(matches)


def get_acronym_meaning_with_context_by_google_search(acronym, context):
    """
    Searches Google for the meaning of an acronym within a specific context.
    
    Args:
        acronym: The acronym to search for
        context: The context/domain for the search (e.g., "telecommunications")
    
    Returns:
        str or None: The meaning found, or None if not found
    """
    search_query = f"{acronym} meaning in {context}"
    search_url = f"https://www.google.com/search?q={search_query}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    response = requests.get(search_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    meaning = None
    for g in soup.find_all(class_='BNeawe s3v9rd AP7Wnd'):
        text = g.get_text()
        if acronym in text:
            meaning = text
            break
    
    return meaning


def get_acronyms_meaning_from_mongodb(file_name, acronyms, enclose_in_parentheses):
    """
    Retrieves acronym meanings from MongoDB database.
    
    Args:
        file_name: The document/file name to look up acronyms for
        acronyms: List of acronyms to find meanings for
        enclose_in_parentheses: If True, wrap output in parentheses
    
    Returns:
        str: Formatted string with acronym meanings
    """
    client = MongoClient("mongodb://localhost:27017/")
    db = client.acronyms
    acronyms_collection = db.acronyms

    document = acronyms_collection.find_one({"file_name": file_name})
    additional_info = ""

    if document:
        for acronym in acronyms:
            if acronym in document["acronyms"]:
                meaning = document["acronyms"][acronym]
                if enclose_in_parentheses:
                    additional_info += f"\n({acronym} stands for {meaning})"
                else:
                    additional_info += f"\n{acronym} stands for {meaning}"
            else:
                if enclose_in_parentheses:
                    additional_info += f"\n(Meaning of the {acronym} is not defined in the document)"
                else:
                    additional_info += f"\nMeaning of {acronym} is not defined in the document"

    return additional_info


def read_acronyms_from_csv(csv_file_path):
    """
    Reads acronyms and their meanings from a CSV file.
    
    Args:
        csv_file_path: Path to the CSV file
    
    Returns:
        dict: Dictionary mapping acronyms to their meanings
    """
    with open(csv_file_path, mode='r', encoding='utf-8') as file:
        reader = csv.reader(file)
        next(reader)  # Skip the header row
        return {rows[0]: rows[1] for rows in reader}


def integrate_acronym_meaning_in_response(
    acronyms, 
    enclose_in_parentheses=True,
    context='',
    csv_file_path=ACRONYM_CSV,
    method="from_csv", 
    source_document_name="NR Static Simulations",
):
    """
    Integrates acronym meanings into a response using the specified method.
    
    Args:
        acronyms: List of acronyms to look up
        enclose_in_parentheses: If True, wrap meanings in parentheses
        context: Context for Google search method
        csv_file_path: Path to CSV file for CSV method
        method: One of "from_csv", "google_search", or "from_mongodb"
        source_document_name: Document name for MongoDB method
    
    Returns:
        str: Formatted string with acronym meanings
    """
    additional_info = ""

    if method == "from_csv":
        acronym_meanings = read_acronyms_from_csv(csv_file_path)
        for acronym in acronyms:
            meaning = acronym_meanings.get(acronym, "Not defined")
            if enclose_in_parentheses:
                additional_info += f"\n({acronym} stands for {meaning})"
            else:
                additional_info += f"\n{acronym} stands for {meaning}"

    elif method == "google_search":
        for acronym in acronyms:
            meaning = get_acronym_meaning_with_context_by_google_search(acronym, context)
            if meaning:
                # Append the meaning at the end of the response or modify as needed
                additional_info += f"\n({acronym} stands for {meaning})"

    elif method == "from_mongodb":
        additional_info = get_acronyms_meaning_from_mongodb(source_document_name, acronyms, enclose_in_parentheses)

    return additional_info


def extract_acronyms_from_markdown(md_file_path):
    """
    Extracts acronyms from a markdown file.
    
    Args:
        md_file_path: Path to the markdown file
    
    Returns:
        list: List of tuples [(acronym, meaning, document_name), ...]
    """
    document_name = os.path.basename(md_file_path).replace('.md', '.docx')

    with open(md_file_path, 'r', encoding='utf-8') as f:
        text = f.read()

    acronyms = find_acronyms_in_text(text)
    results = [(acronym, "", document_name) for acronym in acronyms]

    log_message('info', f'Found {len(results)} acronyms in {document_name}')
    return results


def save_acronyms_to_csv(acronyms, output_directory, reset=True):
    """
    Saves acronyms to a CSV file. Each acronym appears only once.

    Args:
        acronyms: List of tuples [(acronym, meaning, document_name), ...]
        output_directory: Directory to save the CSV file
        reset: If True, recreate the file; if False, append to existing

    Returns:
        str: Path to the saved CSV file
    """
    csv_path = os.path.join(output_directory, ACRONYM_CSV_FILE)

    # Determine existing acronyms if not resetting
    existing_acronyms = set()
    if not reset and os.path.exists(csv_path):
        try:
            with open(csv_path, 'r', encoding='utf-8', newline='') as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                for row in reader:
                    if len(row) >= 1:
                        existing_acronyms.add(row[0])  # Just the acronym
        except Exception as e:
            log_message('warning', f'Could not read existing CSV file: {e}')

    # Remove duplicates - keep only unique acronyms (first occurrence)
    seen = set()
    unique_acronyms = []
    for acronym, meaning, doc_name in acronyms:
        if acronym not in seen and acronym not in existing_acronyms:
            seen.add(acronym)
            unique_acronyms.append((acronym, meaning, doc_name))

    # Write mode depends on reset flag
    mode = 'w' if reset else 'a'
    write_header = reset or not os.path.exists(csv_path)

    try:
        os.makedirs(output_directory, exist_ok=True)

        with open(csv_path, mode, encoding='utf-8', newline='') as f:
            writer = csv.writer(f)

            if write_header:
                writer.writerow(['Acronym', 'Meaning', 'Document'])

            # Sort alphabetically by acronym
            unique_acronyms.sort(key=lambda x: x[0])

            for acronym, meaning, doc_name in unique_acronyms:
                writer.writerow([acronym, meaning, doc_name])

        log_message('info', f'Saved {len(unique_acronyms)} acronyms to {csv_path}')
        return csv_path

    except Exception as e:
        log_message('error', f'Error saving acronyms to CSV: {e}')
        raise


def process_acronyms_from_folder(source_folder, output_directory, reset=True):
    """
    Processes all .md files in a folder and extracts acronyms to CSV.

    Args:
        source_folder: Folder containing .md files (Ingestion directory)
        output_directory: Directory to save the CSV file
        reset: If True, recreate the CSV; if False, append

    Returns:
        tuple: (csv_path, total_acronyms_count)
    """
    if not os.path.exists(source_folder):
        log_message('warning', f'Source folder does not exist: {source_folder}')
        return None, 0

    # Get all .md files
    md_files = [f for f in os.listdir(source_folder) if f.endswith('.md')]

    if not md_files:
        log_message('warning', f'No .md files found in {source_folder}')
        return None, 0

    all_acronyms = []

    for filename in md_files:
        file_path = os.path.join(source_folder, filename)
        try:
            acronyms = extract_acronyms_from_markdown(file_path)
            all_acronyms.extend(acronyms)
        except Exception as e:
            log_message('error', f'Failed to process {filename}: {e}')
            continue

    if all_acronyms:
        csv_path = save_acronyms_to_csv(all_acronyms, output_directory, reset)
        return csv_path, len(all_acronyms)

    return None, 0
