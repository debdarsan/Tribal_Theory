import tiktoken
""" 
Encoding name	        OpenAI models
-------------------------------------
cl100k_base	            gpt-4, gpt-3.5-turbo, text-embedding-BIDA-002
p50k_base	            Codex models, text-davinci-002, text-davinci-003
r50k_base (or gpt2)	    GPT-3 models like davinci 
"""

#ENCODING_NAME = "cl100k_base"
#encoding = tiktoken.get_encoding(ENCODING_NAME)

model = "gpt-3.5-turbo"
encoding = tiktoken.encoding_for_model(model)

# For HuggingFace tokenizer
# tokenizer = GPT2Tokenizer.from_pretrained("EleutherAI/gpt-neo-2.7B")

# Use this with the HuggingFace tokenizer
# def get_text_token_count(text, tokenizer):
#     return len(tokenizer(text)["input_ids"])

def get_text_token_count(text):
    """Returns the number of tokens in a text string."""
    #encoding = tiktoken.get_encoding(ENCODING_NAME)
    token_count = len(encoding.encode(text))
    return token_count

# Use this with the HuggingFace tokenizer
# def get_metadata_token_count(metadata, tokenizer):
#     metadata_str = " ".join([f"{key}: {value}" for key, value in metadata.items()])
#     return len(tokenizer(metadata_str)["input_ids"])

def get_metadata_token_count(metadata):
    metadata_str = " ".join([f"{key}: {value}" for key, value in metadata.items()])
    return get_text_token_count(metadata_str)

# Function to estimate the token count based on character count
def estimate_token_count(chat_history):
    return sum([len(prompt) // 4 for prompt, _ in chat_history])
