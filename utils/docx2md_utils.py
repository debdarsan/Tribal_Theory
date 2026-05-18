import pypandoc
import os
import re
from utils.logging_utils import *
from utils.sys_utils import *
from utils.alt_text_utils import (
    find_enclosing_text_around_image,
    find_enclosing_text_around_image_raw,
    replace_href_by_string,
    correct_alt_text
)
from consts.sys_consts import *
import consts.conv_consts as conv_consts
from consts.conv_consts import OUTPUT_FORMAT, EXTRA_ARGS_LIST, SECTIONS_TO_BE_REMOVED
from PIL import Image as PILImage

# Substitutes IMG_DIR with the constructed_img_dir
def define_pypandoc_media_dir(new_img_dir):
    # Find the index of '--extract-media' in the list
    index = EXTRA_ARGS_LIST.index('--extract-media')
    # Update the element after '--extract-media' with the new directory
    EXTRA_ARGS_LIST[index + 1] = new_img_dir

# Run pypandoc to convert docx to markdown
def run_pypandoc(a_docx_file_file_name, constructed_img_dir, output_md_file):
    try:
        log_message('info', f'Running pypandoc for file: {a_docx_file_file_name}')
        # Use the stored variables when calling pypandoc.convert_file
        # Formulate the output image directory under "static" folder
        # With the subdirectory name as the docx filename without extension
        define_pypandoc_media_dir(constructed_img_dir)
        output = pypandoc.convert_file(
            a_docx_file_file_name,
            OUTPUT_FORMAT,
            outputfile=output_md_file,
            extra_args=EXTRA_ARGS_LIST
        )

        log_message('info', f'Conversion completed for: {a_docx_file_file_name}')
        log_message('info', f'Output file {output_md_file} is written to to root folder.')

    except Exception as e:
        log_message("error", f"Pypandoc error: {e}. Pypandoc failed to convert file using run_pypandoc.")
        raise OSError(f"Pypandoc error: {e}. Pypandoc failed to convert file using run_pypandoc.")

    return

# Removes specified sections from the markdown content
# E.g.: SECTIONS_TO_BE_REMOVED = ['Table of Contents', 'Change History', 'Copyright', 'Index']
def remove_markdown_sections(markdown_content, remove_sections):
    lines = markdown_content.splitlines()
    skip = False
    result = []

    for line in lines:
        # Check if the line starts with a section to remove
        if any(section in line for section in remove_sections) and (line.strip().startswith(('#', '**')) or line.strip() in remove_sections):
            skip = True
            continue
        # If the line starts with a new section or a marker, end the skipping
        if line.strip().startswith(('#', '*')) and not any(section in line for section in remove_sections):
            skip = False
        # If not skipping, add the line to the result
        if not skip:
            result.append(line)

    return '\n'.join(result)

def process_images(markdown_content, filename_without_ext, img_dir):
    """
    Process all images in markdown content: rename, convert, and build <img> tags.

    Handles TWO image formats that pypandoc produces:
      1. HTML <img> tags:  <img src="media/image1.png" ...>
         Pattern: r'<img.*?src=["\'](.*?)["\'](.*?)?>'
      2. Markdown images: ![alt text](media/image1.png){width="..." height="..."}
         Pattern: r'!\\[.*?\\]\\((.*?)(?:\\{.*?\\})?\\)'

    For each image found:
      - Opens with Pillow (handles GIF color mapping that Wand can't)
      - Renames to: <img_dir>/<filename>_imgN.png (sequential numbering)
      - Caps display height at conv_consts.MAX_IMAGE_HEIGHT
      - Replaces original tag with: <img src='./app/<path>' alt='' height=NNN>
        (alt text is initially empty; generate_alt_text() or generate_enhanced_alt_text()
        populates it later)

    Also removes pandoc-generated {width="..." height="..."} attributes and
    ensures each <img> tag is on its own line (\\n\\n prefix).
    """
    try:
        log_message('info', f'Start Processing images for {filename_without_ext}...')
        counter = 1
        # Locate image links


        for match in re.finditer(r'<img.*?src=["\'](.*?)["\'](.*?)?>', markdown_content):
            log_message('info', f'Image counter: {counter}')
            log_message('info', f'Found image link: {match.group(0)}')
            alt_text = ''  # Generally contains the local image file name, so reset it to an empty string

            # Formulate the image path
            image_path = match.group(1).replace('\\', os.sep).replace('/', os.sep)
            log_message('info', f'Image path: {image_path}')

            new_name = os.path.join(img_dir, f"{filename_without_ext}_img{counter}.png")
            log_message("info", f"New Image name: {new_name}")

            if counter >= 367:
                log_message("info", f"Counter: {counter}")
                log_message("info", f"Image path: {image_path}")
                log_message("info", f"New Image name: {new_name}")
            try:
                # DN: Using Pillow, since odd color mapping in the gif file is not being handled by Wand
                image = PILImage.open(image_path.replace('/', os.sep))
                actual_height = image.size[1]
                image_height = min(actual_height, conv_consts.MAX_IMAGE_HEIGHT)
                image.save(new_name)

            except Exception as e:
                log_message("error", f"process_images: Could not load or save image: {e}")
                raise EnvironmentError(f"process_images: Could not load or save image: {e}")

            log_message("info", f"Image saved: {new_name} with height: {image_height}")

            new_name = new_name.replace(os.sep, '/')
            markdown_content = markdown_content.replace(
                match.group(0),
                f"<img src='./app/{new_name}' alt='{alt_text}' height={image_height}>"
            )
            log_message('info', f"Image processed: <img src='./app/{new_name}' alt='{alt_text}' height={image_height}>")
            print(f'Image processed: {new_name}')
            counter += 1

        for match in re.finditer(r'!\[.*?\]\((.*?)(?:\{.*?\})?\)', markdown_content):
            log_message('info', f'Image counter: {counter}')
            log_message('info', f'Found image link: {match.group(0)}')
            alt_text = ''  # Generally contains the local image file name, so reset it to an empty string

            # Formulate the image path
            image_path = match.group(1).replace('\\', os.sep).replace('/', os.sep)
            log_message('info', f'Image path: {image_path}')

            new_name = os.path.join(img_dir, f"{filename_without_ext}_img{counter}.png")
            log_message("info", f"New Image name: {new_name}")

            if counter >= 367:
                log_message("info", f"Counter: {counter}")
                log_message("info", f"Image path: {image_path}")
                log_message("info", f"New Image name: {new_name}")
            try:
                # DN: Using Pillow, since odd color mapping in the gif file is not being handled by Wand
                image = PILImage.open(image_path.replace('/', os.sep))
                actual_height = image.size[1]
                image_height = min(actual_height, conv_consts.MAX_IMAGE_HEIGHT)
                image.save(new_name)

            except Exception as e:
                log_message("error", f"process_images: Could not load or save image: {e}")
                raise EnvironmentError(f"process_images: Could not load or save image: {e}")

            log_message("info", f"Image saved: {new_name} with height: {image_height}")

            new_name = new_name.replace(os.sep, '/')
            markdown_content = markdown_content.replace(
                match.group(0),
                f"<img src='./app/{new_name}' alt='{alt_text}' height={image_height}>"
            )
            log_message('info', f"Image processed: <img src='./app/{new_name}' alt='{alt_text}' height={image_height}>")
            print(f'Image processed: {new_name}')
            counter += 1

        log_message('info', 'Removing {width=".*?" height=".*?"}')
        markdown_content = re.sub(r'\{width=".*?" height=".*?"\}', '', markdown_content)

        markdown_content = re.sub(r'(<img.*?>)', r'\n\n\1', markdown_content)

        return markdown_content

    except Exception as e:
        log_message("error", f"An error occurred in process_images: {e}")
        raise EnvironmentError(f"An error occurred in process_images: {e}")

# The function scans the input text for <img> tags, extracts the value
# of the alt attribute, strips the characters '<', '/', and '>' from
# that alt text, and then reconstructs the image tag with the cleaned
# alt value.
def remove_symbols_within_img_alt(markdown_content):

    """ Parameters
    ----------
    markdown_content : str
        A string containing Markdown content that may include HTML <img> tags.

    Returns
    -------
    str
        A modified version of the input string in which the alt text of all
        <img> tags has been cleaned by removing the characters '<', '/', and '>'.

    Notes
    -----
    - The matching is case-insensitive and supports multi-line tags.
    - Only the alt attribute text is modified; the rest of the tag remains unchanged.
    """

    # Regex to capture the full <img> tag and the value of its alt='...'
    # Group 1: entire <img ...> tag
    # Group 2: content inside the alt attribute quotes

    img_tag_pattern = re.compile(r'(<img\s.*?alt=\'(.*?)\'.*?>)', re.IGNORECASE | re.DOTALL)

    # Function to remove symbols within the alt attribute of img tags
    def remove_symbols(match):
        img_tag = match.group(1)  # Extract the entire img tag
        alt_text = match.group(2)  # Extract the content within the alt attribute
        modified_alt_text = alt_text.replace('<', '').replace('/', '').replace('>', '')
        return f'{img_tag.replace(alt_text, modified_alt_text)}'

    modified_markdown = img_tag_pattern.sub(remove_symbols, markdown_content)

    return modified_markdown

def correct_markdown_formating(markdown_content):
    """
    Clean and normalize Markdown content by removing pandoc-style attributes,
    unwanted formatting artifacts, and certain auto-generated blocks.

    This function performs a series of regex-based transformations to make the
    Markdown more readable and structurally clean. Typical cleanup cases include:
    - Removing `{#id .unnumbered}` fragments while preserving the heading text.
    - Stripping `[link text]{#id .class}` formatting, retaining only the text.
    - Removing empty class anchors such as `[]{#id .class}`.
    - Deleting auto-inserted empty HTML comment blocks like:
        ```{=html}
        <!-- -->
        ```
    - Replacing `[Text]{.smallcaps}` with an uppercase version of `Text`.

    Parameters
    ----------
    markdown_content : str
        Markdown content to be cleaned and normalized.

    Returns
    -------
    str
        The cleaned Markdown string after all formatting corrections.

    Raises
    ------
    EnvironmentError
        Raised when an exception occurs during processing. The original
        exception message is logged and re-wrapped for the caller.

    Notes
    -----
    - Logging is performed at each cleanup step using `log_message(level, message)`.
    - Regexes are intentionally conservative to avoid deleting real content.
    """

    try:
        # Remove inline pandoc section attributes containing `.unnumbered`
        # Example: "## Map Data {#map-data .unnumbered}" → "## Map Data"
        markdown_content = re.sub(r'\{#.*?\.unnumbered\}', '', markdown_content)
        log_message('info', 'Removed .unnumbered sections')

        # Convert "[link text]{#id .class}" → "link text"
        markdown_content = re.sub(r'\[(.*?)\]\{.*?\}', r'\1', markdown_content)
        log_message('info', 'Removed [link text]{#id .class}')

        # Remove empty anchors "[]{#id .class}" entirely
        markdown_content = re.sub(r'\[\]\{.*?\}', '', markdown_content)
        log_message('info', 'Removed []{#id .class}')

        # Delete empty HTML comment fences
        # ```{=html}
        # <!-- -->
        # ```
        markdown_content = re.sub(
            r'```{=html}\n<!-- -->\n```',
            '',
            markdown_content
        )
        log_message('info', 'Removed empty HTML comment block')

        # Convert small-caps formatting to uppercase text
        # Example: "[Example]{.smallcaps}" → "EXAMPLE"
        for match in re.finditer(r'\[(.*?)\]\{\.smallcaps\}', markdown_content):
            markdown_content = markdown_content.replace(
                match.group(0),
                match.group(1).upper()
            )

        return markdown_content

    except Exception as e:
        log_message("error", f"An error occurred in correct_markdown_formating: {e}")
        raise EnvironmentError(
            f"An error occurred in correct_markdown_formating: {e}"
        )

def remove_table_around_equation(markdown_content):
    try:
        # Regular expression pattern to find table rows containing equations
        pattern = r'\|(.*?)(\$.+?\$)(.*?)\|\s*\\\((.*?)\\\)\s*\|'

        def replacer(match):
            equation = match.group(2)
            equation_number = match.group(4)
            return f"{equation} \\({equation_number}\\)"

        modified_content = re.sub(pattern, replacer, markdown_content)

        # Remove following line of dashes and pipes if it exists
        modified_content = re.sub(r'\|\-+\|\-+\|', '', modified_content)

        return modified_content

    except Exception as e:
        log_message("error", f"An error occurred in remove_table_around_equation: {e}")
        raise EnvironmentError(f"An error occurred in remove_table_around_equation: {e}")

def fix_markdown_tables(markdown_content):
    # Split the content into lines for processing
    lines = markdown_content.strip().split('\n')

    # The list to hold our new markdown lines
    new_lines = []

    # Flag to indicate whether the header has been processed
    header_processed = False

    # Regex to match a table row
    table_row_regex = re.compile(r'^\|\s*.*\s*\|$')
    # Regex to match the separator line
    separator_line_regex = re.compile(r'^\|\s*-+\s*\|$')

    # Process each line
    for i, line in enumerate(lines):
        # Check if the line is a table row
        if table_row_regex.match(line):
            # If it's the first row (header), add a separator line after it
            if not header_processed:
                new_lines.append(line)  # Append the header row
                # Generate and append the separator based on the header row
                cells = [cell.strip() for cell in line.strip('|').split('|')]
                separator_line = '|' + '|'.join(['-' * len(cell) for cell in cells]) + '|'
                new_lines.append(separator_line)
                header_processed = True  # Set the flag to True after processing the header
            elif not separator_line_regex.match(line):
                # For non-separator rows after the header, just add them
                new_lines.append(line)
        else:
            # If we reach a non-table line, reset the header_processed flag
            header_processed = False
            new_lines.append(line)

    # Return the fixed markdown content
    return '\n'.join(new_lines)


def md_links2html_links(markdown_content):
    # Replace markdown links with HTML links
    markdown_content = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', markdown_content)

    return markdown_content

def generate_alt_text(markdown_content, markdown_output_file_name):
    try:
        # Find all image tags in the markdown content
        lines = markdown_content.split("\n")

        # Changed this to find all image tags
        img_indices = [i for i, line in enumerate(lines) if line.strip().startswith("<img src='./app")]
        if len(img_indices) > 0:
            for idx in img_indices:
                # Extracting the image path and correcting it
                image_path = lines[idx].split("src='")[1].split("'")[0]
                read_image_path = image_path.replace("./app", "", 1)

                if os.path.exists(read_image_path.replace('/', os.sep)):
                    image_size_kb = os.path.getsize(read_image_path) / 1024.0
                    if image_size_kb <= conv_consts.IGNORE_IMAGE_SIZE_KB:
                        log_message("info", f"Ignoring image of size < 1 KB. Path: {read_image_path}")
                        continue  # Skip to the next image

                top_text, bottom_text, before_para, after_para = find_enclosing_text_around_image(idx, lines)

                log_message("info", f"Image at line {idx+1}")
                log_message("info", f"top_text: {top_text} Size: {len(top_text)}")
                log_message("info", f"bottom_text: {bottom_text} Size: {len(bottom_text)}")
                log_message("info", f"before_para: {before_para} Size: {len(before_para)}")
                log_message("info", f"after_para: {after_para} Size: {len(after_para)}")

                new_alt_text = f"{before_para} {after_para}".replace("\\", "\\\\")
                if new_alt_text:
                    # Safely replace the alt text
                    lines[idx] = re.sub(r"alt='.*?'", f"alt='{new_alt_text}'", lines[idx])
                    log_message("info", f"Context updated for Image {idx + 1}.")
                else:
                    log_message("warning", f"Context not found for Image {idx + 1}.")

            # Write the updated markdown content to file
            updated_markdown_content = "\n".join(lines)
            updated_markdown_content = replace_href_by_string(updated_markdown_content)
            final_markdown_content = correct_alt_text(updated_markdown_content)
            write_markdown_content(final_markdown_content, markdown_output_file_name)
            log_message("info", f"Updated markdown file: {markdown_output_file_name}")
            return updated_markdown_content
        else:
            log_message("warning", "No image tags found.")

    except Exception as e:
        log_message("error", f"An error occurred in generate_alt_text: {e}")
        raise EnvironmentError(f"An error occurred in generate_alt_text: {e}")


def generate_enhanced_alt_text(markdown_content, markdown_output_file_name, source_doc_name, progress_callback=None,
                               summarize_for_bida_text=False, summarize_for_bida_image=False):
    """
    Generate enhanced ALT text using GPT-4o Vision for qualitative OCR.

    This is the V6 enhanced pipeline (replaces generate_alt_text() V5).
    For each image in the markdown:
      1. Extracts raw surrounding text via find_enclosing_text_around_image_raw()
      2. Sends image + context to GPT-4o Vision (via vision_utils.py) for
         qualitative OCR — produces a natural-language description of the screenshot
      3. Composes enhanced ALT text with [CONTEXT], [IMAGE], [NEXT] markers
      4. Returns image_metadata_list for creating the BIDA_images collection

    The qualitative_ocr field becomes the page_content in BIDA_images (Option C:
    search by description only, store raw context in metadata for display).

    Images < conv_consts.IGNORE_IMAGE_SIZE_KB are skipped (tiny decorative elements).

    Note: replace_href_by_string() is called on the final output to strip
    <a href> tags from alt text, since md_links2html_links() may have created
    them in an earlier pipeline stage.

    Args:
        markdown_content: The markdown content with image tags
        markdown_output_file_name: Path to write the updated markdown
        source_doc_name: Name of the source DOCX file
        progress_callback: Optional callback(total_images, processed_count, current_image_name, metrics)
        summarize_for_bida_text: If True, GPT-4o summarizes preceding/following text
            for the enhanced_alt_text stored in <img alt='...'> in BIDA_texts
        summarize_for_bida_image: If True, GPT-4o summarizes preceding/following text
            for page_content (search embeddings) in BIDA_images

    Returns:
        Tuple of (updated_markdown_content, list of image_metadata dicts, VisionMetrics)
    """
    from utils.vision_utils import process_images_batch_with_callback, compose_enhanced_alt_text, VisionMetrics

    try:
        lines = markdown_content.split("\n")
        img_indices = [i for i, line in enumerate(lines) if line.strip().startswith("<img src='./app")]

        image_metadata_list = []
        empty_metrics = VisionMetrics()

        if len(img_indices) == 0:
            log_message("warning", "No image tags found for enhanced alt text generation.")
            if progress_callback:
                progress_callback(0, 0, "", empty_metrics)
            return markdown_content, [], empty_metrics

        # Step 1: Collect all image data for batch processing
        image_data_list = []
        for position, idx in enumerate(img_indices):
            image_path = lines[idx].split("src='")[1].split("'")[0]
            read_image_path = image_path.replace("./app/", "").replace("./app", "")

            # Convert to OS-specific path
            read_image_path_os = read_image_path.replace('/', os.sep)

            # Check if image exists and is large enough
            if not os.path.exists(read_image_path_os):
                log_message("warning", f"Image not found: {read_image_path_os}")
                continue

            image_size_kb = os.path.getsize(read_image_path_os) / 1024.0
            if image_size_kb <= conv_consts.IGNORE_IMAGE_SIZE_KB:
                log_message("info", f"Ignoring small image ({image_size_kb:.1f} KB): {read_image_path_os}")
                continue

            # Extract raw surrounding text
            preceding_text, following_text = find_enclosing_text_around_image_raw(idx, lines)

            image_data = {
                "image_path": read_image_path_os,
                "static_url": image_path,  # Keep the ./app/ prefix for serving
                "preceding_text": preceding_text,
                "following_text": following_text,
                "source_doc": source_doc_name,
                "position": position,
                "line_index": idx
            }
            image_data_list.append(image_data)

            log_message("info", f"Prepared image {position + 1}/{len(img_indices)}: {read_image_path_os}")

        if not image_data_list:
            log_message("warning", "No valid images found for enhanced processing.")
            if progress_callback:
                progress_callback(0, 0, "", empty_metrics)
            return markdown_content, [], empty_metrics

        # Step 2: Process all images with GPT-4o Vision (batch with rate limiting)
        log_message("info", f"Processing {len(image_data_list)} images with GPT-4o Vision...")
        processed_images, vision_metrics = process_images_batch_with_callback(
            image_data_list,
            batch_size=5,
            initial_delay=1.0,
            max_retries=3,
            model="gpt-4o",
            progress_callback=progress_callback,
            summarize_for_bida_text=summarize_for_bida_text,
            summarize_for_bida_image=summarize_for_bida_image
        )

        # Step 3: Update markdown and collect metadata
        for img_data in processed_images:
            idx = img_data["line_index"]
            enhanced_alt_text = img_data["enhanced_alt_text"]

            # Escape special characters for alt attribute
            safe_alt_text = enhanced_alt_text.replace("'", "\\'").replace("\\", "\\\\")

            # Update the alt text in the markdown
            lines[idx] = re.sub(r"alt='.*?'", f"alt='{safe_alt_text}'", lines[idx])
            log_message("info", f"Enhanced alt text applied to image at line {idx + 1}")

            # Prepare metadata for image_collection
            # Option C: Store raw text for display, qualitative_ocr for search
            image_metadata = {
                "image_path": img_data["image_path"],
                "static_url": img_data["static_url"],
                "source_doc": img_data["source_doc"],
                "position": img_data["position"],
                "preceding_text": img_data.get("preceding_text", ""),  # Raw text for display
                "following_text": img_data.get("following_text", ""),  # Raw text for display
                "qualitative_ocr": img_data.get("qualitative_ocr", ""),
                # Note: enhanced_alt_text still used in markdown, but not stored in collection
            }
            # Include summaries when they exist (generated when either summarize flag is True)
            if "preceding_summary" in img_data:
                image_metadata["preceding_summary"] = img_data["preceding_summary"]
            if "following_summary" in img_data:
                image_metadata["following_summary"] = img_data["following_summary"]
            image_metadata_list.append(image_metadata)

        # Step 4: Write updated markdown
        updated_markdown_content = "\n".join(lines)
        updated_markdown_content = replace_href_by_string(updated_markdown_content)
        # Note: We skip correct_alt_text() for enhanced mode to preserve the structured format
        write_markdown_content(updated_markdown_content, markdown_output_file_name)
        log_message("info", f"Updated markdown with enhanced alt text: {markdown_output_file_name}")
        log_message("info", f"Vision API metrics: {vision_metrics}")

        return updated_markdown_content, image_metadata_list, vision_metrics

    except Exception as e:
        log_message("error", f"An error occurred in generate_enhanced_alt_text: {e}")
        raise EnvironmentError(f"An error occurred in generate_enhanced_alt_text: {e}")

def docx2md(DEBUG_DIRECTORY, CONVERSION_DIRECTORY, INGESTION_DIRECTORY, \
            correct_formatting, process_image, format_TOC, file, \
            is_temp_file=False, fix_markdown_table = True):
    """
    Master DOCX-to-Markdown conversion pipeline.

    Takes a .docx file and produces a clean, image-processed markdown file
    ready for ingestion into ChromaDB via loader_utils.py.

    Pipeline stages (each writes a debug file to DEBUG_DIRECTORY):
      1. pypandoc conversion           — DOCX → raw markdown (via run_pypandoc)
      2. NBSP fix                       — replace \\xa0 with regular spaces
      3. Section removal                — strip TOC, Copyright, Index sections
      4. Image processing               — rename/convert images, build <img> tags
      5. Markdown formatting cleanup    — remove pandoc artifacts ({#id .unnumbered}, etc.)
      6. Table fixing                   — ensure proper header/separator structure
      7. TOC link formatting            — convert markdown links to HTML <a> tags
      8. Write to INGESTION_DIRECTORY   — final file for ChromaDB ingestion

    Args:
        DEBUG_DIRECTORY: Where intermediate debug files are saved
        CONVERSION_DIRECTORY: Where pypandoc output is stored
        INGESTION_DIRECTORY: Where final processed markdown is written
        correct_formatting: Whether to run correct_markdown_formating()
        process_image: Whether to run process_images()
        format_TOC: Whether to convert markdown links to HTML
        file: Path to the .docx file
        is_temp_file: Whether this is a temporary upload (not used currently)
        fix_markdown_table: Whether to run fix_markdown_tables()

    Returns:
        Tuple of (markdown_content, markdown_output_file_path)
    """
    ########################################## FILE FUNCTIONS ##################################################
    # 1. construct img directory
    # 2. markdown file name creation
    docx_filename = file
    log_message('info', f'Processing .docx file: {docx_filename}...')

    try:
        filename_without_ext = get_file_name_from_path_no_ext(docx_filename)
        constructed_img_dir = os.path.join(IMG_DIR, filename_without_ext)
        os.makedirs(constructed_img_dir, exist_ok=True)
        log_message('info',f'Constructed image directory: {constructed_img_dir}')
        output_md_file = filename_without_ext + '.md'
    except Exception as e:
        log_message('error', f'Could not construct an image directory or could not save the converted markdown file! {e}')
        raise OSError(f'Could not construct an image directory or could not save the converted markdown file! {e}')

    ########################################## FILE FUNCTIONS ##################################################

    ########################################## PYPANDOC ##################################################

    try:
        run_pypandoc(docx_filename, constructed_img_dir, output_md_file)
    except Exception as e:
        log_message("error", f"pypandoc was not initialized: {e}")
        raise OSError(f"pypandoc was not initialized: {e}")

    ########################################## PYPANDOC ##################################################

    ########################################## DIRECTORY FUNCTIONS ##################################################
    # 1. move pypandoc md file from root to conversion folder
    # 2. track output file of pypandoc
    try:
        output_md_file = move_file_from_root_to_subdirectory(output_md_file, CONVERSION_DIRECTORY)
        log_message('info', f'Moved output md file {output_md_file} to conversion directory {CONVERSION_DIRECTORY}: ' + output_md_file)
    except Exception as e:
        log_message("error", f"move_file_from_root_to_subdirectory: output md file could not be moved to conversion directory ({CONVERSION_DIRECTORY}) {e}")
        raise OSError(f"Could not move md to conversion directory ({CONVERSION_DIRECTORY}): {e}")

    # Read the markdown content from the output file of pypandoc
    try:
        # Track the output file of pypandoc
        save_with_appended_name(output_md_file, DEBUG_DIRECTORY, '_1_pypandoc_output')
        markdown_content = read_markdown_content(output_md_file)
        log_message('info', 'Read markdown content from output file of pypandoc: ' + output_md_file)

        # ── NBSP Fix ──────────────────────────────────
        #
        # DOCX internally represents whitespace between adjacent formatting
        #   runs as non-breaking spaces
        #   (NBSP, Unicode U+00A0, Python '\xa0'). pypandoc faithfully preserves
        #   these in the markdown output — all intermediate pipeline files
        #   (Conversion/, Ingestion/, Debug/) show correct spacing.
        #
        # THE PROBLEM: LangChain's MarkdownHeaderTextSplitter silently strips
        #   '\xa0' characters during split_text(), causing adjacent words to
        #   concatenate in the final ChromaDB data. Examples from the BillTrak
        #   Administrator Guide (578 NBSP instances):
        #     "define\xa0rules"  → "definerules"
        #     "on\xa0the"        → "onthe"
        #     "checkbox\xa0on"   → "checkboxon"
        #     "the\xa0Application" → "theApplication"
        #
        # THE SOLUTION: Replace all '\xa0' with regular spaces ' ' in the markdown content before any further processing.
        # ─────────────────────────────────────────────────────────────────────
        nbsp_count = markdown_content.count('\xa0')
        if nbsp_count > 0:
            markdown_content = markdown_content.replace('\xa0', ' ')
            log_message('info', f'Replaced {nbsp_count} non-breaking spaces (NBSP) with regular spaces')

    except Exception as e:
        log_message('error', f"read_markdown_content: Could not read markdown content from output file of pypandoc {e}")
        raise OSError(f"read_markdown_content: Could not read .md file: {e}")

    ########################################## DIRECTORY FUNCTIONS ##################################################

    ########################################## SECTION REMOVAL ######################################################
    try:
        markdown_content = remove_markdown_sections(markdown_content, SECTIONS_TO_BE_REMOVED)
        log_message("info", "Removed Contents, Copyright Information, Contents table and index")

    except Exception as e:
        log_message("error", f"remove_markdown_sections: Could not remove Sections! {e}")
        raise EnvironmentError(f"remove_markdown_sections: Could not remove Sections! {e}")

    ########################################## SECTION REMOVAL ######################################################

    ########################################## IMAGE PROCESSING ######################################################
    # 1. convert markdown images to html using pillow
    # 2. convert img tags into our format
    # 3. Generate image filename and save it.
    # 4. alt='' and remove any height or width attributes.

    try:
        if process_image:
            markdown_content = process_images(markdown_content, filename_without_ext, constructed_img_dir)
            markdown_content = remove_symbols_within_img_alt(markdown_content)
            log_message('info', f'Processed images for {filename_without_ext}')
            write_markdown_content_appened_filename(markdown_content, filename_without_ext, '_2_precessed_image', DEBUG_DIRECTORY)

    except Exception as e:
        log_message("error",f"process_images: Could not resolve process_images! {e}")
        raise EnvironmentError(f"process_images: Images could not be processed {e}")

    ########################################## IMAGE PROCESSING ######################################################

    ########################################## MD FORMATTING ######################################################

    # 1. Convert [link text]{#id .class} to link text
    # 2. Convert 'some text []{#id .class} more text', to 'some text more text'
    # 3. Delete the empty HTML comment block
    # 4. Remove the .smallcaps class from the text, but apply the uppercase to the text
    # 5. Get rid of the unnumbered hanging blank sections

    try:
        if correct_formatting:
            markdown_content = correct_markdown_formating(markdown_content)
            log_message('info', f'Corrected markdown formatting for {filename_without_ext}')
            write_markdown_content_appened_filename(markdown_content, filename_without_ext, '_3_markdown_formatting', DEBUG_DIRECTORY)
    except Exception as e:
        log_message("error",f"correct_markdown_formating: Could not resolve correct_markdown_formatting! {e}")
        raise EnvironmentError(f"correct_markdown_formating: Formatting could not be processed {e}")

    ########################################## MD FORMATTING ######################################################

    ########################################## MD CLEANUP - LATEX, PIPE AROUND TABLES, EQN2PLCHLDR ######################################################

    # 1. process_latex_equations: convert $$ to $, extract equations in them and remove surronding table or pipe character and return the equations back.
    # 2. remove_table_around_equation: extracts equations(if any) from the table rows, and removes extra pipe chars. It also remove ..-+... lines.

    ########################################## MD CLEANUP - LATEX, PIPE AROUND TABLES, EQN2PLCHLDR ######################################################

    ########################################## FIX MARKDOWN TABLES ######################################################

    # 1. Remove the separator line existing in the table. It is always wrong as generated by pandoc.
    # 2. Put correct separator line.
    # 3. ensure that only 1 separator line has been put, to reduce errors.

    if(fix_markdown_table):
        try:
            markdown_content = fix_markdown_tables(markdown_content)

            log_message('info','Fixed Markdown tables' )

        except Exception as e:
            log_message("error", f"Markdown tables not fixed{e}")
            raise EnvironmentError(f"Tables could not be processed{e}")

    ########################################## FIX MARKDOWN TABLES ######################################################

    if format_TOC:
        try:
            markdown_content = md_links2html_links(markdown_content)

        except Exception as e:
            log_message("error", f"Could not resolve md_links2html_links!{e}")
            raise EnvironmentError("Links could not be processed")

        log_message('info', f'Formatted TOC for {filename_without_ext}')

        write_markdown_content_appened_filename(markdown_content, filename_without_ext, '_6_Format TOC', DEBUG_DIRECTORY)

    try:
        filename_with_ext = get_file_name_with_ext_from_path(output_md_file)
        markdown_output_file_name = INGESTION_DIRECTORY + filename_with_ext
        write_markdown_content(markdown_content, markdown_output_file_name)
        log_message('info', f'~~~~~~~~~~~~~Wrote markdown content to file: {markdown_output_file_name} to ingestion directory {INGESTION_DIRECTORY}')
        return markdown_content, markdown_output_file_name
    except Exception as e:
        log_message("error",f"Could not resolve write_markdown_content!{e}")
        raise OSError("Could not save .md file")
