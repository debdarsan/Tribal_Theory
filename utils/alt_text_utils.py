import re
from utils.logging_utils import *
from utils.string_utils import *


def find_enclosing_text_around_image_raw(image_tag_line_index, lines, max_lines=15):
    """
    Extract raw text surrounding an image without sanitization.
    Used for enhanced ALT text generation with GPT-4o Vision.

    Args:
        image_tag_line_index: Line number where the image tag is located
        lines: List of all markdown content lines
        max_lines: Maximum lines to look backward/forward (default 15)

    Returns:
        Tuple of (preceding_text, following_text) as raw strings
    """
    preceding_lines = []
    following_lines = []

    # Extract preceding text (go backwards from image)
    for i in reversed(range(max(0, image_tag_line_index - max_lines), image_tag_line_index)):
        line = lines[i].strip()

        # Stop at another image
        if line.startswith('<img'):
            break

        # Stop at major headers (but include them as context)
        if line.startswith('#'):
            preceding_lines.insert(0, line)
            break

        # Skip empty lines at the boundary
        if not line and not preceding_lines:
            continue

        preceding_lines.insert(0, line)

    # Extract following text (go forward from image)
    for i in range(image_tag_line_index + 1, min(len(lines), image_tag_line_index + max_lines + 1)):
        line = lines[i].strip()

        # Stop at another image
        if line.startswith('<img'):
            break

        # Stop at major headers (but include them as context)
        if line.startswith('#'):
            following_lines.append(line)
            break

        # Skip empty lines at the boundary
        if not line and not following_lines:
            continue

        following_lines.append(line)

    # Join lines with spaces, filter out image tags that might be inline
    preceding_text = ' '.join([l for l in preceding_lines if not l.startswith('<img')])
    following_text = ' '.join([l for l in following_lines if not l.startswith('<img')])

    # Basic cleanup: condense multiple spaces
    preceding_text = re.sub(r'\s+', ' ', preceding_text).strip()
    following_text = re.sub(r'\s+', ' ', following_text).strip()

    return preceding_text, following_text


def find_enclosing_text_around_image(image_tag_line_index, lines, max_lines=10, encapsulating_lines=2):

    top_text = ''
    bottom_text = ''
    before_para = ''
    after_para = ''

    # Initialize an empty list to store each line for top_text
    top_text_list = []

    # For top_text
    for i in reversed(range(max(0, image_tag_line_index - max_lines), image_tag_line_index)):
        log_message('info', 'Image: ' + str(i))
        log_message('info', f"Line: {lines[i]}")
        if lines[i].strip().startswith('<img'):
            break
        if lines[i].startswith('#') or lines[i].startswith('##') or lines[i].startswith('###') or lines[i].startswith('**') or lines[i].startswith('*'):
            top_text_list = lines[i:image_tag_line_index]
            top_text = '\n'.join(top_text_list)
            break
        else:
            # Append the current line to top_text_list
            top_text_list.insert(0, lines[i])
            top_text = '\n'.join(top_text_list)

    # For bottom_text
    for i in range(image_tag_line_index + 1, min(len(lines), image_tag_line_index + max_lines + 1)):
        if lines[i].strip().startswith('<img'):
            break
        if lines[i].startswith('#') or lines[i].startswith('##') or lines[i].startswith('###') or lines[i].startswith('**') or lines[i].startswith('*'):
            bottom_text = '\n'.join(lines[image_tag_line_index + 1:i + 1])
            break

    # For before_para and after_para
    before_para = ''
    after_para = ''

    for i in reversed(range(max(0, image_tag_line_index - max_lines), image_tag_line_index)):
        if re.search(r'Fig\.|Figure|Fig ', lines[i]):
            before_para = lines[i]
            break
        # Stop adding sentences if these characters are encountered
        elif lines[i].strip().startswith(('#', '##', '###', '####', '**')):
            break
        else:  # If not found, get the last sentences before the image
            text_before = " ".join(lines[max(0, image_tag_line_index - max_lines):image_tag_line_index])
            sentences_before = re.split(r'(?<=[.!?]) +', text_before)
            # Filter sentences that contain "<img src"
            sentences_before = [s for s in sentences_before if '<img src' not in s]
            before_para = " ".join(sentences_before[-encapsulating_lines:])

    for i in range(image_tag_line_index + 1, min(len(lines), image_tag_line_index + max_lines + 1)):
        if re.search(r'Fig\.|Figure|Fig ', lines[i]):
            after_para = lines[i]
            break
        # Stop adding sentences if these characters are encountered
        elif lines[i].strip().startswith(('#', '##', '###', '####', '**')):
            break
        else:  # If not found, get the first sentences after the image
            text_after = " ".join(lines[image_tag_line_index + 1:min(len(lines), image_tag_line_index + max_lines + 1)])
            sentences_after = re.split(r'(?<=[.!?]) +', text_after)
            # Filter sentences that contain "<img src"
            sentences_after = [s for s in sentences_after if '<img src' not in s]
            after_para = " ".join(sentences_after[:encapsulating_lines])

    # Added this to replace single quotes with double quotes
    top_text = delete_chars_and_condense_spaces(top_text, '\'\""|', condense_spaces=True)
    bottom_text = delete_chars_and_condense_spaces(bottom_text, '\'\""|', condense_spaces=True)
    before_para = delete_chars_and_condense_spaces(before_para, '\'\""|', condense_spaces=True)
    after_para = delete_chars_and_condense_spaces(after_para, '\'\""|', condense_spaces=True)


    return top_text, bottom_text, before_para, after_para


def replace_href_by_string(text):
    """
    Replaces patterns like <a href='#...'>text</a> with just the text.
    """
    return re.sub(r"<a href=['\"][^'\"]*['\"]>(.*?)</a>", r'\1', text)

def find_img_tags(markdown_text):
    """
    Identifies <img> tags in the provided markdown text and returns their alt texts.
    """
    # Adjusted pattern to handle alt text containing single quotes
    img_pattern = r"<img\s+[^>]*alt='(.*?)(?:' height=|'>)"
    img_tags = re.findall(img_pattern, markdown_text, re.DOTALL)
    return img_tags

def remove_pattern(text, start_pattern, end_pattern):
    """
    Removes text between specified start and end patterns.

    Parameters:
    text (str): The input text.
    start_pattern (str): The starting pattern.
    end_pattern (str): The ending pattern.

    Returns:
    str: Text with the specified patterns removed.
    """
    pattern = f"{re.escape(start_pattern)}.*?{re.escape(end_pattern)}"
    return re.sub(pattern, end_pattern, text)

def replace_characters_and_condense_spaces_regex(text, chars_to_replace, to_be_replaced_by, condense_spaces=False):
    """
    Replaces a set of characters in the text using a regular expression and optionally condenses consecutive spaces.
    """
    # Create a regular expression pattern for characters to be replaced
    pattern = f"[{''.join(map(re.escape, chars_to_replace))}]"

    # Replace specified characters using regular expression
    for replacement in to_be_replaced_by:
        text = re.sub(pattern, replacement, text)

    # Condense consecutive spaces if required
    if condense_spaces:
        text = re.sub(r'\s+', ' ', text)

    return text

def replace_string_encl_by_characters_and_condense_spaces(text, chars_to_replace, to_be_replaced_by, condense_spaces=False, left_char='<', right_char='>'):
    """
    Replaces a set of characters in the text, removes content enclosed by specific characters,
    and optionally condenses consecutive spaces.
    """
    # Replace specified characters
    for char, replacement in zip(chars_to_replace, to_be_replaced_by):
        text = text.replace(char, replacement)

    # Remove content enclosed by left_char and right_char
    enclosed_content_pattern = f'{re.escape(left_char)}.*?{re.escape(right_char)}'
    text = re.sub(enclosed_content_pattern, '', text)

    # Condense consecutive spaces if required
    if condense_spaces:
        text = re.sub(r'\s+', ' ', text)

    return text

def sanitize_al_text(alt_text, chars_to_replace, to_be_replaced_by, start_pattern='height=', end_pattern='>', left_char='<', right_char='>', condense_spaces=True):

    alt_text = replace_characters_and_condense_spaces_regex(alt_text, chars_to_replace, to_be_replaced_by, condense_spaces=True)
    log_message("info", f"[blue] 2. Replaced characters and condensed spaces: {alt_text}\n")
    alt_text = replace_string_encl_by_characters_and_condense_spaces(alt_text, chars_to_replace, to_be_replaced_by, condense_spaces=False, left_char=left_char, right_char=right_char)
    log_message("info", f"[blue] 3. Replaced string enclosed by characters and condensed spaces: {alt_text}\n")
    alt_text = remove_pattern(alt_text, start_pattern, end_pattern)
    log_message("info", f"4. Replaced string enclosed by start and end patterns: {alt_text}\n")

    return alt_text

def clean_nested_img_tags_in_alt(outer_html):
    """
    In the outermost <img> tags, replace all instances of nested <img> tags
    with just their 'alt' text, while keeping the outer <img> tags intact.
    """
    def replace_nested_img_with_alt(match):
        # Extract the complete outer <img> tag and the alt attribute
        outer_img_tag = match.group(0)
        alt_attr = match.group(1)

        # Replace nested <img> tags within the alt attribute
        nested_img_pattern = r"<img\s+[^>]*alt='(.*?)'[^>]*>"
        cleaned_alt = re.sub(nested_img_pattern, r'\1', alt_attr)

        # Construct the new outer <img> tag with the cleaned alt attribute
        new_outer_img_tag = re.sub(r"alt='.*?'", f"alt='{cleaned_alt}'", outer_img_tag)

        return new_outer_img_tag

    # Regular expression to find outer <img> tags
    outer_img_pattern = r"(<img\s+[^>]*alt='(.*?)'[^>]*>)"

    # Replace nested <img> tags in all alt attributes of outer <img> tags
    cleaned_html = re.sub(outer_img_pattern, replace_nested_img_with_alt, outer_html)

    return cleaned_html

def replace_alt_in_img_tags(original_content, img_tags, modified_tags):
    """
    Replaces the alt text in <img> tags with modified tag values.

    Parameters:
    original_content (str): The original markdown content.
    img_tags (list): List of original alt texts of <img> tags.
    modified_tags (list): List of modified alt texts.

    Returns:
    str: The markdown content with replaced alt text in <img> tags.
    """
    modified_content = original_content
    for original, modified in zip(img_tags, modified_tags):
        # Create the original and new alt attribute
        original_alt = f"alt='{original}'"
        modified_alt = f"alt='{modified}'"

        # Replace the original alt attribute with the modified one
        modified_content = modified_content.replace(original_alt, modified_alt)

    return modified_content

def correct_alt_text(markdown_content):

    img_tags = find_img_tags(markdown_content)
    log_message("info", "found all img tags")

    cleaned_img_tags = [clean_nested_img_tags_in_alt(tag) for tag in img_tags]
    log_message("info", "cleaned all img tags")

    chars_to_replace = ["'", '"', '*', '[', ']', '(', ')', '{', '}', '+', '-', '!', '`', '_', '#', '|', '~', ':', ';', '<', '>', '=', '?', '/', "\\*", "\\[", "\\]"]
    to_be_replaced_by = [""] * len(chars_to_replace) # Replace with empty string
    delete_chars = '|'
    start_pattern = 'height='
    end_pattern = '>'
    left_char = '<'
    right_char = '>'

    processed_tags = [sanitize_al_text(tag, chars_to_replace, to_be_replaced_by) for tag in cleaned_img_tags]
    log_message("info", "Alt text extracted")

    new_markdown_content = replace_alt_in_img_tags(markdown_content, img_tags, processed_tags)

    return new_markdown_content
