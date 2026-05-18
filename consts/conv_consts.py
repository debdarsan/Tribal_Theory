# Store switches and arguments in separate variables

OUTPUT_FORMAT = 'md'
IMG_DIR = 'static'
MAX_IMAGE_HEIGHT = 300  # Default value, can be overridden

EXTRA_ARGS_LIST = [
    '-f', 'docx',
    '-t', 'markdown-simple_tables-multiline_tables-grid_tables',
    '--extract-media', IMG_DIR,
    '--wrap=none'
]

IGNORE_IMAGE_SIZE_KB = 10  # Default value, can be overridden

SECTIONS_TO_BE_REMOVED = ['Table of Contents', 'Change History', 'Copyright', 'Index', 'Contents']


def set_max_image_height(value):
    """Set the MAX_IMAGE_HEIGHT value."""
    global MAX_IMAGE_HEIGHT
    MAX_IMAGE_HEIGHT = value


def set_ignore_image_size_kb(value):
    """Set the IGNORE_IMAGE_SIZE_KB value."""
    global IGNORE_IMAGE_SIZE_KB
    IGNORE_IMAGE_SIZE_KB = value
