import re


def extract_without_breaking_words(text: str, max_chars: int) -> str:
    """
    Extract a substring from text up to max_chars without breaking words.

    Args:
        text: The input text string
        max_chars: Maximum number of characters to extract

    Returns:
        A substring that doesn't exceed max_chars and doesn't break words
    """
    if not text:
        return ""

    # If text is shorter than max_chars, return as is
    if len(text) <= max_chars:
        return text.strip()

    # Find the last space before max_chars
    truncated = text[:max_chars]
    last_space = truncated.rfind(' ')

    if last_space > 0:
        return truncated[:last_space].strip()
    else:
        # No space found, return truncated text
        return truncated.strip()


_QUESTION_STARTERS = {
    'how', 'what', 'when', 'where', 'why', 'who', 'which',
    'can', 'could', 'is', 'are', 'was', 'were', 'do', 'does', 'did',
    'will', 'would', 'should', 'shall', 'may', 'might', 'must', 'have', 'has',
}


def enhance_question_for_llm(question: str, suffix: str = " Explain with images") -> str:
    """Append an LLM-only instruction to the question, ensuring a terminating
    punctuation mark precedes it. Uses '?' if the first word looks like a
    question starter, else '.'. Empty input returns empty.

    Applied only to the text sent to the LLM, not to retrieval or UI history.
    """
    q = question.rstrip() if question else ""
    if not q:
        return q

    if q[-1] not in ".!?":
        first_word = q.split(maxsplit=1)[0].lower().strip(",:;'\"")
        q += "?" if first_word in _QUESTION_STARTERS else "."

    return q + suffix


def delete_chars_and_condense_spaces(text, chars_to_delete, condense_spaces=False):
    """
    Deletes a set of characters from the text and optionally condenses consecutive spaces.

    Parameters:
    text (str): The input text.
    chars_to_delete (str): A string containing all characters to be deleted.
    condense_spaces (bool): If True, consecutive spaces will be condensed into a single space.

    Returns:
    str: The modified text.
    """
    # Create a regular expression pattern for characters to be deleted
    pattern = f'[{re.escape(chars_to_delete)}]'

    # Delete specified characters
    text = re.sub(pattern, '', text)

    # Condense consecutive spaces if required
    if condense_spaces:
        text = re.sub(r'\s+', ' ', text)

    return text
