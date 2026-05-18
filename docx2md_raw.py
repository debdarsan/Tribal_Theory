"""
================================================================================
DOCX to Raw Markdown Converter
================================================================================

PURPOSE:
    This Streamlit application converts Microsoft Word (.docx) files to Markdown
    format. The key feature is that it replaces embedded images with the exact
    text content extracted from those images using OpenAI's GPT-4o Vision model.

WORKFLOW:
    1. User uploads one or more DOCX files through the Streamlit interface
    2. Each file is converted to Markdown using pypandoc (a Python wrapper for Pandoc)
    3. Images embedded in the document are extracted to a temporary directory
    4. For each image, GPT-4o Vision API is called to perform OCR (Optical Character Recognition)
    5. Image tags in the markdown are replaced with ">>> image" followed by the extracted text
    6. The final markdown is saved to the Debug directory as <filename>_RAW.md
    7. The converted markdown is displayed in the UI for review

OUTPUT FORMAT:
    Images in the output will appear as:

    >>> image
    [Exact text extracted from the image by GPT-4o Vision]

DEPENDENCIES:
    - streamlit: Web application framework for the UI
    - pypandoc: Python wrapper for Pandoc document converter
    - openai: OpenAI API client for GPT-4o Vision calls
    - python-dotenv: Load environment variables from .env file (for OPENAI_API_KEY)

AUTHOR: Auto-generated for BIDA-INT project
DATE: January 2026
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

import streamlit as st      # Streamlit framework for building the web UI
import pypandoc             # Python wrapper for Pandoc - converts DOCX to Markdown
import os                   # Operating system interface for file/directory operations
import re                   # Regular expressions for pattern matching in text
import tempfile             # Create temporary files for uploaded DOCX storage
import base64               # Encode images to base64 for API transmission
import time                 # Time delays to avoid API rate limiting
from openai import OpenAI   # OpenAI API client for GPT-4o Vision
from dotenv import load_dotenv  # Load environment variables from .env file

# =============================================================================
# ENVIRONMENT SETUP
# =============================================================================

# Load environment variables from .env file
# This is where the OPENAI_API_KEY should be stored
# The .env file should contain: OPENAI_API_KEY=sk-...
load_dotenv()

# =============================================================================
# CONSTANTS
# =============================================================================

# Directory where the final converted markdown files will be saved
# Format: Debug/<filename>_RAW.md
DEBUG_DIRECTORY = "Debug"

# Temporary directory for storing images extracted from DOCX files during conversion
# Pypandoc extracts embedded images here before we process them with GPT-4o Vision
TEMP_IMG_DIR = "temp_images"

# =============================================================================
# DIRECTORY INITIALIZATION
# =============================================================================

# Create the Debug directory if it doesn't exist
# exist_ok=True prevents error if directory already exists
os.makedirs(DEBUG_DIRECTORY, exist_ok=True)

# Create the temporary images directory if it doesn't exist
# This will hold images extracted from DOCX files during processing
os.makedirs(TEMP_IMG_DIR, exist_ok=True)

# =============================================================================
# GPT-4o VISION PROMPT
# =============================================================================

# This prompt is sent to GPT-4o Vision along with each image
# It instructs the model to extract EXACT text (OCR) rather than describe the image
# Key requirements:
# - Extract ALL visible text without summarization
# - Preserve layout using line breaks
# - Include all UI elements (buttons, labels, menus, etc.)
# - No commentary or explanation - just the raw text
EXACT_OCR_PROMPT = """Extract ALL text visible in this image exactly as it appears.

IMPORTANT RULES:
- Extract every piece of text you can see - labels, buttons, menu items, field names, values, headers, etc.
- Preserve the original layout as much as possible using line breaks
- Include table content row by row
- Do NOT summarize or describe - just extract the exact text
- Do NOT add any commentary or explanation
- If text is unclear, make your best attempt to read it
- Include text from buttons, tabs, navigation, headers, footers, etc.

Output ONLY the extracted text, nothing else."""


# =============================================================================
# OPENAI CLIENT FUNCTION
# =============================================================================

def get_openai_client() -> OpenAI:
    """
    Create and return an OpenAI API client instance.

    The client automatically reads the OPENAI_API_KEY from environment variables.
    This key should be set in the .env file or system environment.

    Returns:
        OpenAI: An initialized OpenAI client ready for API calls

    Note:
        If OPENAI_API_KEY is not set, the OpenAI() constructor will raise an error
    """
    return OpenAI()


# =============================================================================
# IMAGE ENCODING FUNCTION
# =============================================================================

def encode_image_to_base64(image_path: str) -> str:
    """
    Read an image file and encode it to a base64 string.

    GPT-4o Vision API requires images to be sent as base64-encoded strings
    embedded in a data URL format. This function handles the encoding.

    Args:
        image_path (str): The filesystem path to the image file
                         Can be PNG, JPEG, GIF, or other common formats

    Returns:
        str: Base64-encoded string representation of the image
             Returns empty string "" if encoding fails

    Error Handling:
        - If file cannot be read (not found, permission denied, etc.),
          displays error in Streamlit UI and returns empty string

    Example:
        >>> encoded = encode_image_to_base64("screenshot.png")
        >>> print(encoded[:50])  # First 50 chars of base64 string
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ...'
    """
    try:
        # Open image file in binary read mode ("rb")
        # Binary mode is required for non-text files like images
        with open(image_path, "rb") as f:
            # Read entire file content as bytes, encode to base64, then decode to string
            # base64.b64encode() returns bytes, .decode("utf-8") converts to string
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        # Display error in Streamlit UI for user visibility
        st.error(f"Error encoding image {image_path}: {e}")
        # Return empty string to indicate failure (caller should check for this)
        return ""


# =============================================================================
# GPT-4o VISION OCR FUNCTION
# =============================================================================

def extract_text_from_image(image_path: str, model: str = "gpt-4o") -> str:
    """
    Use GPT-4o Vision to extract exact text from an image (OCR).

    This is the core OCR function that sends an image to OpenAI's GPT-4o Vision
    model and receives back the text content visible in the image.

    Args:
        image_path (str): Path to the image file to process
                         Supports PNG, JPEG, and other common formats
        model (str): OpenAI model identifier to use
                    Default is "gpt-4o" which has vision capabilities
                    Could also use "gpt-4o-mini" for lower cost

    Returns:
        str: The extracted text from the image
             Returns error message string if extraction fails

    API Request Structure:
        The GPT-4o Vision API expects messages with multimodal content:
        - A text part containing the prompt/instructions
        - An image_url part containing the base64-encoded image

    Cost Considerations:
        - GPT-4o Vision pricing: ~$2.50/1M input tokens, ~$10/1M output tokens
        - Images are tokenized based on size; "detail": "high" uses more tokens
        - Each image call typically costs $0.01-0.03 depending on image size

    Example:
        >>> text = extract_text_from_image("screenshot.png")
        >>> print(text)
        'File  Edit  View  Help
         New Document
         Open...
         Save'
    """
    # Get an OpenAI client instance
    client = get_openai_client()

    # Encode the image to base64 for API transmission
    base64_image = encode_image_to_base64(image_path)

    # Check if encoding failed (empty string returned)
    if not base64_image:
        return "[Error: Could not read image]"

    # Determine the MIME type based on file extension
    # This is required for the data URL format: data:<mime_type>;base64,<data>
    ext = os.path.splitext(image_path)[1].lower()  # Get extension like ".png"
    media_type = "image/png" if ext == ".png" else "image/jpeg"
    # Note: For simplicity, treating all non-PNG as JPEG
    # In practice, could add more types: .gif -> image/gif, .webp -> image/webp

    try:
        # Make the API call to GPT-4o Vision
        response = client.chat.completions.create(
            model=model,  # The model to use (gpt-4o has vision capabilities)
            messages=[
                {
                    "role": "user",  # Message from the "user" role
                    "content": [
                        # First content part: The text prompt with OCR instructions
                        {
                            "type": "text",
                            "text": EXACT_OCR_PROMPT
                        },
                        # Second content part: The image to analyze
                        {
                            "type": "image_url",
                            "image_url": {
                                # Data URL format: data:<mime>;base64,<encoded_data>
                                "url": f"data:{media_type};base64,{base64_image}",
                                # "high" detail mode for better OCR accuracy
                                # Uses more tokens but extracts text more accurately
                                # Alternative: "low" for faster/cheaper processing
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            # Maximum tokens in the response
            # 2000 is generous for OCR output; most screenshots need less
            max_tokens=2000
        )

        # Extract the text content from the API response
        # response.choices[0] = first (and usually only) completion choice
        # .message.content = the actual text content of the response
        # .strip() removes leading/trailing whitespace
        return response.choices[0].message.content.strip()

    except Exception as e:
        # Return error message if API call fails
        # Common failures: rate limiting, invalid API key, network issues
        return f"[Error extracting text: {e}]"


# =============================================================================
# MAIN CONVERSION FUNCTION
# =============================================================================

def convert_docx_to_raw_markdown(docx_path: str, filename: str, progress_callback=None) -> tuple:
    """
    Convert a DOCX file to raw markdown with exact text extraction from images.

    This is the main conversion function that orchestrates the entire process:
    1. Convert DOCX to Markdown using pypandoc
    2. Find all image references in the markdown
    3. For each image, call GPT-4o Vision to extract text
    4. Replace image tags with ">>> image" + extracted text
    5. Clean up markdown formatting artifacts
    6. Save the result to the Debug directory

    Args:
        docx_path (str): Full path to the DOCX file to convert
                        This should be a valid .docx file
        filename (str): Base filename without extension
                       Used for naming the output file and image directory
        progress_callback (callable, optional): Function to call for progress updates
                                               Signature: callback(current, total, image_name)

    Returns:
        tuple: A 3-element tuple containing:
            - markdown_content (str): The converted markdown with image text
            - image_count (int): Total number of images found and processed
            - output_path (str): Path where the markdown file was saved

    Raises:
        Exception: If pypandoc conversion fails

    Process Details:
        - Pypandoc extracts images to temp_images/<filename>/ directory
        - Two regex patterns catch different image formats:
          1. HTML-style: <img src="path">
          2. Markdown-style: ![alt](path)
        - Images < 1KB are skipped (likely decorative icons)
        - 0.5 second delay between API calls to avoid rate limiting
    """

    # -------------------------------------------------------------------------
    # STEP 1: Create temporary directory for extracted images
    # -------------------------------------------------------------------------

    # Build path for this document's images: temp_images/<filename>/
    img_dir = os.path.join(TEMP_IMG_DIR, filename)

    # Create the directory if it doesn't exist
    os.makedirs(img_dir, exist_ok=True)

    # -------------------------------------------------------------------------
    # STEP 2: Convert DOCX to Markdown using pypandoc
    # -------------------------------------------------------------------------

    try:
        # pypandoc.convert_file() calls the Pandoc executable
        # Arguments:
        #   - docx_path: Input file path
        #   - 'markdown': Output format
        #   - extra_args: Additional Pandoc command-line arguments
        #     --extract-media: Extract embedded media (images) to specified directory
        markdown_content = pypandoc.convert_file(
            docx_path,
            'markdown',
            extra_args=['--extract-media', img_dir]
        )
    except Exception as e:
        # Re-raise with more descriptive message
        raise Exception(f"Pypandoc conversion failed: {e}")

    # -------------------------------------------------------------------------
    # STEP 3: Find all image references in the markdown
    # -------------------------------------------------------------------------

    # Pattern 1: HTML-style image tags
    # Matches: <img src="path/to/image.png"> or <img src='path/to/image.png'>
    # Also handles additional attributes: <img src="..." alt="..." width="...">
    # Captures the path in group 1
    img_pattern1 = re.compile(r'<img[^>]*src=["\']([^"\']+)["\'][^>]*>')

    # Pattern 2: Markdown-style image syntax
    # Matches: ![alt text](path/to/image.png)
    # The .*? matches any alt text (non-greedy)
    # Captures the path in group 1
    img_pattern2 = re.compile(r'!\[.*?\]\(([^)]+)\)')

    # List to store all found images with their positions
    # Each entry is a dict with: full_match, path, start position, end position
    images = []

    # Find all HTML-style images
    for match in img_pattern1.finditer(markdown_content):
        images.append({
            'full_match': match.group(0),  # The entire matched string
            'path': match.group(1),         # Just the image path
            'start': match.start(),         # Start position in the text
            'end': match.end()              # End position in the text
        })

    # Find all Markdown-style images
    for match in img_pattern2.finditer(markdown_content):
        images.append({
            'full_match': match.group(0),
            'path': match.group(1),
            'start': match.start(),
            'end': match.end()
        })

    # -------------------------------------------------------------------------
    # STEP 4: Sort and deduplicate images
    # -------------------------------------------------------------------------

    # Sort by position in REVERSE order (highest position first)
    # This is crucial! When we replace text, we start from the END of the document
    # If we started from the beginning, our position indices would become invalid
    # after the first replacement (because the text length changes)
    images.sort(key=lambda x: x['start'], reverse=True)

    # Remove duplicates (same image might be matched by both patterns)
    # We use start position as the unique identifier
    seen_positions = set()
    unique_images = []
    for img in images:
        if img['start'] not in seen_positions:
            seen_positions.add(img['start'])
            unique_images.append(img)

    # Replace the list with deduplicated version
    images = unique_images
    total_images = len(images)

    # Report initial progress if callback provided
    if progress_callback:
        progress_callback(0, total_images, "Found images...")

    # -------------------------------------------------------------------------
    # STEP 5: Process each image
    # -------------------------------------------------------------------------

    for i, img in enumerate(images):
        image_path = img['path']

        # ---------------------------------------------------------------------
        # STEP 5a: Resolve the image path
        # ---------------------------------------------------------------------

        # Check if the path is relative (not absolute)
        if not os.path.isabs(image_path):
            # Try multiple possible path resolutions
            # Different systems/Pandoc versions may format paths differently
            possible_paths = [
                image_path,  # As-is
                os.path.join(os.path.dirname(docx_path), image_path),  # Relative to DOCX
                image_path.replace('\\', '/'),  # Unix-style separators
                image_path.replace('/', os.sep)  # OS-native separators
            ]

            # Try each possible path until we find one that exists
            resolved_path = None
            for p in possible_paths:
                if os.path.exists(p):
                    resolved_path = p
                    break

            # If image not found with any path resolution
            if not resolved_path:
                # Create replacement text indicating the image was not found
                replacement = f"\n\n>>> image\n[Image not found: {image_path}]\n\n"

                # Replace the image tag with the error message
                # Using string slicing: text[:start] + replacement + text[end:]
                markdown_content = (
                    markdown_content[:img['start']] +
                    replacement +
                    markdown_content[img['end']:]
                )
                # Skip to next image
                continue

            # Use the resolved path
            image_path = resolved_path

        # ---------------------------------------------------------------------
        # STEP 5b: Update progress
        # ---------------------------------------------------------------------

        if progress_callback:
            # Report current progress: which image we're processing
            progress_callback(i + 1, total_images, os.path.basename(image_path))

        # ---------------------------------------------------------------------
        # STEP 5c: Process the image
        # ---------------------------------------------------------------------

        # Verify image file exists
        if os.path.exists(image_path):
            # Get file size in kilobytes
            file_size_kb = os.path.getsize(image_path) / 1024

            if file_size_kb < 1:
                # Skip very small images (< 1KB)
                # These are typically decorative icons, bullets, or spacer images
                # Not worth the API cost and don't contain meaningful text
                replacement = "\n\n>>> image\n[Small decorative image skipped]\n\n"
            else:
                # Extract text from the image using GPT-4o Vision
                extracted_text = extract_text_from_image(image_path)

                # Create the replacement text with ">>> image" marker
                replacement = f"\n\n>>> image\n{extracted_text}\n\n"

                # Add a small delay between API calls to avoid rate limiting
                # OpenAI has rate limits on requests per minute
                # 0.5 seconds = max 120 requests per minute (well under limits)
                time.sleep(0.5)
        else:
            # Image file doesn't exist at the resolved path
            replacement = f"\n\n>>> image\n[Image not found: {image_path}]\n\n"

        # ---------------------------------------------------------------------
        # STEP 5d: Replace the image tag with extracted text
        # ---------------------------------------------------------------------

        # String slicing to replace the matched text
        # Since we're processing in reverse order, positions remain valid
        markdown_content = (
            markdown_content[:img['start']] +  # Everything before the image tag
            replacement +                       # Our new text with extracted content
            markdown_content[img['end']:]      # Everything after the image tag
        )

    # -------------------------------------------------------------------------
    # STEP 6: Clean up markdown formatting
    # -------------------------------------------------------------------------

    # Remove Pandoc artifacts and excessive whitespace
    markdown_content = clean_markdown(markdown_content)

    # -------------------------------------------------------------------------
    # STEP 7: Save the result
    # -------------------------------------------------------------------------

    # Build output filename: <original_name>_RAW.md
    output_filename = f"{filename}_RAW.md"

    # Build full path: Debug/<original_name>_RAW.md
    output_path = os.path.join(DEBUG_DIRECTORY, output_filename)

    # Write the markdown content to file
    # encoding='utf-8' ensures proper handling of special characters
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(markdown_content)

    # Return the results
    return markdown_content, total_images, output_path


# =============================================================================
# MARKDOWN CLEANUP FUNCTION
# =============================================================================

def clean_markdown(content: str) -> str:
    """
    Clean up common markdown formatting issues introduced by Pandoc.

    Pandoc sometimes adds extra attributes and formatting that we don't need.
    This function removes those artifacts to produce cleaner markdown.

    Args:
        content (str): Raw markdown content from Pandoc conversion

    Returns:
        str: Cleaned markdown with artifacts removed

    Artifacts Removed:
        1. {#section-id} - Pandoc section ID attributes
        2. {.unnumbered} - Pandoc class for unnumbered headings
        3. []{#...} - Empty anchor links with IDs
        4. ```{=html}<!-- -->``` - Empty HTML comment blocks
        5. Excessive newlines (4+ consecutive) reduced to 3
    """

    # Remove Pandoc section ID attributes
    # Example: "## My Section {#my-section}" -> "## My Section "
    # Pattern: {# followed by anything except }, then }
    content = re.sub(r'\{#[^}]*\}', '', content)

    # Remove unnumbered class attribute
    # Example: "## Introduction {.unnumbered}" -> "## Introduction "
    content = re.sub(r'\{\.unnumbered\}', '', content)

    # Remove empty anchor links
    # Example: "[]{#some-id .some-class}" -> ""
    # These are invisible anchors Pandoc creates for cross-referencing
    content = re.sub(r'\[\]\{[^}]*\}', '', content)

    # Remove empty HTML comment blocks that Pandoc sometimes generates
    # These appear as fenced code blocks containing only an HTML comment
    content = re.sub(r'```\{=html\}\n<!-- -->\n```', '', content)

    # Clean up excessive newlines
    # Replace 4 or more consecutive newlines with exactly 3
    # This preserves paragraph breaks while removing excessive spacing
    content = re.sub(r'\n{4,}', '\n\n\n', content)

    return content


# =============================================================================
# STREAMLIT MAIN FUNCTION
# =============================================================================

def main():
    """
    Main function that sets up and runs the Streamlit web application.

    This function:
    1. Configures the Streamlit page settings
    2. Displays the UI with file uploader
    3. Handles file uploads and conversion
    4. Shows progress during processing
    5. Displays results and conversion summary

    UI Components:
        - Title and description
        - Multi-file uploader (accepts .docx files)
        - "Convert All Files" button
        - Progress bar and status text for each file
        - Expandable section showing converted markdown
        - Summary of all conversions at the end
    """

    # -------------------------------------------------------------------------
    # Page Configuration
    # -------------------------------------------------------------------------

    # Configure Streamlit page settings
    # This must be the first Streamlit command in the script
    st.set_page_config(
        page_title="DOCX to Raw Markdown",  # Browser tab title
        page_icon="📄",                      # Browser tab icon (emoji or URL)
        layout="wide"                        # Use full page width
    )

    # -------------------------------------------------------------------------
    # Header Section
    # -------------------------------------------------------------------------

    # Main title
    st.title("DOCX to Raw Markdown Converter")

    # Description/instructions
    st.markdown("""
    Upload DOCX files to convert them to markdown. Images will be replaced with
    `>>> image` followed by the exact text extracted using GPT-4o Vision.
    """)

    # -------------------------------------------------------------------------
    # File Upload Section
    # -------------------------------------------------------------------------

    # Create file uploader widget
    # accept_multiple_files=True allows batch processing
    uploaded_files = st.file_uploader(
        "Upload DOCX files",           # Label text
        type=['docx'],                 # Restrict to .docx files only
        accept_multiple_files=True     # Allow multiple file selection
    )

    # -------------------------------------------------------------------------
    # Processing Section (only shown when files are uploaded)
    # -------------------------------------------------------------------------

    if uploaded_files:
        # Show count of selected files
        st.write(f"**{len(uploaded_files)} file(s) selected**")

        # Convert button - type="primary" makes it visually prominent
        if st.button("Convert All Files", type="primary"):

            # List to store results for summary
            results = []

            # Process each uploaded file
            for uploaded_file in uploaded_files:

                # -----------------------------------------------------------------
                # File Header
                # -----------------------------------------------------------------

                # Show horizontal line and filename being processed
                st.markdown(f"---\n### Processing: `{uploaded_file.name}`")

                # -----------------------------------------------------------------
                # Save to Temporary File
                # -----------------------------------------------------------------

                # Streamlit's uploaded file is in memory; we need it on disk for pypandoc
                # NamedTemporaryFile creates a file that persists until explicitly deleted
                # delete=False: Don't auto-delete when closed (we need it for pypandoc)
                # suffix='.docx': Ensure correct file extension
                with tempfile.NamedTemporaryFile(delete=False, suffix='.docx') as tmp:
                    # Write the uploaded file content to temp file
                    tmp.write(uploaded_file.getvalue())
                    # Store the path for later use
                    tmp_path = tmp.name

                # Extract filename without extension for output naming
                filename = os.path.splitext(uploaded_file.name)[0]

                # -----------------------------------------------------------------
                # Progress Tracking Setup
                # -----------------------------------------------------------------

                # Create a progress bar widget (initially at 0%)
                progress_bar = st.progress(0)

                # Create an empty placeholder for status text
                # Using empty() allows us to update the text in place
                status_text = st.empty()

                # Define callback function for progress updates
                # This will be called by convert_docx_to_raw_markdown after each image
                def update_progress(current, total, image_name):
                    """
                    Update the progress bar and status text.

                    Args:
                        current: Number of images processed so far
                        total: Total number of images to process
                        image_name: Name of the current image being processed
                    """
                    if total > 0:
                        # Calculate progress as fraction (0.0 to 1.0)
                        progress = current / total
                        # Update progress bar
                        progress_bar.progress(progress)
                        # Update status text
                        status_text.text(f"Processing image {current}/{total}: {image_name}")
                    else:
                        # No images in document
                        status_text.text("Converting document...")

                # -----------------------------------------------------------------
                # Conversion Process
                # -----------------------------------------------------------------

                try:
                    # Call the main conversion function
                    markdown_content, image_count, output_path = convert_docx_to_raw_markdown(
                        tmp_path,                      # Path to temp DOCX file
                        filename,                      # Base filename for output
                        progress_callback=update_progress  # Progress update function
                    )

                    # Set progress to 100% when complete
                    progress_bar.progress(1.0)
                    status_text.text(f"Complete! Processed {image_count} images.")

                    # Store successful result
                    results.append({
                        'filename': uploaded_file.name,
                        'output_path': output_path,
                        'image_count': image_count,
                        'content': markdown_content,
                        'success': True
                    })

                    # -----------------------------------------------------------------
                    # Display Results
                    # -----------------------------------------------------------------

                    # Show converted markdown in an expandable section
                    # expanded=True means it starts open (user can collapse)
                    # {len(markdown_content):,} formats number with commas (e.g., 1,234)
                    with st.expander(f"View Converted Markdown ({len(markdown_content):,} chars)", expanded=True):
                        # Display as code block with markdown syntax highlighting
                        st.code(markdown_content, language='markdown')

                    # Show success message with output path
                    st.success(f"Saved to: `{output_path}`")

                except Exception as e:
                    # -----------------------------------------------------------------
                    # Error Handling
                    # -----------------------------------------------------------------

                    # Display error message
                    st.error(f"Error converting {uploaded_file.name}: {e}")

                    # Store failed result
                    results.append({
                        'filename': uploaded_file.name,
                        'success': False,
                        'error': str(e)
                    })

                finally:
                    # -----------------------------------------------------------------
                    # Cleanup
                    # -----------------------------------------------------------------

                    # Always delete the temporary file, even if conversion failed
                    # This prevents accumulation of temp files
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)  # unlink = delete file

            # =====================================================================
            # CONVERSION SUMMARY
            # =====================================================================

            st.markdown("---\n## Conversion Summary")

            # Count successful conversions
            successful = sum(1 for r in results if r['success'])

            # Display overall success rate
            st.write(f"**{successful}/{len(results)}** files converted successfully")

            # List each file with its result
            for r in results:
                if r['success']:
                    # Show filename, output path, and image count
                    st.write(f"- {r['filename']} -> `{r['output_path']}` ({r['image_count']} images)")
                else:
                    # Show filename and error message
                    st.write(f"- {r['filename']} - **Failed**: {r.get('error', 'Unknown error')}")


# =============================================================================
# SCRIPT ENTRY POINT
# =============================================================================

# This block runs only when the script is executed directly
# (not when imported as a module)
# Streamlit runs this file directly, so main() will be called
if __name__ == "__main__":
    main()
