"""
Vision utilities for GPT-4o Vision integration.
Provides qualitative OCR for screenshots and text summarization for enhanced ALT text generation.
"""

import os
import base64
import time
from typing import List, Dict, Optional, Tuple, Callable
from openai import OpenAI
from dotenv import load_dotenv
from utils.logging_utils import log_message

# Load environment variables
load_dotenv()

# GPT-4o pricing (per 1M tokens) - updated as of 2024
GPT4O_INPUT_PRICE_PER_1M = 2.50  # $2.50 per 1M input tokens
GPT4O_OUTPUT_PRICE_PER_1M = 10.00  # $10.00 per 1M output tokens

# Metrics tracking class
class VisionMetrics:
    """Track metrics for vision API calls."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_time_seconds = 0.0
        self.api_calls = 0
        self.images_processed = 0

    def add_usage(self, input_tokens: int, output_tokens: int, elapsed_time: float):
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_time_seconds += elapsed_time
        self.api_calls += 1

    def add_image(self):
        self.images_processed += 1

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def estimated_cost(self) -> float:
        input_cost = (self.total_input_tokens / 1_000_000) * GPT4O_INPUT_PRICE_PER_1M
        output_cost = (self.total_output_tokens / 1_000_000) * GPT4O_OUTPUT_PRICE_PER_1M
        return input_cost + output_cost

    def to_dict(self) -> Dict:
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "total_time_seconds": round(self.total_time_seconds, 2),
            "api_calls": self.api_calls,
            "images_processed": self.images_processed,
            "estimated_cost_usd": round(self.estimated_cost, 4)
        }

    def __str__(self) -> str:
        return (
            f"Images: {self.images_processed}, "
            f"API Calls: {self.api_calls}, "
            f"Tokens: {self.total_tokens:,} (in: {self.total_input_tokens:,}, out: {self.total_output_tokens:,}), "
            f"Time: {self.total_time_seconds:.1f}s, "
            f"Cost: ${self.estimated_cost:.4f}"
        )


# Global metrics instance
_current_metrics = VisionMetrics()

# Prompts for GPT-4o
QUALITATIVE_OCR_PROMPT = """Analyze this screenshot from a software user guide. Describe it QUALITATIVELY.

DESCRIBE:
- UI layout sections (header, navigation, main content, sidebars)
- Types of input fields and their purpose
- Table columns and what data categories they represent
- Visual indicators (warning icons, checkmarks, color coding)
- Available buttons and actions
- What workflow step this screen represents

DO NOT INCLUDE:
- Specific account numbers, IDs, or reference codes
- Dollar amounts or numeric values
- Dates shown in fields
- Sample vendor or customer names
- Any data that is clearly example/test data

Write 2-4 sentences focusing on what a user can DO on this screen and what UI elements are available."""

SUMMARIZE_PRECEDING_PROMPT = """Summarize this instructional text in 1-2 sentences.
Focus on:
- What ACTION the user is being instructed to perform
- What CONCEPT is being explained
- How this step fits in the overall workflow

If the text is very short or unclear, summarize what you can understand.

Text:
{text}"""

SUMMARIZE_FOLLOWING_PROMPT = """Summarize this instructional text in 1-2 sentences.
Focus on:
- What ACTION comes NEXT after the current step
- What CONCEPT is being explained
- How this connects to the previous step

If the text is very short or unclear, summarize what you can understand.

Text:
{text}"""


def get_openai_client() -> OpenAI:
    """Get or create OpenAI client."""
    return OpenAI()


def encode_image_to_base64(image_path: str) -> Optional[str]:
    """
    Encode an image file to base64 string.

    Args:
        image_path: Path to the image file

    Returns:
        Base64 encoded string or None if file not found
    """
    try:
        if not os.path.exists(image_path):
            log_message("error", f"Image file not found: {image_path}")
            return None

        with open(image_path, "rb") as image_file:
            return base64.standard_b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        log_message("error", f"Error encoding image {image_path}: {e}")
        return None


def qualitative_ocr(image_path: str, model: str = "gpt-4o", metrics: VisionMetrics = None) -> Tuple[str, Dict]:
    """
    Call GPT-4o Vision to describe screenshot qualitatively.

    Args:
        image_path: Path to the screenshot image
        model: OpenAI model to use (default: gpt-4o)
        metrics: Optional VisionMetrics instance to track usage

    Returns:
        Tuple of (Qualitative description, usage_dict with tokens and time)
    """
    client = get_openai_client()
    usage_info = {"input_tokens": 0, "output_tokens": 0, "elapsed_time": 0.0}

    # Encode image to base64
    base64_image = encode_image_to_base64(image_path)
    if not base64_image:
        return "Unable to process image.", usage_info

    # Determine image type from extension
    ext = os.path.splitext(image_path)[1].lower()
    media_type = "image/png" if ext == ".png" else "image/jpeg"

    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": QUALITATIVE_OCR_PROMPT
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=500
        )
        elapsed_time = time.time() - start_time

        result = response.choices[0].message.content.strip()

        # Extract token usage from response
        if hasattr(response, 'usage') and response.usage:
            usage_info["input_tokens"] = response.usage.prompt_tokens
            usage_info["output_tokens"] = response.usage.completion_tokens
        usage_info["elapsed_time"] = elapsed_time

        # Update metrics if provided
        if metrics:
            metrics.add_usage(usage_info["input_tokens"], usage_info["output_tokens"], elapsed_time)

        log_message("info", f"Qualitative OCR for {image_path}: {result[:100]}... (tokens: {usage_info['input_tokens']}+{usage_info['output_tokens']})")
        return result, usage_info

    except Exception as e:
        log_message("error", f"Error in qualitative_ocr for {image_path}: {e}")
        return "Unable to analyze screenshot.", usage_info


def summarize_context(text: str, position: str = "preceding", model: str = "gpt-4o", metrics: VisionMetrics = None) -> Tuple[str, Dict]:
    """
    Summarize instructional text to 1-2 sentences.

    Args:
        text: The instructional text to summarize
        position: "preceding" or "following" to indicate context position
        model: OpenAI model to use (default: gpt-4o)
        metrics: Optional VisionMetrics instance to track usage

    Returns:
        Tuple of (Summarized text, usage_dict with tokens and time)
    """
    usage_info = {"input_tokens": 0, "output_tokens": 0, "elapsed_time": 0.0}

    # Handle edge cases
    if not text or text.strip() == "":
        if position == "preceding":
            return "Beginning of document section.", usage_info
        else:
            return "End of document section.", usage_info

    # If text is already very short, return it as-is
    if len(text.split()) < 15:
        return text.strip(), usage_info

    client = get_openai_client()

    # Select appropriate prompt based on position
    if position == "preceding":
        prompt = SUMMARIZE_PRECEDING_PROMPT.format(text=text)
    else:
        prompt = SUMMARIZE_FOLLOWING_PROMPT.format(text=text)

    try:
        start_time = time.time()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=150,
            temperature=0.3
        )
        elapsed_time = time.time() - start_time

        result = response.choices[0].message.content.strip()

        # Extract token usage from response
        if hasattr(response, 'usage') and response.usage:
            usage_info["input_tokens"] = response.usage.prompt_tokens
            usage_info["output_tokens"] = response.usage.completion_tokens
        usage_info["elapsed_time"] = elapsed_time

        # Update metrics if provided
        if metrics:
            metrics.add_usage(usage_info["input_tokens"], usage_info["output_tokens"], elapsed_time)

        log_message("info", f"Summarized {position} text: {result[:80]}... (tokens: {usage_info['input_tokens']}+{usage_info['output_tokens']})")
        return result, usage_info

    except Exception as e:
        log_message("error", f"Error in summarize_context: {e}")
        # Fallback: return first 2 sentences or truncated text
        sentences = text.split('.')
        if len(sentences) >= 2:
            return '. '.join(sentences[:2]).strip() + '.', usage_info
        return (text[:200].strip() + "..." if len(text) > 200 else text.strip()), usage_info


def compose_enhanced_alt_text(
    preceding_summary: str,
    qualitative_ocr: str,
    following_summary: str
) -> str:
    """
    Combine three components into structured enhanced ALT text.

    Args:
        preceding_summary: Summarized preceding context
        qualitative_ocr: Qualitative description from vision model
        following_summary: Summarized following context

    Returns:
        Formatted enhanced ALT text with markers
    """
    return f"[CONTEXT: {preceding_summary}] [IMAGE: {qualitative_ocr}] [NEXT: {following_summary}]"


def process_single_image(
    image_data: Dict,
    model: str = "gpt-4o",
    metrics: VisionMetrics = None,
    summarize_for_bida_text: bool = False,
    summarize_for_bida_image: bool = False
) -> Dict:
    """
    Process a single image to generate enhanced ALT text.

    Args:
        image_data: Dictionary containing:
            - image_path: Path to the image file
            - preceding_text: Text before the image
            - following_text: Text after the image
            - source_doc: Source document name
            - position: Position in document
        model: OpenAI model to use
        metrics: Optional VisionMetrics instance to track usage
        summarize_for_bida_text: If True, GPT-4o summarizes preceding/following text
            for the enhanced_alt_text stored in <img alt='...'> in BIDA_texts
        summarize_for_bida_image: If True, GPT-4o summarizes preceding/following text
            for page_content (search embeddings) in BIDA_images

    Returns:
        Enhanced image_data with additional fields:
            - preceding_text: Raw text (passed through)
            - following_text: Raw text (passed through)
            - qualitative_ocr
            - enhanced_alt_text
            - preceding_summary (only when either summarize flag is True)
            - following_summary (only when either summarize flag is True)
    """
    result = image_data.copy()

    # Summarize when either flag is True (avoid duplicate API calls)
    if summarize_for_bida_text or summarize_for_bida_image:
        result["preceding_summary"], _ = summarize_context(
            image_data.get("preceding_text", ""),
            position="preceding",
            model=model,
            metrics=metrics
        )

        result["following_summary"], _ = summarize_context(
            image_data.get("following_text", ""),
            position="following",
            model=model,
            metrics=metrics
        )

    # Get qualitative OCR (metrics are accumulated inside the function)
    result["qualitative_ocr"], _ = qualitative_ocr(
        image_data["image_path"],
        model=model,
        metrics=metrics
    )

    # Compose enhanced ALT text - V6: structured combination of all three context fields
    if summarize_for_bida_text:
        # Use summaries for the alt text stored in markdown (BIDA_texts)
        result["enhanced_alt_text"] = compose_enhanced_alt_text(
            result.get("preceding_summary", ""),
            result["qualitative_ocr"],
            result.get("following_summary", "")
        )
    else:
        # Default: use raw text for alt text
        preceding = result.get("preceding_text", "").strip()
        following = result.get("following_text", "").strip()
        ocr = result.get("qualitative_ocr", "").strip()
        result["enhanced_alt_text"] = f"[CONTEXT: {preceding}] [IMAGE: {ocr}] [FOLLOWING: {following}]"

    # Track image processed
    if metrics:
        metrics.add_image()

    return result


def process_images_batch(
    image_data_list: List[Dict],
    batch_size: int = 5,
    initial_delay: float = 1.0,
    max_retries: int = 3,
    model: str = "gpt-4o",
    summarize_for_bida_text: bool = False,
    summarize_for_bida_image: bool = False
) -> Tuple[List[Dict], VisionMetrics]:
    """
    Process multiple images with rate limiting.

    Args:
        image_data_list: List of image data dictionaries (see process_single_image)
        batch_size: Number of images to process per batch
        initial_delay: Initial delay between batches in seconds
        max_retries: Maximum retry attempts on rate limit errors
        model: OpenAI model to use
        summarize_for_bida_text: If True, summarize context for BIDA_texts enhanced_alt_text
        summarize_for_bida_image: If True, summarize context for BIDA_images page_content

    Returns:
        Tuple of (List of processed image data with enhanced ALT text, VisionMetrics)
    """
    results = []
    metrics = VisionMetrics()
    total_images = len(image_data_list)

    log_message("info", f"Processing {total_images} images in batches of {batch_size}")

    for i in range(0, total_images, batch_size):
        batch = image_data_list[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_images + batch_size - 1) // batch_size

        log_message("info", f"Processing batch {batch_num}/{total_batches}")

        for j, image_data in enumerate(batch):
            image_idx = i + j + 1
            log_message("info", f"Processing image {image_idx}/{total_images}: {image_data.get('image_path', 'unknown')}")

            retry_count = 0
            delay = initial_delay

            while retry_count <= max_retries:
                try:
                    processed = process_single_image(
                        image_data, model=model, metrics=metrics,
                        summarize_for_bida_text=summarize_for_bida_text,
                        summarize_for_bida_image=summarize_for_bida_image
                    )
                    results.append(processed)
                    break

                except Exception as e:
                    error_str = str(e).lower()

                    # Check for rate limit error
                    if "rate_limit" in error_str or "429" in error_str:
                        retry_count += 1
                        if retry_count <= max_retries:
                            log_message("warning", f"Rate limit hit, retry {retry_count}/{max_retries} after {delay}s")
                            time.sleep(delay)
                            delay *= 2  # Exponential backoff
                        else:
                            log_message("error", f"Max retries exceeded for image {image_idx}")
                            # Add with fallback values
                            fallback = image_data.copy()
                            fallback["preceding_summary"] = image_data.get("preceding_text", "")[:200]
                            fallback["following_summary"] = image_data.get("following_text", "")[:200]
                            fallback["qualitative_ocr"] = "Unable to analyze screenshot due to rate limiting."
                            fallback["enhanced_alt_text"] = compose_enhanced_alt_text(
                                fallback["preceding_summary"],
                                fallback["qualitative_ocr"],
                                fallback["following_summary"]
                            )
                            results.append(fallback)
                            metrics.add_image()  # Count as processed even with fallback
                    else:
                        # Other error - use fallback
                        log_message("error", f"Error processing image {image_idx}: {e}")
                        fallback = image_data.copy()
                        fallback["preceding_summary"] = image_data.get("preceding_text", "")[:200]
                        fallback["following_summary"] = image_data.get("following_text", "")[:200]
                        fallback["qualitative_ocr"] = "Unable to analyze screenshot."
                        fallback["enhanced_alt_text"] = compose_enhanced_alt_text(
                            fallback["preceding_summary"],
                            fallback["qualitative_ocr"],
                            fallback["following_summary"]
                        )
                        results.append(fallback)
                        metrics.add_image()  # Count as processed even with fallback
                        break

        # Delay between batches (except for last batch)
        if i + batch_size < total_images:
            log_message("info", f"Batch {batch_num} complete. Waiting {initial_delay}s before next batch...")
            time.sleep(initial_delay)

    log_message("info", f"Completed processing {len(results)} images. {metrics}")
    return results, metrics


def process_images_batch_with_callback(
    image_data_list: List[Dict],
    batch_size: int = 5,
    initial_delay: float = 1.0,
    max_retries: int = 3,
    model: str = "gpt-4o",
    progress_callback: callable = None,
    summarize_for_bida_text: bool = False,
    summarize_for_bida_image: bool = False
) -> Tuple[List[Dict], VisionMetrics]:
    """
    Process multiple images with rate limiting and progress callback.

    Args:
        image_data_list: List of image data dictionaries (see process_single_image)
        batch_size: Number of images to process per batch
        initial_delay: Initial delay between batches in seconds
        max_retries: Maximum retry attempts on rate limit errors
        model: OpenAI model to use
        progress_callback: Optional callback function(total_images, processed_count, current_image_name, metrics)
                          Called after each image is processed
        summarize_for_bida_text: If True, summarize context for BIDA_texts enhanced_alt_text
        summarize_for_bida_image: If True, summarize context for BIDA_images page_content

    Returns:
        Tuple of (List of processed image data with enhanced ALT text, VisionMetrics)
    """
    results = []
    metrics = VisionMetrics()
    total_images = len(image_data_list)

    log_message("info", f"Processing {total_images} images in batches of {batch_size}")

    # Initial callback to report total count
    if progress_callback:
        progress_callback(total_images, 0, "Starting...", metrics)

    for i in range(0, total_images, batch_size):
        batch = image_data_list[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_images + batch_size - 1) // batch_size

        log_message("info", f"Processing batch {batch_num}/{total_batches}")

        for j, image_data in enumerate(batch):
            image_idx = i + j + 1
            image_name = os.path.basename(image_data.get('image_path', 'unknown'))
            log_message("info", f"Processing image {image_idx}/{total_images}: {image_name}")

            retry_count = 0
            delay = initial_delay

            while retry_count <= max_retries:
                try:
                    processed = process_single_image(
                        image_data, model=model, metrics=metrics,
                        summarize_for_bida_text=summarize_for_bida_text,
                        summarize_for_bida_image=summarize_for_bida_image
                    )
                    results.append(processed)

                    # Call progress callback after successful processing
                    if progress_callback:
                        progress_callback(total_images, len(results), image_name, metrics)

                    break

                except Exception as e:
                    error_str = str(e).lower()

                    # Check for rate limit error
                    if "rate_limit" in error_str or "429" in error_str:
                        retry_count += 1
                        if retry_count <= max_retries:
                            log_message("warning", f"Rate limit hit, retry {retry_count}/{max_retries} after {delay}s")
                            time.sleep(delay)
                            delay *= 2  # Exponential backoff
                        else:
                            log_message("error", f"Max retries exceeded for image {image_idx}")
                            # Add with fallback values
                            fallback = image_data.copy()
                            fallback["preceding_summary"] = image_data.get("preceding_text", "")[:200]
                            fallback["following_summary"] = image_data.get("following_text", "")[:200]
                            fallback["qualitative_ocr"] = "Unable to analyze screenshot due to rate limiting."
                            fallback["enhanced_alt_text"] = compose_enhanced_alt_text(
                                fallback["preceding_summary"],
                                fallback["qualitative_ocr"],
                                fallback["following_summary"]
                            )
                            results.append(fallback)
                            metrics.add_image()  # Count as processed even with fallback

                            if progress_callback:
                                progress_callback(total_images, len(results), f"{image_name} (fallback)", metrics)
                    else:
                        # Other error - use fallback
                        log_message("error", f"Error processing image {image_idx}: {e}")
                        fallback = image_data.copy()
                        fallback["preceding_summary"] = image_data.get("preceding_text", "")[:200]
                        fallback["following_summary"] = image_data.get("following_text", "")[:200]
                        fallback["qualitative_ocr"] = "Unable to analyze screenshot."
                        fallback["enhanced_alt_text"] = compose_enhanced_alt_text(
                            fallback["preceding_summary"],
                            fallback["qualitative_ocr"],
                            fallback["following_summary"]
                        )
                        results.append(fallback)
                        metrics.add_image()  # Count as processed even with fallback

                        if progress_callback:
                            progress_callback(total_images, len(results), f"{image_name} (error)", metrics)

                        break

        # Delay between batches (except for last batch)
        if i + batch_size < total_images:
            log_message("info", f"Batch {batch_num} complete. Waiting {initial_delay}s before next batch...")
            time.sleep(initial_delay)

    log_message("info", f"Completed processing {len(results)} images. {metrics}")
    return results, metrics


def extract_image_section_from_alt_text(enhanced_alt_text: str) -> str:
    """
    Extract just the [IMAGE: ...] section from enhanced ALT text.

    Args:
        enhanced_alt_text: Full enhanced ALT text with all three sections

    Returns:
        Just the qualitative OCR description (without markers)
    """
    import re
    match = re.search(r'\[IMAGE:\s*(.*?)\]', enhanced_alt_text)
    if match:
        return match.group(1).strip()
    return enhanced_alt_text


def extract_context_section_from_alt_text(enhanced_alt_text: str) -> str:
    """
    Extract just the [CONTEXT: ...] section from enhanced ALT text.

    Args:
        enhanced_alt_text: Full enhanced ALT text with all three sections

    Returns:
        Just the preceding context summary (without markers)
    """
    import re
    match = re.search(r'\[CONTEXT:\s*(.*?)\]', enhanced_alt_text)
    if match:
        return match.group(1).strip()
    return ""


def extract_next_section_from_alt_text(enhanced_alt_text: str) -> str:
    """
    Extract just the [NEXT: ...] section from enhanced ALT text.

    Args:
        enhanced_alt_text: Full enhanced ALT text with all three sections

    Returns:
        Just the following context summary (without markers)
    """
    import re
    match = re.search(r'\[NEXT:\s*(.*?)\]', enhanced_alt_text)
    if match:
        return match.group(1).strip()
    return ""
