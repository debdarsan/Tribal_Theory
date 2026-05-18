# Vector database constants
import os

# Legacy single collection name (kept for backward compatibility)
VECTORSTORE_NAME = "BIDA"

# Two-collection architecture names
TEXT_COLLECTION_NAME = "BIDA_texts"
IMAGE_COLLECTION_NAME = "BIDA_images"

## To supress the following warning, set TOKENIZERS_PARALLELISM to false
# huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
# To disable this warning, you can either:
#         - Avoid using `tokenizers` before the fork if possible
#         - Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)

os.environ["TOKENIZERS_PARALLELISM"] = "false"
