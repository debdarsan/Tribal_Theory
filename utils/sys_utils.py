import os
import re
import base64
import mimetypes
import json
from datetime import datetime
import shutil
import zipfile
import io
from utils.logging_utils import *
from consts.consts import *


def get_path_and_dir_sep():
    """
    Returns the default path and the directory separator.

    Returns:
        tuple: (current_path, separator)
    """
    current_path = os.getcwd()
    separator = os.path.sep
    return current_path, separator


def get_dir_sep() -> str:
    """
    Returns the directory separator.

    Returns:
        str: Directory separator for current OS
    """
    return os.path.sep


def sanitize_filename(filename):
    """
    Sanitizes a filename by replacing invalid characters with underscores.

    Args:
        filename: The filename to sanitize

    Returns:
        str: Sanitized filename
    """
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '_', filename)
    return sanitized


def create_directory(path) -> None:
    """
    Create the output directory if it doesn't exist.

    Args:
        path: Directory path to create
    """
    if not os.path.exists(path):
        os.makedirs(path)
        log_message("info", "Directory: " + path + " created successfully!")
    else:
        log_message("info", "Directory: " + path + " already exists!")


def does_directory_exist(path) -> bool:
    """
    Checks if directory exists.

    Args:
        path: Directory path to check

    Returns:
        bool: True if directory exists, False otherwise
    """
    if not os.path.exists(path):
        log_message("info", "Directory: " + path + " does not exist!")
        return False
    else:
        log_message("info", "Directory: " + path + " exists!")
        return True


def clear_directory(directory):
    """
    Removes all files and empty directories from a directory.

    Args:
        directory: Path to the directory to clear
    """
    all_files_and_dirs = os.listdir(directory)

    for item in all_files_and_dirs:
        item_path = os.path.join(directory, item)
        if os.path.isfile(item_path):
            os.remove(item_path)
        elif os.path.isdir(item_path):
            os.rmdir(item_path)  # Note: This will only remove empty directories

    log_message("info", "All files and empty directories have been removed from the directory: " + directory)


def delete_directory(directory):
    """
    Deletes a directory and all its contents.

    Args:
        directory: Path to the directory to delete
    """
    if os.path.exists(directory):
        shutil.rmtree(directory)


def correct_directory_separator(directory_path):
    """
    Corrects directory separator based on the current OS.

    Args:
        directory_path: Path with potentially incorrect separators

    Returns:
        str: Path with correct separators for current OS
    """
    os_type = "UNIX" if os.name == "posix" else "WIN"
    print(f"Detected OS: {os_type}")

    correct_separator = os.sep

    if os_type == "WIN":
        corrected_path = directory_path.replace("/", correct_separator)
    else:
        corrected_path = directory_path.replace("\\", correct_separator)

    return corrected_path


def find_directory_path(directory_name, root_path='.'):
    """
    Search for the specified directory name starting from the root_path.

    Args:
        directory_name: Name of the directory to find
        root_path: Root path to start the search from. Defaults to current directory.

    Returns:
        str or None: Path of the found directory or None if not found
    """
    try:
        for root, dirs, _ in os.walk(root_path):
            if directory_name in dirs:
                return os.path.join(root, directory_name)
    except Exception as e:
        log_message("error", f"Error finding directory: {e}")
    return None


def extract_filename(text):
    """
    Extracts filename from a path string (UNIX or Windows).

    Args:
        text: Text containing a file path

    Returns:
        tuple: (full_filename, filename_without_extension, file_extension) or (None, None, None)
    """
    try:
        pattern = r"(/[^/\n\r]+)$|([a-zA-Z]:\\(?:[^\\/\n\r]+\\)*[^\\/\n\r]+)$"
        match = re.search(pattern, text)

        if match:
            full_filename = (
                match.group(0).split("/")[-1]
                if "/" in match.group(0)
                else match.group(0).split("\\")[-1]
            )
            filename_without_extension, file_extension = os.path.splitext(full_filename)
            return full_filename, filename_without_extension, file_extension
        else:
            return None, None, None
    except Exception as e:
        log_message("error", f"An error occurred in extract_filename: {e}")
        raise


def get_file_name_from_path_no_ext(file_name):
    """
    Gets filename without extension from a path.

    Args:
        file_name: Full file path or name

    Returns:
        str: Filename without extension
    """
    file_name_without_ext = os.path.splitext(os.path.basename(file_name))[0]
    log_message("info", "File name without extension: " + file_name_without_ext)
    return file_name_without_ext


def get_file_name_with_ext_from_path(file_name):
    """
    Gets filename with extension from a path.

    Args:
        file_name: Full file path

    Returns:
        str: Filename with extension
    """
    file_name_without_ext = os.path.splitext(os.path.basename(file_name))[0]
    log_message("info", "File name without extension: " + file_name_without_ext)
    ext = os.path.splitext(os.path.basename(file_name))[1]
    log_message("info", "File extension: " + ext)
    file_name_with_ext = file_name_without_ext + ext
    return file_name_with_ext


def read_markdown_content(markdown_file):
    """
    Reads content from a markdown file.

    Args:
        markdown_file: Path to the markdown file

    Returns:
        str or None: File content or None if failed
    """
    try:
        with open(markdown_file, "r", encoding="utf-8") as file:
            markdown_content = file.read()
            log_message("info", "Read the markdown file: " + markdown_file)
            return markdown_content
    except:
        log_message("error", "Failed to read markdown file: " + markdown_file)
        return None


def write_markdown_content(markdown_content, output_md_file):
    """
    Writes content to a markdown file.

    Args:
        markdown_content: Content to write
        output_md_file: Path to the output file
    """
    try:
        with open(output_md_file, "w", encoding="utf-8") as file:
            file.write(markdown_content)
        log_message("info", "Written the markdown file: " + output_md_file)
    except Exception as e:
        log_message("error", "Failed to write markdown file: " + output_md_file + '\n' + str(e))
        return None


def write_markdown_content_appened_filename(markdown_content, output_md_file, append_filename_string, directory):
    """
    Writes markdown content to a file with an appended string in the filename.

    Args:
        markdown_content: Content to write
        output_md_file: Base filename
        append_filename_string: String to append to filename
        directory: Output directory
    """
    try:
        if not output_md_file.lower().endswith('.md'):
            output_md_file += '.md'

        base_name = os.path.splitext(output_md_file)[0]
        new_file_name = base_name + append_filename_string + '.md'
        new_file_path = os.path.join(directory, new_file_name)

        with open(new_file_path, "w", encoding="utf-8") as file:
            file.write(markdown_content)
        log_message("info", "Written the markdown file: " + new_file_path)

    except Exception as e:
        log_message("error", "Failed to write markdown file: " + new_file_path + '\n' + str(e))
        return None


def move_file_from_root_to_subdirectory(md_filename, CONVERTED_DIRECTORY):
    """
    Moves a file from root directory to a subdirectory.

    Args:
        md_filename: Name of the file to move
        CONVERTED_DIRECTORY: Destination directory

    Returns:
        str or None: New file path or None if failed
    """
    root_directory = os.path.abspath(".")
    source_path = os.path.join(root_directory, md_filename)
    destination_path = os.path.join(CONVERTED_DIRECTORY, md_filename)

    try:
        shutil.move(source_path, destination_path)
        log_message("info", "Moved file: " + source_path + " to: " + destination_path)
    except:
        log_message("error", "Failed to move file: " + source_path + " to: " + destination_path)
        return None

    return destination_path


def save_with_appended_name(original_file_path, directory, append_filename_string):
    """
    Copies a file with an appended string in the filename.

    Args:
        original_file_path: Path to the original file
        directory: Destination directory
        append_filename_string: String to append to filename

    Returns:
        str: Path to the new file
    """
    file_name, file_extension = os.path.splitext(original_file_path)
    base_name = os.path.basename(file_name)
    new_file_name = base_name + append_filename_string + file_extension
    new_file_path = os.path.join(directory, new_file_name)
    shutil.copy(original_file_path, new_file_path)
    return new_file_path


def set_directories():
    """
    Set up application directories for document processing.

    Returns:
        tuple: (DOC_SOURCE_DIRECTORY, CONVERSION_DIRECTORY, INGESTION_DIRECTORY,
                DEBUG_DIRECTORY, DATA_DIRECTORY, TABLE_DATA_DIRECTORY)
    """
    from consts.sys_consts import (
        DOC_SOURCE_DIR, CONVERSION_DIR, INGESTION_DIR,
        DEBUG_DIR, DATA_DIR, TABLE_DATA_DIR
    )

    current_path, dir_seperator = get_path_and_dir_sep()

    # Create all required directories
    DOC_SOURCE_DIRECTORY = current_path + dir_seperator + DOC_SOURCE_DIR
    create_directory(DOC_SOURCE_DIRECTORY)
    DOC_SOURCE_DIRECTORY = DOC_SOURCE_DIRECTORY + dir_seperator

    CONVERSION_DIRECTORY = current_path + dir_seperator + CONVERSION_DIR
    create_directory(CONVERSION_DIRECTORY)
    CONVERSION_DIRECTORY = CONVERSION_DIRECTORY + dir_seperator

    INGESTION_DIRECTORY = current_path + dir_seperator + INGESTION_DIR
    create_directory(INGESTION_DIRECTORY)
    INGESTION_DIRECTORY = INGESTION_DIRECTORY + dir_seperator

    DEBUG_DIRECTORY = current_path + dir_seperator + DEBUG_DIR
    create_directory(DEBUG_DIRECTORY)
    DEBUG_DIRECTORY = DEBUG_DIRECTORY + dir_seperator

    DATA_DIRECTORY = current_path + dir_seperator + DATA_DIR
    create_directory(DATA_DIRECTORY)
    DATA_DIRECTORY = DATA_DIRECTORY + dir_seperator

    TABLE_DATA_DIRECTORY = current_path + dir_seperator + TABLE_DATA_DIR
    create_directory(TABLE_DATA_DIRECTORY)
    TABLE_DATA_DIRECTORY = TABLE_DATA_DIRECTORY + dir_seperator

    return (
        DOC_SOURCE_DIRECTORY,
        CONVERSION_DIRECTORY,
        INGESTION_DIRECTORY,
        DEBUG_DIRECTORY,
        DATA_DIRECTORY,
        TABLE_DATA_DIRECTORY
    )


def set_QA_directory():
    """
    Set up QA directory.

    Returns:
        tuple: (QA_DIRECTORY,)
    """
    current_path, dir_seperator = get_path_and_dir_sep()

    QA_DIRECTORY = current_path + dir_seperator + QA_DIR
    create_directory(QA_DIRECTORY)
    QA_DIRECTORY = QA_DIRECTORY + dir_seperator

    return (QA_DIRECTORY,)


def set_chat_related_directories():
    """
    Set up chat-related directories.

    Returns:
        str: QA_DIRECTORY path
    """
    current_path, dir_seperator = get_path_and_dir_sep()

    QA_DIRECTORY = current_path + dir_seperator + QA_DIR
    create_directory(QA_DIRECTORY)
    QA_DIRECTORY = QA_DIRECTORY + dir_seperator

    return QA_DIRECTORY


def zip_files(directory_path, user_name, file_names, zip_name, only_today=False):
    """
    Creates a ZIP file from specified files.

    Args:
        directory_path: Directory containing the files
        user_name: User name to append to filenames
        file_names: List of file names to include
        zip_name: Name for the ZIP file
        only_today: If True, only include files from today

    Returns:
        tuple: (zip_buffer, zip_name)
    """
    zip_buffer = io.BytesIO()
    today_str = datetime.now().strftime("%y%m%d")

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_name in file_names:
            file_date = file_name.split('_')[-1][:6]
            if not only_today or file_date == today_str:
                file_path = os.path.join(directory_path, file_name) + "_" + user_name + ".json"
                if os.path.exists(file_path):
                    zip_file.write(file_path, os.path.basename(file_path))

    zip_buffer.seek(0)
    return zip_buffer, zip_name


def restructure_qa_history_for_export(qa_history):
    """
    Restructure QA history to separate source_documents and relevant_images.

    Args:
        qa_history: Original QA history dict

    Returns:
        dict: Restructured QA history with separate source_documents and relevant_images
    """
    restructured = {
        "historical_prompts": qa_history.get("historical_prompts", []),
        "historical_responses": []
    }

    for response in qa_history.get("historical_responses", []):
        new_response = dict(response)  # Copy the response

        source_docs = response.get("source_documents", [])
        if source_docs:
            text_docs = []
            image_docs = []

            for doc in source_docs:
                if isinstance(doc, dict):
                    metadata = doc.get("metadata", {})
                else:
                    metadata = getattr(doc, "metadata", {})

                if metadata.get('collection_type') == 'image':
                    image_docs.append(doc)
                else:
                    text_docs.append(doc)

            new_response["source_documents"] = text_docs
            if image_docs:
                new_response["relevant_images"] = image_docs

        restructured["historical_responses"].append(new_response)

    return restructured


def zip_files_multi_user(directory_path, user_chat_history_dict, zip_name, selected_user="All Users", only_today=False):
    """
    Zip files for multiple users or a selected user.

    Args:
        directory_path: Directory containing the files
        user_chat_history_dict: Dictionary mapping users to their file lists
        zip_name: Name for the ZIP file
        selected_user: User to export ("All Users" for everyone)
        only_today: If True, only include files from today

    Returns:
        tuple: (zip_buffer, zip_name)
    """
    zip_buffer = io.BytesIO()
    today_str = datetime.now().strftime("%y%m%d")

    if selected_user == "All Users":
        users_to_zip = user_chat_history_dict.keys()
    else:
        users_to_zip = [selected_user] if selected_user in user_chat_history_dict else []

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for user in users_to_zip:
            file_names = user_chat_history_dict.get(user, [])
            for file_name in file_names:
                file_date = file_name.split('_')[-1][:6]
                if not only_today or file_date == today_str:
                    file_path = os.path.join(directory_path, file_name + "_" + user + ".json")
                    if os.path.exists(file_path):
                        # Read, restructure, and write the JSON
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                qa_history = json.load(f)

                            restructured = restructure_qa_history_for_export(qa_history)
                            json_content = json.dumps(restructured, indent=2, ensure_ascii=False)
                            zip_file.writestr(os.path.basename(file_path), json_content.encode('utf-8'))
                        except Exception as e:
                            log_message("error", f"Error restructuring {file_path}: {e}")
                            # Fall back to original file
                            zip_file.write(file_path, os.path.basename(file_path))

    zip_buffer.seek(0)
    return zip_buffer, zip_name


def get_image_base64(image_path):
    """
    Convert an image file to base64 string.

    Args:
        image_path: Path to the image file

    Returns:
        str or None: Base64 data URI or None if failed
    """
    try:
        mime_type, _ = mimetypes.guess_type(image_path)
        if mime_type is None:
            mime_type = 'image/png'

        with open(image_path, 'rb') as img_file:
            b64_data = base64.b64encode(img_file.read()).decode('utf-8').replace('\n', '').replace('\r', '')

        return f"data:{mime_type};base64,{b64_data}"
    except Exception as e:
        log_message("error", f"Error encoding image {image_path}: {e}")
        return None


def embed_images_in_html(content, base_path="."):
    """
    Replace image src paths with base64 embedded data in HTML img tags.

    Args:
        content: HTML content with img tags
        base_path: Base path for resolving relative image paths

    Returns:
        str: Content with embedded base64 images
    """
    img_pattern = r'<img\s+[^>]*src=["\']([^"\']+)["\'][^>]*>'

    def replace_img(match):
        full_tag = match.group(0)
        img_src = match.group(1)

        if img_src.startswith('data:'):
            return full_tag

        clean_src = img_src
        if clean_src.startswith('./'):
            clean_src = clean_src[2:]
        if clean_src.startswith('app/'):
            clean_src = clean_src[4:]

        possible_paths = [
            os.path.join(base_path, img_src),
            os.path.join(base_path, clean_src),
            os.path.join(base_path, 'static', clean_src.replace('static/', '')),
            img_src,
            clean_src,
        ]

        cwd = os.getcwd()
        possible_paths.extend([
            os.path.join(cwd, img_src),
            os.path.join(cwd, clean_src),
            os.path.join(cwd, img_src.lstrip('./')),
        ])

        for img_path in possible_paths:
            img_path = os.path.normpath(img_path)
            if os.path.exists(img_path):
                b64_data = get_image_base64(img_path)
                if b64_data:
                    new_tag = re.sub(r"src=['\"][^'\"]+['\"]", f'src="{b64_data}"', full_tag)
                    # Ensure image has block display styling
                    if 'style=' not in new_tag.lower():
                        new_tag = new_tag.replace('<img', '<img style="display:block; max-width:100%; height:auto; margin:15px 0;"')
                    elif 'display' not in new_tag.lower():
                        # Add display:block to existing style
                        new_tag = re.sub(r'style=["\']', r'style="display:block; ', new_tag)
                    return new_tag

        log_message("warning", f"Could not find image: {img_src}")
        return full_tag

    return re.sub(img_pattern, replace_img, content, flags=re.IGNORECASE)


def convert_qa_to_markdown(qa_history, embed_images=True, base_path="."):
    """
    Convert QA history to markdown format with embedded images.

    Args:
        qa_history: Dictionary with historical_prompts and historical_responses
        embed_images: If True, embed images as base64
        base_path: Base path for resolving image paths

    Returns:
        str: Markdown formatted content
    """
    def ensure_html_blocks_have_blank_lines(text):
        """Ensure HTML tags like <img> are surrounded by blank lines for proper rendering."""
        text = re.sub(r'(<img[^>]+>)', r'\n\n\1\n\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text

    markdown_lines = []

    markdown_lines.append("# Chat History")
    markdown_lines.append("")
    markdown_lines.append(f"*Exported on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    markdown_lines.append("")
    markdown_lines.append("---")
    markdown_lines.append("")

    prompts = qa_history.get("historical_prompts", [])
    responses = qa_history.get("historical_responses", [])

    for i, (prompt, response) in enumerate(zip(prompts, responses), 1):
        markdown_lines.append(f"## Q{i}: {prompt}")
        markdown_lines.append("")

        answer = response.get("result", "No answer available")

        if embed_images:
            answer = embed_images_in_html(answer, base_path)
            answer = ensure_html_blocks_have_blank_lines(answer)

        markdown_lines.append("### Answer:")
        markdown_lines.append("")
        markdown_lines.append(answer)
        markdown_lines.append("")

        if not response.get("greet_flag", False):
            source_docs = response.get("source_documents", [])
            if source_docs:
                # Separate text and image documents
                text_docs = []
                image_docs = []
                for doc in source_docs:
                    if isinstance(doc, dict):
                        metadata = doc.get("metadata", {})
                    else:
                        metadata = getattr(doc, "metadata", {})

                    if metadata.get('collection_type') == 'image':
                        image_docs.append(doc)
                    else:
                        text_docs.append(doc)

                # Display text sources
                if text_docs:
                    markdown_lines.append("")
                    markdown_lines.append("<details>")
                    markdown_lines.append(f"<summary>Source Documents ({len(text_docs)})</summary>")
                    markdown_lines.append("")

                    for j, doc in enumerate(text_docs, 1):
                        if isinstance(doc, dict):
                            page_content = doc.get("page_content", "")
                            metadata = doc.get("metadata", {})
                        else:
                            page_content = getattr(doc, "page_content", "")
                            metadata = getattr(doc, "metadata", {})

                        markdown_lines.append(f"**Source {j}:**")
                        markdown_lines.append("")
                        if metadata:
                            markdown_lines.append(f"- File: {metadata.get('File', 'N/A')}")
                            markdown_lines.append(f"- Section: {metadata.get('Section', 'N/A')}")
                            markdown_lines.append("")

                        if embed_images:
                            page_content = embed_images_in_html(page_content, base_path)
                            page_content = ensure_html_blocks_have_blank_lines(page_content)

                        markdown_lines.append(page_content)
                        markdown_lines.append("")

                    markdown_lines.append("</details>")
                    markdown_lines.append("")

                # Display image sources (Relevant Images)
                if image_docs:
                    markdown_lines.append("")
                    markdown_lines.append("<details>")
                    markdown_lines.append(f"<summary>Relevant Images ({len(image_docs)})</summary>")
                    markdown_lines.append("")

                    for j, doc in enumerate(image_docs, 1):
                        if isinstance(doc, dict):
                            metadata = doc.get("metadata", {})
                        else:
                            metadata = getattr(doc, "metadata", {})

                        static_url = metadata.get('static_url', '')
                        source_doc = metadata.get('source_doc', 'Screenshot')
                        qualitative_ocr = metadata.get('qualitative_ocr', '')
                        preceding_text = metadata.get('preceding_text', '')
                        following_text = metadata.get('following_text', '')

                        markdown_lines.append(f"**Image {j}: {source_doc}**")
                        markdown_lines.append("")

                        # Display preceding context
                        if preceding_text:
                            markdown_lines.append(f"**Preceding Context:**")
                            markdown_lines.append(f"> {preceding_text}")
                            markdown_lines.append("")

                        # Embed the image
                        if static_url and embed_images:
                            img_path = static_url.replace('./app/', '').replace('/', os.sep)
                            possible_paths = [
                                os.path.join(base_path, img_path),
                                os.path.join(base_path, static_url),
                                img_path,
                            ]
                            for path in possible_paths:
                                path = os.path.normpath(path)
                                if os.path.exists(path):
                                    b64_data = get_image_base64(path)
                                    if b64_data:
                                        markdown_lines.append(f'<img src="{b64_data}" style="max-width:100%; height:auto; border:1px solid #ddd; border-radius:4px; margin:10px 0;">')
                                        markdown_lines.append("")
                                        break

                        # Display image description
                        if qualitative_ocr:
                            markdown_lines.append(f"**Description:** *{qualitative_ocr}*")
                            markdown_lines.append("")

                        # Display following context
                        if following_text:
                            markdown_lines.append(f"**Following Context:**")
                            markdown_lines.append(f"> {following_text}")
                            markdown_lines.append("")

                    markdown_lines.append("</details>")
                    markdown_lines.append("")

        markdown_lines.append("---")
        markdown_lines.append("")

    return "\n".join(markdown_lines)


def convert_markdown_tables(text):
    """
    Convert markdown tables to HTML tables, preserving any HTML content within cells.
    This function specifically handles tables and can work with mixed HTML/markdown content.
    """
    from utils.chat_utils import convert_inline_markdown

    if not text or '|' not in text:
        return text

    # Normalize literal \n to actual newlines
    text = text.replace('\\n', '\n')
    lines = text.split('\n')
    result_lines = []
    i = 0

    def is_table_separator(line):
        """Check if line is a markdown table separator."""
        stripped = line.strip()
        # Must have at least one | and consist mainly of |, -, :, and whitespace
        if '|' not in stripped:
            return False
        # Remove all valid separator characters and see if anything remains
        cleaned = re.sub(r'[\|\-:\s]', '', stripped)
        return len(cleaned) == 0 and '-' in stripped

    def parse_table_row(line):
        """Parse a markdown table row into cells."""
        stripped = line.strip()
        if stripped.startswith('|'):
            stripped = stripped[1:]
        if stripped.endswith('|'):
            stripped = stripped[:-1]
        # Split by | but be careful with content
        cells = [cell.strip() for cell in stripped.split('|')]
        return cells

    def is_potential_table_row(line):
        """Check if line could be a table row (has | separators with content)."""
        stripped = line.strip()
        if '|' not in stripped:
            return False
        if is_table_separator(stripped):
            return False
        # Should have at least some content between pipes
        cells = parse_table_row(stripped)
        return len(cells) >= 1 and any(cell.strip() for cell in cells)

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Look for table start: a row with |, followed by separator
        if is_potential_table_row(stripped):
            # Look ahead for separator
            separator_idx = None
            for j in range(i + 1, min(i + 3, len(lines))):  # Check next 2 lines for separator
                if is_table_separator(lines[j]):
                    separator_idx = j
                    break

            if separator_idx is not None:
                # Found a table! Collect all rows before separator as header candidates
                header_rows = []
                for k in range(i, separator_idx):
                    if is_potential_table_row(lines[k]) or lines[k].strip() == '|':
                        header_rows.append(lines[k])
                    elif lines[k].strip():
                        # Non-table content before separator - might be part of a weird format
                        header_rows.append(lines[k])

                # Start building table HTML
                result_lines.append('<table style="border-collapse: collapse; width: 100%; margin: 10px 0;">')

                # Use the row just before separator as header (or first content row)
                if header_rows:
                    # Find the best header row (one with actual cell content)
                    header_line = None
                    for hr in reversed(header_rows):
                        if is_potential_table_row(hr):
                            header_line = hr
                            break

                    if header_line:
                        cells = parse_table_row(header_line)
                        result_lines.append('<thead><tr>')
                        for cell in cells:
                            cell = convert_inline_markdown(cell)
                            result_lines.append(f'<th style="border: 1px solid #ddd; padding: 8px; background: #f5f5f5; text-align: left;">{cell}</th>')
                        result_lines.append('</tr></thead>')

                result_lines.append('<tbody>')

                # Skip to after separator(s)
                i = separator_idx + 1
                # Skip any additional separator lines
                while i < len(lines) and is_table_separator(lines[i]):
                    i += 1

                # Collect body rows
                while i < len(lines):
                    row_line = lines[i].strip()
                    if is_potential_table_row(row_line):
                        cells = parse_table_row(row_line)
                        result_lines.append('<tr>')
                        for cell in cells:
                            cell = convert_inline_markdown(cell)
                            result_lines.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{cell}</td>')
                        result_lines.append('</tr>')
                        i += 1
                    elif is_table_separator(row_line):
                        # Skip separator within table
                        i += 1
                    else:
                        # End of table
                        break

                result_lines.append('</tbody></table>')
                continue

        # Not a table row, pass through
        result_lines.append(line)
        i += 1

    return '\n'.join(result_lines)


def markdown_to_html(text):
    """
    Convert markdown text to HTML for export.

    Handles: headers, bold, italic, numbered lists, bullet lists, tables, line breaks.
    """
    from utils.chat_utils import convert_inline_markdown

    if not text:
        return text

    # Normalize literal \n to actual newlines
    text = text.replace('\\n', '\n')
    lines = text.split('\n')
    result_lines = []
    in_list = False
    list_type = None  # 'ol' or 'ul'
    in_table = False
    table_row_count = 0

    def apply_inline_formatting(content):
        """Apply bold and italic formatting with spacing fixes."""
        return convert_inline_markdown(content)

    def parse_table_row(line):
        """Parse a markdown table row into cells."""
        stripped = line.strip()
        if stripped.startswith('|'):
            stripped = stripped[1:]
        if stripped.endswith('|'):
            stripped = stripped[:-1]
        cells = [cell.strip() for cell in stripped.split('|')]
        return cells

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Table handling: any line with | is potentially a table line
        # (lenient detection matching in-app simple_markdown_to_html behavior)
        if '|' in stripped:
            # Skip separator rows (only pipes, dashes, colons, spaces)
            if re.match(r'^[\|\-:\s]+$', stripped):
                i += 1
                continue

            # Parse cells
            cells = parse_table_row(stripped)
            if cells and any(c.strip() for c in cells):
                if not in_table:
                    # Close any open list
                    if in_list:
                        result_lines.append(f'</{list_type}>')
                        in_list = False
                        list_type = None
                    in_table = True
                    table_row_count = 0
                    result_lines.append('<table style="border-collapse: collapse; width: 100%; margin: 10px 0;">')

                tag = 'th' if table_row_count == 0 else 'td'
                bg_style = ' background: #f5f5f5;' if table_row_count == 0 else ''
                result_lines.append('<tr>')
                for cell in cells:
                    cell = apply_inline_formatting(cell)
                    result_lines.append(f'<{tag} style="border: 1px solid #ddd; padding: 8px;{bg_style} text-align: left;">{cell}</{tag}>')
                result_lines.append('</tr>')
                table_row_count += 1
                i += 1
                continue

        # Close any open table when hitting a non-table line
        if in_table:
            result_lines.append('</table>')
            in_table = False

        # Check for numbered list (1. 2. 3. etc.)
        numbered_match = re.match(r'^(\d+)\.\s+(.+)$', stripped)
        # Check for bullet list (- or *)
        bullet_match = re.match(r'^[-*]\s+(.+)$', stripped)

        if numbered_match:
            if not in_list or list_type != 'ol':
                if in_list:
                    result_lines.append(f'</{list_type}>')
                result_lines.append('<ol>')
                in_list = True
                list_type = 'ol'
            content = numbered_match.group(2)
            content = apply_inline_formatting(content)
            result_lines.append(f'<li>{content}</li>')
        elif bullet_match:
            if not in_list or list_type != 'ul':
                if in_list:
                    result_lines.append(f'</{list_type}>')
                result_lines.append('<ul>')
                in_list = True
                list_type = 'ul'
            content = bullet_match.group(1)
            content = apply_inline_formatting(content)
            result_lines.append(f'<li>{content}</li>')
        else:
            # Close any open list
            if in_list:
                result_lines.append(f'</{list_type}>')
                in_list = False
                list_type = None

            # Blockquote
            if stripped.startswith('>'):
                bq_content = stripped[2:] if stripped.startswith('> ') else stripped[1:]
                if bq_content.strip():
                    bq_content = apply_inline_formatting(bq_content)
                    result_lines.append(f'<blockquote style="border-left:3px solid #1a73e8; padding:5px 10px; margin:5px 0; background:#f0f7ff;">{bq_content}</blockquote>')
            # Process non-list content - check headers from most specific to least
            elif stripped.startswith('###### '):
                result_lines.append(f'<h6>{apply_inline_formatting(stripped[7:])}</h6>')
            elif stripped.startswith('##### '):
                result_lines.append(f'<h6>{apply_inline_formatting(stripped[6:])}</h6>')
            elif stripped.startswith('#### '):
                result_lines.append(f'<h5>{apply_inline_formatting(stripped[5:])}</h5>')
            elif stripped.startswith('### '):
                result_lines.append(f'<h4>{apply_inline_formatting(stripped[4:])}</h4>')
            elif stripped.startswith('## '):
                result_lines.append(f'<h3>{apply_inline_formatting(stripped[3:])}</h3>')
            elif stripped.startswith('# '):
                result_lines.append(f'<h2>{apply_inline_formatting(stripped[2:])}</h2>')
            elif stripped == '':
                result_lines.append('<br>')
            elif '<img' in stripped.lower():
                # Don't wrap img tags in <p> - they should be block elements
                result_lines.append(f'<div class="image-container">{stripped}</div>')
            else:
                processed = apply_inline_formatting(stripped)
                result_lines.append(f'<p>{processed}</p>')

        i += 1

    # Close any remaining open elements
    if in_table:
        result_lines.append('</table>')
    if in_list:
        result_lines.append(f'</{list_type}>')

    return '\n'.join(result_lines)


def convert_qa_to_html(qa_history, embed_images=True, base_path="."):
    """
    Convert QA history to standalone HTML format with embedded images.

    Args:
        qa_history: Dictionary with historical_prompts and historical_responses
        embed_images: If True, embed images as base64
        base_path: Base path for resolving image paths

    Returns:
        str: HTML formatted content
    """
    from utils.chat_utils import (
        convert_inline_markdown,
        convert_img_tags_to_embedded,
        fix_malformed_angle_brackets
    )

    prompts = qa_history.get("historical_prompts", [])
    responses = qa_history.get("historical_responses", [])

    html_parts = []

    html_parts.append("""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Chat History</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
               max-width: 900px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        .chat-container { background: white; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .question { color: #1a73e8; font-size: 1.2em; font-weight: bold; margin-bottom: 10px; }
        .answer { color: #333; line-height: 1.6; }
        .answer p { margin: 8px 0; }
        .answer h2, .answer h3, .answer h4, .answer h5, .answer h6 { color: #1a73e8; margin: 15px 0 10px 0; }
        .source h2, .source h3, .source h4, .source h5, .source h6 { color: #1a73e8; margin: 12px 0 8px 0; font-size: 1em; }
        .answer ol, .answer ul { margin: 10px 0; padding-left: 25px; }
        .answer li { margin: 5px 0; line-height: 1.5; }
        .answer strong { color: #333; }
        .answer img, .source img { display: block; max-width: 100%; height: auto; margin: 15px 0; border: 1px solid #ddd; border-radius: 4px; }
        .answer table, .source table { border-collapse: collapse; width: 100%; margin: 10px 0; }
        .answer th, .source th { border: 1px solid #ddd; padding: 8px; background: #f5f5f5; text-align: left; }
        .answer td, .source td { border: 1px solid #ddd; padding: 8px; }
        .source p { margin: 8px 0; }
        .source ol, .source ul { margin: 10px 0; padding-left: 25px; }
        .source li { margin: 5px 0; line-height: 1.5; }
        .source-content { line-height: 1.6; }
        .source-content img { display: block; max-width: 100%; height: auto; margin: 15px 0; border: 1px solid #ddd; border-radius: 4px; }
        .image-container { display: block; margin: 15px 0; clear: both; }
        details { margin-top: 15px; padding: 10px; background: #f9f9f9; border-radius: 4px; }
        summary { cursor: pointer; font-weight: bold; color: #666; }
        .source { margin: 10px 0; padding: 10px; border-left: 3px solid #1a73e8; background: #fff; }
        blockquote { border-left: 3px solid #1a73e8; padding: 5px 10px; margin: 10px 0; background: #f0f7ff; color: #333; }
        .metadata { font-size: 0.85em; color: #666; }
        hr { border: none; border-top: 1px solid #eee; margin: 20px 0; }
        h1 { color: #333; }
        .export-info { color: #888; font-size: 0.9em; }
    </style>
</head>
<body>
    <h1>Chat History</h1>
    <p class="export-info">Exported on: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>
    <hr>
""")

    for i, (prompt, response) in enumerate(zip(prompts, responses), 1):
        answer = response.get("result", "No answer available")

        # Clean up backslash escape artifacts
        answer = answer.replace('\\"', '"').replace("\\'", "'").replace('\\$', '$')
        # Convert markdown to HTML for proper formatting
        answer = markdown_to_html(answer)
        # Post-process inline markdown with spacing fixes
        answer = convert_inline_markdown(answer)

        if embed_images:
            answer = embed_images_in_html(answer, base_path)

        html_parts.append(f"""
    <div class="chat-container">
        <div class="question">Q{i}: {prompt}</div>
        <div class="answer">{answer}</div>
""")

        if not response.get("greet_flag", False):
            source_docs = response.get("source_documents", [])
            if source_docs:
                # Separate text and image documents
                text_docs = []
                image_docs = []
                for doc in source_docs:
                    if isinstance(doc, dict):
                        metadata = doc.get("metadata", {})
                    else:
                        metadata = getattr(doc, "metadata", {})

                    if metadata.get('collection_type') == 'image':
                        image_docs.append(doc)
                    else:
                        text_docs.append(doc)

                # Display text sources
                if text_docs:
                    html_parts.append(f"""
        <details>
            <summary>Source Documents ({len(text_docs)})</summary>
""")
                    for j, doc in enumerate(text_docs, 1):
                        if isinstance(doc, dict):
                            page_content = doc.get("page_content", "")
                            metadata = doc.get("metadata", {})
                        else:
                            page_content = getattr(doc, "page_content", "")
                            metadata = getattr(doc, "metadata", {})

                        # Apply same formatting pipeline as in-app rendering
                        # Step 1: Convert V6 <img> tags to base64 before angle bracket cleanup
                        page_content = convert_img_tags_to_embedded(page_content)
                        # Step 2: Fix malformed angle brackets from V6 alt text
                        page_content = fix_malformed_angle_brackets(page_content)
                        # Step 3: Clean up backslash escape artifacts
                        page_content = page_content.replace('\\"', '"').replace("\\'", "'").replace('\\$', '$')

                        # Step 4: Preserve HTML tables before markdown conversion
                        html_tables_found = re.findall(r'<table\b[^>]*>.*?</table>', page_content, flags=re.DOTALL)
                        for idx, table_html in enumerate(html_tables_found):
                            page_content = page_content.replace(table_html, f"%%HTMLTABLE{idx}%%", 1)

                        # Step 5: Convert markdown to HTML
                        page_content = markdown_to_html(page_content)
                        # Step 6: Post-process inline markdown with spacing fixes
                        page_content = convert_inline_markdown(page_content)

                        # Step 7: Reinsert preserved HTML tables
                        for idx, table_html in enumerate(html_tables_found):
                            page_content = page_content.replace(f"%%HTMLTABLE{idx}%%", table_html)

                        # Step 8: Embed remaining images
                        if embed_images:
                            page_content = embed_images_in_html(page_content, base_path)

                        html_parts.append(f"""
            <div class="source">
                <strong>Source {j}:</strong>
                <div class="metadata">
                    File: {metadata.get('File', 'N/A')} | Section: {metadata.get('Section', 'N/A')}
                </div>
                <div class="source-content">{page_content}</div>
            </div>
""")
                    html_parts.append("        </details>")

                # Display image sources (Relevant Images)
                if image_docs:
                    html_parts.append(f"""
        <details>
            <summary>Relevant Images ({len(image_docs)})</summary>
""")
                    for j, doc in enumerate(image_docs, 1):
                        if isinstance(doc, dict):
                            metadata = doc.get("metadata", {})
                        else:
                            metadata = getattr(doc, "metadata", {})

                        static_url = metadata.get('static_url', '')
                        source_doc = metadata.get('source_doc', 'Screenshot')
                        qualitative_ocr = metadata.get('qualitative_ocr', '')
                        preceding_text = metadata.get('preceding_text', '')
                        following_text = metadata.get('following_text', '')

                        html_parts.append(f"""
            <div class="source">
                <strong>Image {j}: {source_doc}</strong>
""")
                        # Display preceding context with formatting
                        if preceding_text:
                            preceding_text = preceding_text.replace('\\"', '"').replace("\\'", "'").replace('\\$', '$')
                            preceding_text = convert_inline_markdown(preceding_text)
                            preceding_text = preceding_text.replace('\n', '<br>')
                            html_parts.append(f'                <div style="margin:10px 0; padding:8px; background:#f0f7ff; border-radius:4px;"><strong style="color:#1a73e8;">Preceding Context:</strong><br>{preceding_text}</div>')

                        # Embed the image
                        if static_url and embed_images:
                            img_path = static_url.replace('./app/', '').replace('/', os.sep)
                            possible_paths = [
                                os.path.join(base_path, img_path),
                                os.path.join(base_path, static_url),
                                img_path,
                            ]
                            for path in possible_paths:
                                path = os.path.normpath(path)
                                if os.path.exists(path):
                                    b64_data = get_image_base64(path)
                                    if b64_data:
                                        html_parts.append(f'                <div><img src="{b64_data}" style="max-width:100%; height:auto; border:1px solid #ddd; border-radius:4px; margin:10px 0;"></div>')
                                        break

                        # Display image description with formatting
                        if qualitative_ocr:
                            qualitative_ocr = qualitative_ocr.replace('\\"', '"').replace("\\'", "'").replace('\\$', '$')
                            qualitative_ocr = convert_inline_markdown(qualitative_ocr)
                            qualitative_ocr = qualitative_ocr.replace('\n', '<br>')
                            html_parts.append(f'                <div style="color:#666; font-style:italic; margin:5px 0;"><strong>Description:</strong> {qualitative_ocr}</div>')

                        # Display following context with formatting
                        if following_text:
                            following_text = following_text.replace('\\"', '"').replace("\\'", "'").replace('\\$', '$')
                            following_text = convert_inline_markdown(following_text)
                            following_text = following_text.replace('\n', '<br>')
                            html_parts.append(f'                <div style="margin:10px 0; padding:8px; background:#fff7f0; border-radius:4px;"><strong style="color:#e87a1a;">Following Context:</strong><br>{following_text}</div>')

                        html_parts.append("            </div>")

                    html_parts.append("        </details>")

        html_parts.append("    </div>")

    html_parts.append("""
</body>
</html>""")

    return "".join(html_parts)


def export_qa_history_to_markdown(directory, json_filename, output_filename=None, embed_images=True):
    """
    Load QA history from JSON and export to markdown with embedded images.

    Args:
        directory: Directory containing the JSON file
        json_filename: Name of the JSON file
        output_filename: Optional output filename
        embed_images: If True, embed images as base64

    Returns:
        tuple: (markdown_content, output_filename) or (None, None) on error
    """
    try:
        json_path = os.path.join(directory, json_filename)
        if not json_filename.endswith('.json'):
            json_path += '.json'

        with open(json_path, 'r', encoding='utf-8') as f:
            qa_history = json.load(f)

        base_path = os.path.dirname(os.path.dirname(directory))

        markdown_content = convert_qa_to_markdown(qa_history, embed_images, base_path)

        if output_filename is None:
            output_filename = json_filename.replace('.json', '.md')

        return markdown_content, output_filename

    except Exception as e:
        log_message("error", f"Error exporting QA history to markdown: {e}")
        return None, None


def create_markdown_zip(directory, user_chat_history_dict, zip_name, selected_user="All Users", embed_images=True, output_format="html", only_today=False):
    """
    Create a ZIP file containing markdown or HTML exports of chat histories.

    Args:
        directory: Directory containing the JSON files
        user_chat_history_dict: Dictionary mapping users to their file lists
        zip_name: Name for the ZIP file
        selected_user: User to export ("All Users" for everyone)
        embed_images: If True, embed images as base64
        output_format: "html" or "md"
        only_today: If True, only include files from today

    Returns:
        tuple: (zip_buffer, zip_name)
    """
    zip_buffer = io.BytesIO()

    if selected_user == "All Users":
        users_to_export = user_chat_history_dict.keys()
    else:
        users_to_export = [selected_user] if selected_user in user_chat_history_dict else []

    base_path = os.getcwd()
    file_ext = ".html" if output_format == "html" else ".md"
    today_str = datetime.now().strftime("%y%m%d")

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for user in users_to_export:
            file_names = user_chat_history_dict.get(user, [])
            for file_name in file_names:
                if only_today:
                    file_date = file_name.split('_')[-1][:6]
                    if file_date != today_str:
                        continue

                json_path = os.path.join(directory, file_name + "_" + user + ".json")

                if os.path.exists(json_path):
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            qa_history = json.load(f)

                        if output_format == "html":
                            content = convert_qa_to_html(qa_history, embed_images, base_path)
                        else:
                            content = convert_qa_to_markdown(qa_history, embed_images, base_path)

                        output_filename = file_name + "_" + user + file_ext
                        zip_file.writestr(output_filename, content.encode('utf-8'))

                    except Exception as e:
                        log_message("error", f"Error processing {json_path}: {e}")

    zip_buffer.seek(0)
    return zip_buffer, zip_name
