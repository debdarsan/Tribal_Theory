import streamlit as st
import re
from consts.consts import *
import streamlit.components.v1 as components
from streamlit_star_rating import st_star_rating
from vars.s_state import *
from html_css_templates import *
from utils.init_app_utils import *
from consts.consts import *
from utils.logging_utils import *
from utils.json_utils import *
from utils.chat_helper import *
import string
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
try:
    import markdown
    MARKDOWN_AVAILABLE = True
except ImportError:
    MARKDOWN_AVAILABLE = False


def simple_markdown_to_html(text: str) -> str:
    """Simple markdown to HTML converter that handles malformed and inline tables."""

    # Pre-process: Handle inline tables (tables that don't start at beginning of line)
    # Look for pattern: text | Field | Value | and split into separate lines
    def normalize_inline_tables(content):
        # Find inline tables: non-pipe content followed by | content |
        # Pattern: text followed by | that starts a table row
        result = []
        lines = content.split('\n')

        for line in lines:
            # Check if line has table content not at the start
            # Pattern: some text followed by | Field | ... |
            match = re.match(r'^(.+?)\s*(\|\s*[^|\n]+\s*\|.*)$', line)
            if match:
                prefix = match.group(1).strip()
                table_part = match.group(2).strip()

                # Check if prefix doesn't look like part of a table
                if prefix and not prefix.startswith('|') and '|' not in prefix:
                    # Split: add prefix as separate line, then table part
                    result.append(prefix)
                    result.append(table_part)
                    continue

            result.append(line)

        return '\n'.join(result)

    text = normalize_inline_tables(text)

    lines = text.split('\n')
    result_lines = []
    in_table = False
    table_rows = []

    for line in lines:
        stripped = line.strip()

        # Check if this is a table line (starts with | or contains | pattern)
        if '|' in stripped:
            # Check if separator row (only dashes, colons, pipes, spaces)
            if re.match(r'^[\|\-:\s]+$', stripped):
                continue  # Skip separator rows

            # Check if it's a table row with actual content
            cells = [c.strip() for c in stripped.split('|')]
            # Remove empty cells from start/end
            if cells and cells[0] == '':
                cells = cells[1:]
            if cells and cells[-1] == '':
                cells = cells[:-1]

            # Only treat as table if we have cells with content
            if cells and any(c for c in cells):
                if not in_table:
                    in_table = True
                    table_rows = []
                table_rows.append(cells)
                continue

        # Not a table line - close any open table first
        if in_table:
            result_lines.append(build_html_table(table_rows))
            in_table = False
            table_rows = []

        # Process non-table content
        # Convert headers: ### ## # ######
        if stripped.startswith('###### '):
            line = f'<h6 style="margin:6px 0; color:#87CEEB;">{stripped[7:]}</h6>'
        elif stripped.startswith('##### '):
            line = f'<h5 style="margin:7px 0; color:#87CEEB;">{stripped[6:]}</h5>'
        elif stripped.startswith('#### '):
            line = f'<h4 style="margin:8px 0; color:#87CEEB;">{stripped[5:]}</h4>'
        elif stripped.startswith('### '):
            line = f'<h4 style="margin:8px 0; color:#87CEEB;">{stripped[4:]}</h4>'
        elif stripped.startswith('## '):
            line = f'<h3 style="margin:10px 0; color:#87CEEB;">{stripped[3:]}</h3>'
        elif stripped.startswith('# '):
            line = f'<h2 style="margin:12px 0; color:#87CEEB;">{stripped[2:]}</h2>'
        else:
            # Blockquote
            if stripped.startswith('> ') or stripped == '>':
                bq_content = stripped[2:] if stripped.startswith('> ') else ''
                if bq_content.strip():
                    bq_content = convert_inline_markdown(bq_content)
                    line = f'<blockquote style="border-left:3px solid #555; padding:5px 10px; margin:5px 0; color:#ccc; background:#1a1a2e;">{bq_content}</blockquote>'
                else:
                    line = ''
            # Convert bullet lists
            elif stripped.startswith('- '):
                line = f'<li>{convert_inline_markdown(stripped[2:])}</li>'
            # Convert numbered lists (1. 2. 3. etc.)
            elif re.match(r'^\d+\.\s', stripped):
                content = re.sub(r'^\d+\.\s', '', stripped)
                line = f'<li>{convert_inline_markdown(content)}</li>'
            else:
                # Convert inline markdown (bold, italic) with spacing fix
                line = convert_inline_markdown(line)

        result_lines.append(line)

    # Close any remaining open table
    if in_table:
        result_lines.append(build_html_table(table_rows))

    # Join and convert remaining line breaks
    html = '<br>'.join(result_lines)

    # Wrap consecutive <li> items in <ul>
    html = re.sub(r'((?:<li>.*?</li><br>?)+)', r'<ul>\1</ul>', html)

    return html


def build_html_table(rows: list) -> str:
    """Build an HTML table from a list of rows (each row is a list of cells)."""
    if not rows:
        return ''

    html = '<table style="border-collapse:collapse; margin:10px 0; width:100%; border:1px solid #555;">'

    for i, row in enumerate(rows):
        html += '<tr>'
        tag = 'th' if i == 0 else 'td'  # First row as header
        style = 'padding:8px 12px; text-align:left; border:1px solid #555;'
        if i == 0:
            style += ' background-color:#2a4a6a; font-weight:bold; color:#fff;'
        else:
            # Alternate row colors for readability
            bg_color = '#1a1a2e' if i % 2 == 0 else '#16213e'
            style += f' background-color:{bg_color};'
        for cell in row:
            cell = convert_inline_markdown(cell)
            html += f'<{tag} style="{style}">{cell}</{tag}>'
        html += '</tr>'

    html += '</table>'
    return html


def convert_markdown_to_html(text: str, font_size: str = "14px") -> str:
    """
    Convert markdown text to HTML for display inside HTML containers.

    Args:
        text: Markdown text to convert
        font_size: CSS font size for the text

    Returns:
        HTML string with markdown converted
    """
    try:
        # Preserve raw HTML <table>...</table> blocks before markdown conversion.
        # simple_markdown_to_html() joins lines with <br>, which inserts invalid
        # <br> tags between HTML table elements (<table><br><colgroup>...) and
        # breaks the table layout. Extract them first, convert the rest, then
        # reinsert the original HTML tables.
        html_table_placeholders = {}
        preserved_text = text

        def replace_html_table(match):
            placeholder_id = f"%%HTMLTABLE{len(html_table_placeholders)}%%"
            html_table_placeholders[placeholder_id] = match.group(0)
            return placeholder_id

        preserved_text = re.sub(
            r'<table\b[^>]*>.*?</table>',
            replace_html_table,
            preserved_text,
            flags=re.DOTALL
        )

        # Check if text contains tables (has | characters in multiple lines)
        # Use our custom handler for tables since it handles malformed tables better
        lines_with_pipes = [l for l in preserved_text.split('\n') if '|' in l]
        has_table = len(lines_with_pipes) >= 2

        if has_table:
            # Use custom converter for tables (handles malformed tables)
            html_content = simple_markdown_to_html(preserved_text)
        elif MARKDOWN_AVAILABLE:
            # Use markdown library for non-table content
            html_content = markdown.markdown(
                preserved_text,
                extensions=['fenced_code', 'nl2br']
            )
        else:
            # Use simple fallback converter
            html_content = simple_markdown_to_html(preserved_text)

        # Post-process to catch any remaining **bold** or ***bold italic***
        # markers that the markdown library didn't convert (e.g. mid-word
        # emphasis like "the**next**transition" is skipped by smart_strong).
        # convert_inline_markdown() also adds spaces between word characters
        # and formatting tags to prevent words from running together.
        html_content = convert_inline_markdown(html_content)

        # Reinsert preserved HTML tables
        for placeholder_id, original_table in html_table_placeholders.items():
            html_content = html_content.replace(placeholder_id, original_table)

        # Wrap in a div with font size; color inherits from parent so
        # light/dark themes both render correctly
        return f"""<div style='font-size:{font_size};'>{html_content}</div>"""
    except Exception as e:
        log_message("warning", f"Markdown conversion failed: {e}")
        # Fallback: return text wrapped in pre tag (color inherits)
        return f"""<pre style='font-size:{font_size}; white-space:pre-wrap;'>{text}</pre>"""


def convert_img_tags_to_embedded(text: str) -> str:
    """
    Convert <img> tags with local file paths to embedded base64 images.

    Handles <img src='./app/static/...' alt='...' height=300> tags
    that appear in page_content from the text collection. The alt text
    (which may contain HTML fragments) is stripped to prevent
    fix_malformed_angle_brackets() from corrupting the tag.

    Args:
        text: Text containing <img> HTML tags with local src paths

    Returns:
        Text with <img> tags replaced with base64-embedded images
    """
    import os

    # Pattern to match <img> tags with src pointing to ./app/static/
    # The alt text can contain: > characters (HTML fragments), unescaped '
    # after \\ (e.g. \\'Invalid Taxes\\'), and newlines. Rather than parsing
    # the alt value character-by-character, we use non-greedy .*? and anchor
    # to the required height=NNN> at the end of the tag. Since "height="
    # never appears inside the alt text, .*? correctly expands past any
    # intermediate ' characters until it reaches ' height=\d+>.
    pattern = r"<img\s+src='(\./app/static/[^']+)'(?:\s+alt='.*?')?\s*(?:height=\d+\s*)?>"

    def replace_img_tag(match):
        src = match.group(1)

        # Convert ./app/ path to actual file path
        img_path = src.replace('./app/', '').replace('/', os.sep)

        # Encode image as base64
        data_uri = encode_image_to_base64(img_path)
        if data_uri:
            return f"<img src='{data_uri}' style='max-width: 100%; height: auto; border: 1px solid #555; border-radius: 4px; margin: 10px 0;'>"
        else:
            return f"<span style='color:#FF6B6B;'>[Image not found: {img_path}]</span>"

    return re.sub(pattern, replace_img_tag, text, flags=re.DOTALL)


def convert_image_urls_to_embedded(text: str) -> str:
    """
    Convert image URL references in text to embedded base64 images.

    Handles patterns like:
    - ![alt text](./app/static/path/image.png) - markdown image syntax
    - URL: [./app/static/path/image.png](./app/static/path/image.png)
    - [./app/static/path/image.png](./app/static/path/image.png)

    Args:
        text: Text containing image URL references

    Returns:
        Text with image URLs replaced with embedded images
    """
    import os

    # Pattern to match markdown images and links to image files
    # Matches: ![alt](url), URL: [text](url), [text](url) for image files
    pattern = r'(?:URL:\s*)?!?\[([^\]]*)\]\(([^\)]+\.(?:png|jpg|jpeg|gif))\)'

    def replace_with_image(match):
        link_text = match.group(1)
        url = match.group(2)

        # Convert ./app/ path to actual file path
        img_path = url.replace('./app/', '').replace('/', os.sep)

        # Encode image as base64
        data_uri = encode_image_to_base64(img_path)
        if data_uri:
            # Include caption if alt text is meaningful (not just the filename)
            caption_html = ""
            if link_text and not link_text.endswith(('.png', '.jpg', '.jpeg', '.gif')):
                caption_html = f"""<p style='color:#90EE90; font-size:12px; font-style:italic; margin-top:5px;'>{link_text}</p>"""
            return f"""<img src='{data_uri}' style='max-width: 100%; height: auto; border: 1px solid #555; border-radius: 4px; margin: 10px 0;'>{caption_html}"""
        else:
            return f"""<span style='color:#FF6B6B;'>[Image not found: {img_path}]</span>"""

    return re.sub(pattern, replace_with_image, text)

def correct_angle_brackets_with_flags(s: str) -> str:
    stack = []
    keep = [True] * len(s)

    in_math = False
    in_code = False
    i = 0

    while i < len(s):
        # Check for code block start/end (```), must be at beginning of line or standalone
        if s[i:i+3] == '```':
            in_code = not in_code
            i += 3
            continue

        # Check for inline math ($)
        if s[i] == '$':
            in_math = not in_math
            i += 1
            continue

        # Only process angle brackets if not inside math or code
        if not in_math and not in_code:
            if s[i] == '<':
                stack.append(i)
            elif s[i] == '>':
                if stack:
                    stack.pop()
                else:
                    keep[i] = False  # unmatched '>'

        i += 1

    # Remove unmatched '<' from the stack
    for index in stack:
        keep[index] = False

    # Build the corrected string
    corrected = ''.join(s[i] for i in range(len(s)) if keep[i])
    return corrected


def fix_malformed_angle_brackets(s: str) -> str:
    chars = list(s)
    pointer = -1
    residue = 0
    removal_flag = 0

    for i, char in enumerate(chars):
        if char == '<':
            if pointer != -1:
                # Invalidate previous `<`
                chars[pointer] = ''  # Remove it
                residue += 1
            pointer = i  # New unmatched <
        elif char == '>':
            if residue > 0 and residue == 1:
                removal_flag = 1
                residue -= 1
            elif residue > 0 and residue > 1:
                residue -= 1
            elif residue == 0 and removal_flag == 1:
                chars[i] = ''
                removal_flag = 0
                pointer = -1
            elif pointer != -1 and residue == 0:
                pointer = -1  # Clear pointer, we closed it
    return ''.join(chars)

def encode_image_to_base64(image_path: str) -> str:
    """
    Encode an image file to base64 data URI for embedding in HTML.

    Args:
        image_path: Path to the image file

    Returns:
        Base64 data URI string or empty string if file not found
    """
    import base64
    import os

    if not os.path.exists(image_path):
        log_message("warning", f"Image not found for display: {image_path}")
        return ""

    try:
        # Determine MIME type
        ext = os.path.splitext(image_path)[1].lower()
        mime_type = "image/png" if ext == ".png" else "image/jpeg"

        with open(image_path, "rb") as img_file:
            img_data = base64.b64encode(img_file.read()).decode("utf-8")
            return f"data:{mime_type};base64,{img_data}"
    except Exception as e:
        log_message("error", f"Error encoding image {image_path}: {e}")
        return ""


def convert_inline_markdown(text: str) -> str:
    """
    Convert inline markdown formatting to HTML.
    Handles ***bold italic***, **bold**, __bold__, and *italic* within text
    that will be embedded inside HTML tags where Streamlit won't process
    markdown. Also adds spaces between word characters and formatting tags
    to prevent words from running together (e.g. "the**next**transition"
    renders as "the next transition").

    Uses [^*\\n]+ instead of .+? to prevent matching across asterisk
    boundaries in malformed markdown (e.g. "***next**.*However" won't
    cause the regex to greedily span huge chunks of text looking for a
    distant closing ***).
    """
    # Bold+italic: ***text*** (must come before ** and * patterns)
    text = re.sub(r'\*\*\*([^*\n]+)\*\*\*', r'<strong><em>\1</em></strong>', text)
    # Bold: **text** or __text__
    text = re.sub(r'\*\*([^*\n]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
    # Italic: *text* (including mid-word like disputes*not*created)
    text = re.sub(r'\*([^*\n]+)\*', r'<em>\1</em>', text)
    # Clean up orphaned markdown asterisks left from malformed patterns
    # (e.g. "***next**.*" leaves stray * after bold/italic conversion fails).
    # Strip 1-3 asterisks at boundaries between text and punctuation/tags.
    text = re.sub(r'(?<=[\s.,;:!?])\*{1,3}(?=\w)', '', text)
    text = re.sub(r'(?<=\w)\*{1,3}(?=[\s.,;:!?])', '', text)
    text = re.sub(r'(?<=\w)\*{1,3}(?=<)', '', text)
    text = re.sub(r'(?<=>)\*{1,3}(?=[\w.,;:!?])', '', text)
    text = re.sub(r'^\*{1,3}(?=\w)', '', text)
    text = re.sub(r'(?<=\w)\*{1,3}$', '', text)
    # Add spaces between word characters and formatting tags to prevent
    # words from running together when markers were adjacent to text
    text = re.sub(r'(\w)(<(?:strong|em)>)', r'\1 \2', text)
    text = re.sub(r'(</(?:strong|em)>)(\w)', r'\1 \2', text)
    # Fix missing spaces between punctuation and formatting tags
    # (source data often has no space: "example,**Manager**" or "to**A/P Send**")
    text = re.sub(r'([.,;:!?])(<(?:strong|em)>)', r'\1 \2', text)
    # Fix missing space after sentence-ending punctuation before a capital letter
    # (e.g. ".However" → ". However" from malformed source like "**.*However")
    text = re.sub(r'([.!?])([A-Z])', r'\1 \2', text)
    return text


def format_image_doc_html(doc, counter):
    """
    Format an image document for HTML display with the actual image.

    Args:
        doc: Document object from image collection
        counter: Document counter for display

    Returns:
        HTML string for the image document
    """
    import os

    metadata = doc.metadata if hasattr(doc, 'metadata') else {}
    static_url = metadata.get('static_url', '')
    source_doc = metadata.get('source_doc', 'Screenshot')
    qualitative_ocr = metadata.get('qualitative_ocr', '')
    preceding_text = metadata.get('preceding_text', '')
    following_text = metadata.get('following_text', '')

    # Clean up backslash escape artifacts, convert inline markdown to HTML
    # (since text is embedded in HTML tags where Streamlit won't process
    # markdown), and replace newlines with <br> to prevent paragraph breaks.
    if qualitative_ocr:
        qualitative_ocr = qualitative_ocr.replace('\\"', '"').replace("\\'", "'").replace('\\$', '$')
        qualitative_ocr = convert_inline_markdown(qualitative_ocr)
        qualitative_ocr = qualitative_ocr.replace('\n', '<br>')
    if preceding_text:
        preceding_text = _strip_table_fragment(preceding_text)
        preceding_text = preceding_text.replace('\\"', '"').replace("\\'", "'").replace('\\$', '$')
        preceding_text = convert_inline_markdown(preceding_text)
        preceding_text = preceding_text.replace('\n', '<br>')
    if following_text:
        following_text = _strip_table_fragment(following_text)
        following_text = following_text.replace('\\"', '"').replace("\\'", "'").replace('\\$', '$')
        following_text = convert_inline_markdown(following_text)
        following_text = following_text.replace('\n', '<br>')

    # Theme-aware accent colors. The original palette (sky blue, light
    # green, light orange, light grey) was chosen for a dark background;
    # in light mode those colors disappear into the page. Detect the
    # active theme by checking the user's text color luminance.
    theme = _theme_accents()
    value_color = ss.get('__text_color', '#1A1A2E')

    # Build HTML for image display
    html = f"""<p><span style='color:{theme['heading']}; font-size:15px;'><strong>{counter}. Screenshot from {source_doc}</strong></span></p>"""

    # Display preceding context (no colored background — keeps the panel
    # neutral and readable in both themes)
    if preceding_text:
        html += f"""<p style='padding:4px 0; margin:5px 0;'><span style='color:{theme['preceding']}; font-size:12px;'><strong>Preceding Context:</strong></span><br><span style='color:{value_color}; font-size:12px;'>{preceding_text}</span></p>"""

    # Display the actual image if URL is available
    if static_url:
        # Convert ./app/ path to actual file path
        img_path = static_url.replace('./app/', '').replace('/', os.sep)

        # Encode image as base64 data URI for embedding in HTML
        data_uri = encode_image_to_base64(img_path)
        if data_uri:
            html += f"""<p><img src='{data_uri}' style='max-width: 100%; height: auto; border: 1px solid #555; border-radius: 4px; margin: 10px 0;'></p>"""
        else:
            html += f"""<p><span style='color:#DC2626; font-size:12px;'>[Image not found: {img_path}]</span></p>"""

    # Display the qualitative OCR description as caption
    if qualitative_ocr:
        html += f"""<p><span style='color:{theme['description']}; font-size:12px;'><strong>Description:</strong> <em>{qualitative_ocr}</em></span></p>"""

    # Display following context (no colored background, see above)
    if following_text:
        html += f"""<p style='padding:4px 0; margin:5px 0;'><span style='color:{theme['following']}; font-size:12px;'><strong>Following Context:</strong></span><br><span style='color:{value_color}; font-size:12px;'>{following_text}</span></p>"""

    return html


def _strip_table_fragment(text: str) -> str:
    """Truncate preceding/following context text at the first table marker.

    During ingestion, the text captured around an image sometimes ends in
    a partial table (HTML <table>/<tr>/<td>... or a markdown |---|---|
    separator). When that fragment renders, the user sees a half-rendered
    table where the rest was chopped off. Cleaner to drop everything from
    the start of the table onward — the prose before it is still useful,
    the table fragment is not.
    """
    if not text:
        return text

    # 1) HTML table fragment: cut at the first table-family tag.
    m = re.search(
        r'<(?:table|tbody|thead|tfoot|tr|td|th)\b',
        text,
        flags=re.IGNORECASE,
    )
    if m:
        text = text[:m.start()].rstrip()

    # 2) Markdown table separator |---|---|. The line ABOVE it is usually
    #    the header row — drop both, plus everything that follows.
    m = re.search(r'\n[ \t]*\|[\s\-:|]+\|[ \t]*(?:\n|$)', text)
    if m:
        cut_at = m.start()
        # Look backward for the header row (preceding line containing |)
        prev_nl = text.rfind('\n', 0, cut_at)
        if prev_nl >= 0 and '|' in text[prev_nl + 1:cut_at]:
            cut_at = prev_nl
        text = text[:cut_at].rstrip()

    return text


def _theme_accents():
    """Return accent colors that contrast with the active theme background.

    Determined by inspecting `__text_color`: a light text color implies
    dark theme (so we keep bright accents); a dark text color implies
    light theme (so we shift to deeper accents that read on white).
    """
    text_color = ss.get('__text_color', '#F5F5F5').lstrip('#')
    try:
        r = int(text_color[0:2], 16)
        g = int(text_color[2:4], 16)
        b = int(text_color[4:6], 16)
        is_dark_theme = (r + g + b) > 380  # text is light → dark theme
    except Exception:
        is_dark_theme = True

    if is_dark_theme:
        return {
            'heading':     '#FDD017',  # gold
            'context':     '#87CEEB',  # sky blue
            'preceding':   '#87CEEB',
            'description': '#90EE90',  # light green
            'following':   '#e8a87c',  # light orange
        }
    return {
        'heading':     '#8B6508',  # deep gold readable on white
        'context':     '#1E5AA8',  # deep blue
        'preceding':   '#1E5AA8',
        'description': '#15803D',  # forest green
        'following':   '#B45309',  # amber
    }


def format_bot_response(bot_response):
    try:
        if "result" in bot_response.keys():
            if(bot_response["greet_flag"]):
                answer = (bot_response["result"])
                source_docs = 0
            else:
                answer, source_docs = (
                    bot_response["result"],
                    [] if not ss.return_source_docs else bot_response["source_documents"],
                )
        else:
            if(bot_response["greet_flag"]):
                answer = (bot_response["answer"])
                source_docs = 0
            else:
                answer, source_docs = (
                    bot_response["answer"],
                    [] if not ss.return_source_docs else bot_response["source_documents"],
                )

        # Removing square brackets from the beginning and end of the string
        if answer.startswith("[") and answer.endswith("]"):
            answer = answer[1:-1]
        else:
            answer = answer

        # Collapse blank line between a numbered item and its first sub-bullet
        # so "1. Heading:" and its bullets render tight. Permissive on bullet
        # indent ([ \t]*) because LLMs emit bullets at column 0 or indented.
        # We deliberately do NOT collapse the blank line between the LAST
        # sub-bullet and the NEXT numbered item — that gap visually separates
        # consecutive steps.
        answer = re.sub(r'(\d+\.\s.+)\n\n([ \t]*[-*]\s)', r'\1\n\2', answer)

        # Convert <img> tags (from source text) and markdown image URLs to embedded base64
        answer = convert_img_tags_to_embedded(answer)
        answer = convert_image_urls_to_embedded(answer)

        # Markdown tables don't render inside the <div class="message"> wrapper
        # because Streamlit treats raw HTML blocks as opaque. Convert them to
        # <table> HTML so they render correctly. Must run BEFORE inline-markdown
        # so the inline pass doesn't trip over remaining `|` chars.
        from utils.sys_utils import convert_markdown_tables
        answer = convert_markdown_tables(answer)

        # Convert inline markdown to HTML since the answer is rendered inside
        # an HTML <div> (bot_template) where Streamlit may not process markdown
        answer = convert_inline_markdown(answer)

        formatted_bot_response = answer
        # Critical: the following line is necessary to display equations correctly, for whatever reason
        formatted_bot_response = "\n" + "\n" + formatted_bot_response
        if all(string not in answer for string in strings_to_check_in_response):
            formatted_bot_response = formatted_bot_response + "\n" + "\n"
            if source_docs:
                # Separate text and image documents
                text_docs = []
                image_docs = []
                if source_docs != []:
                    for doc in source_docs:
                        metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                        if metadata.get('collection_type') == 'image':
                            image_docs.append(doc)
                        else:
                            text_docs.append(doc)

                # Display text sources
                if text_docs:
                    docs_html = f"""<details><summary>Text Sources</summary>"""
                    doc_counter = 1
                    # Theme-aware accents (see _theme_accents)
                    _ts_theme = _theme_accents()
                    _ts_value_color = ss.get('__text_color', '#1A1A2E')
                    for doc in text_docs:
                        page_content, metadata = parse_document(doc)
                        if metadata:
                            # HITL-validated entries don't have a File field;
                            # label them by the contributor instead so the
                            # reviewer can tell user-added content apart from
                            # document chunks.
                            if metadata.get("source") == "hitl_validated":
                                _contrib = metadata.get("original_contributor") or "user"
                                source_doc_name = f"Information added by {_contrib}"
                            else:
                                source_doc_name = metadata.get("File") or "Information added by user"
                            page_content = convert_img_tags_to_embedded(page_content)
                            page_content = fix_malformed_angle_brackets(page_content)

                        docs_html += f"""<p><span style='color:{_ts_theme['heading']}; font-size:15px;'><strong>{doc_counter}. {source_doc_name}</strong></span></p>"""

                        # Build context path from metadata fields
                        if metadata:
                            context_parts = []
                            for field in ["File", "Section", "Subsection", "Subsubsection", "Subsubsubsection"]:
                                value = metadata.get(field, "")
                                if value and value.strip():
                                    context_parts.append(value.strip())

                            if context_parts:
                                context_path = ", ".join(context_parts)
                                docs_html += f"""<p><span style='color:{_ts_theme['context']}; font-size:12px;'><strong>Context:</strong> <span style='color:{_ts_value_color};'>{context_path}</span></span></p>"""

                        # Remove "Context: ..." prefix from page_content if present
                        source_text = page_content.strip()
                        if source_text.startswith("Context:"):
                            # Find where actual content starts (after the metadata path)
                            # The metadata path ends and content begins - look for the content after last metadata item
                            if metadata:
                                # Get the last non-empty metadata value
                                last_meta = None
                                for field in ["Subsubsubsection", "Subsubsection", "Subsection", "Section", "File"]:
                                    value = metadata.get(field, "")
                                    if value and value.strip():
                                        last_meta = value.strip()
                                        break

                                if last_meta and last_meta in source_text:
                                    # Find position after the last metadata item
                                    pos = source_text.find(last_meta)
                                    if pos != -1:
                                        pos += len(last_meta)
                                        source_text = source_text[pos:].lstrip(', ').strip()
                                else:
                                    # Fallback: just remove "Context: " prefix
                                    source_text = source_text[8:].strip()
                            else:
                                source_text = source_text[8:].strip()

                        # Clean up backslash escape artifacts from document storage
                        source_text = source_text.replace('\\"', '"').replace("\\'", "'").replace('\\$', '$')

                        # Convert markdown to HTML so it renders inside the <details> tag
                        docs_html += convert_markdown_to_html(source_text, font_size="14px")

                        doc_counter += 1
                    docs_html += """</details>"""
                    formatted_bot_response += docs_html

                # Display image sources (screenshots) - folded by default
                if image_docs:
                    img_html = f"""<details><summary>Related Screenshots</summary>"""
                    img_counter = 1
                    for doc in image_docs:
                        img_html += format_image_doc_html(doc, img_counter)
                        img_counter += 1
                    img_html += """</details>"""
                    formatted_bot_response += img_html

        return formatted_bot_response
    except Exception as e:
        log_message("error", f"Error formatting bot response {str(e)}")
        raise

def display_QA(qa_history, show_appraise_controls, skip_rated=False) -> None:
    """
    Displays the Question and Answer (QA) history in a conversational format.

    Example usage:
        qa_history = {
            'historical_prompts': ['What is your name?', 'What do you do?'],
            'historical_responses': ['I am a bot.', 'I answer questions.']
        }
        display_QA(qa_history)
    """
    st.write(css_old, unsafe_allow_html=True)
    if is_qa_history_not_empty(qa_history):
        try:
            if 'saved_qas' not in st.session_state:
                st.session_state.saved_qas = set() 
            for id, (user_prompt, bot_response) in enumerate(
                zip(
                    reversed(qa_history["historical_prompts"]),
                    reversed(qa_history["historical_responses"]),
                )
            ):
                if skip_rated:
                    # Check if the "Appraiser" field is already populated
                    if bot_response.get("Appraiser"):
                        continue  # Skip this QA pair if it has been appraised
                    
                disp_user_prompt = user_template.replace("{{MSG}}", user_prompt)
                formatted_bot_response = format_bot_response(bot_response)
                disp_bot_response = bot_template.replace("{{MSG}}", formatted_bot_response)
                st.markdown(disp_user_prompt, unsafe_allow_html=True)
                st.markdown(disp_bot_response, unsafe_allow_html=True)

                if show_appraise_controls:
                # Retrieve saved star rating and comment if they exist
                    saved_stars = bot_response.get("Rating", 3)  # Default to 3 if not found
                    saved_comment = bot_response.get("Comment", "")  # Default to empty if not found 
                    
                    # Display star rating and comment area with saved values
                    stars = st_star_rating("", maxValue=5, defaultValue=saved_stars, size=20, key=f"star_{id}_{ss._qa_filename}")
                    comment = st.text_area("", placeholder="Add a comment?", height=5, value=saved_comment, key=f"comment_{id}")
                    
                    if st.button(label="Save", key=f"save_{id}"):
                        save_appraised_qa_json(ss._QA_DIRECTORY, ss._qa_filename, qa_history, id, stars, comment, ss.user_name)
                        st.session_state.saved_qas.add(id)
                        st.rerun()
        except Exception as e:
            log_message("error", f"display_qa error: {e}")
            raise
        
def save_appraised_qa_json(DIRECTORY, qa_filename, qa_history, id, stars, comment, appraiser_name):
    try:
        # Get the current date and time for Appraised_Date
        appraised_date = get_date_time_stamp()

        # Update the qa_history with the appraisal information
        # Assuming that the id is used to index into historical_responses
        qa_pair = qa_history["historical_responses"][-(id+1)]
        qa_pair["Appraiser"] = appraiser_name
        qa_pair["Appraised_Date"] = appraised_date
        qa_pair["Rating"] = stars
        qa_pair["Comment"] = comment

        # Save the updated qa_history to a file (or handle as needed)
        save_qa_history(DIRECTORY, qa_filename, qa_history)
        st.rerun()

    except Exception as e:
        st.error(f"Error saving QA appraisal: {e}")