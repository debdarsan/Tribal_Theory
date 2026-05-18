import streamlit as st
import smtplib
import ssl
from email.message import EmailMessage
from vars.s_state import *
from utils.json_utils import *
from utils.date_time_utils import *
from utils.token_utils import *
from utils.string_utils import *
from consts.consts import *
import string

def clear_QA() -> None:
    ss.qa_history = {
        "historical_prompts": [],
        "historical_responses": [],
    }
    ss._user_prompt = ""
    ss._qa_filename = ""
    ss.chat_history = []
    return None

def load_history(directory, user_chat_history_name, user_name, chat_history):

    qa_history_file_name = user_chat_history_name + "_" + user_name + ".json"
    #if chat_history:
    history_data = load_qa_history(directory, qa_history_file_name)
    if not history_data:
        return
    ss.qa_history["historical_prompts"] = history_data["historical_prompts"]
    ss.qa_history["historical_responses"] = history_data["historical_responses"]
    ss._qa_filename = qa_history_file_name

    # Rebuild ss.chat_history from the loaded thread so multi-turn context
    # is available when the user continues the conversation. Each exchange
    # contributes a ("user", Q) and ("assistant", A) tuple. manage_chat_history
    # will truncate to the configured token limit before the next LLM call.
    ss.chat_history = []
    for prompt, response in zip(history_data["historical_prompts"], history_data["historical_responses"]):
        result = response.get("result", "") if isinstance(response, dict) else ""
        if not result:
            continue
        ss.chat_history.append(("user", prompt))
        ss.chat_history.append(("assistant", result))

    st.rerun()

def delete_history(directory, user_chat_history_name, user_name, clear_current=True):
    """Delete a specific chat history file and optionally clear current session if it matches."""
    qa_history_file_name = user_chat_history_name + "_" + user_name + ".json"
    file_path = os.path.join(directory, qa_history_file_name)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)

            # Clear current session state if this was the active chat
            if clear_current and ss._qa_filename == qa_history_file_name:
                ss.qa_history = {
                    "historical_prompts": [],
                    "historical_responses": [],
                }
                ss._qa_filename = ""
                ss.chat_history = []

            return True
        return False
    except Exception as e:
        st.error(f"Error deleting history: {e}")
        log_message("error", f"Error deleting history file {file_path}: {e}")
        return False

def rename_history(directory, old_chat_name, new_display_name, user_name):
    """Rename a specific chat history file while preserving timestamp and user."""
    try:
        # Extract the timestamp from the old name (format: question_timestamp)
        parts = old_chat_name.rsplit('_', 1)
        if len(parts) == 2:
            timestamp = parts[1]
        else:
            # If no timestamp found, use current timestamp
            from utils.date_time_utils import get_date_time_stamp_compact
            timestamp = get_date_time_stamp_compact()

        # Sanitize the new display name
        symbols_to_remove = "[]{}\\?<>:\"/|*"
        new_display_name = ''.join([char for char in new_display_name if char not in symbols_to_remove])
        new_display_name = new_display_name.strip()

        if not new_display_name:
            st.error("Invalid name. Please provide a valid name.")
            return False

        # Construct old and new file paths
        old_file_name = old_chat_name + "_" + user_name + ".json"
        new_file_name = new_display_name + "_" + timestamp + "_" + user_name + ".json"

        old_file_path = os.path.join(directory, old_file_name)
        new_file_path = os.path.join(directory, new_file_name)

        # Check if old file exists
        if not os.path.exists(old_file_path):
            st.error("Chat history file not found.")
            return False

        # Check if new file already exists
        if os.path.exists(new_file_path) and old_file_path != new_file_path:
            st.error("A chat with this name already exists.")
            return False

        # Rename the file
        os.rename(old_file_path, new_file_path)
        return True

    except Exception as e:
        st.error(f"Error renaming history: {e}")
        log_message("error", f"Error renaming history: {e}")
        return False

def send_email(email_sender, email_receiver, subject, body):

    subject = str(subject)
    body = str(body)
    email_password = 'jkrs cppl cebl uczg'
    # Set the subject and body of the email

    em = EmailMessage()
    em['From'] = email_sender
    em['To'] = email_receiver
    em['Subject'] = subject
    em.set_content(body)

    # Add SSL (layer of security)
    context = ssl.create_default_context()

    # Log in and send the email
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as smtp:
        smtp.login(email_sender, email_password)
        smtp.sendmail(email_sender, email_receiver, em.as_string())

def download_chat_history(DIRECTORY, user_name, user_chat_history_names, only_today=False, selected_user="All Users"):
    """Download chat history for selected user or all users."""
    try:
        from utils.sys_utils import zip_files_multi_user

        if selected_user == "All Users":
            zip_name = "all_users_chat_history_" + get_date_time_stamp() + ".zip"
        else:
            zip_name = selected_user + "_chat_history_" + get_date_time_stamp() + ".zip"

        zip_buffer, zip_name = zip_files_multi_user(
            DIRECTORY,
            user_chat_history_names,
            zip_name,
            selected_user=selected_user,
            only_today=only_today
        )
        return zip_buffer, zip_name
    except Exception as e:
        st.error(f"Unable to download chat history: {e}")
        log_message("error", f"Error occurred while trying to download history: {e}")
        return None, None
    
def manage_chat_history(chat_history, token_limit):
    while estimate_token_count(chat_history) > token_limit:
        chat_history.pop(0)  # Remove the oldest conversation

def greet_back(greeting):
    # Handle greeting messages
    return greetings[greeting]

def process_message(message):
    # Remove punctuation and convert to lowercase
    return message.lower().translate(str.maketrans("", "", string.punctuation))

def is_greeting(message):
    # Check if the message is a greeting
    processed_message = process_message(message)
    for greeting in greetings:
        if process_message(greeting) == processed_message:
            return greet_back(greeting)
    return 0

def is_qa_history_not_empty(qa_history):
    # Check if 'historical_prompts' and 'historical_responses' are in qa_history and not empty
    return ('historical_prompts' in qa_history and qa_history['historical_prompts'] and 
            'historical_responses' in qa_history and qa_history['historical_responses'])

def create_bot_response(answer, docs, chat_history, user_prompt, greet_flag=False):
    bot_response = {
        "question": user_prompt,
        "chat_history": [],
        "result": answer,
        "source_documents": docs if docs else [],
        "greet_flag": greet_flag
    }
    simplified_history = [chat_block[1] for chat_block in chat_history]

    bot_response["chat_history"].append([list(qa_pair) for qa_pair in \
                                           zip(simplified_history[::2],simplified_history[1::2])])
    return bot_response

def parse_document(doc):
    try:
        if isinstance(doc, Document):
            # If doc is a Document object
            page_content = doc.page_content
            metadata = doc.metadata
        elif isinstance(doc, str):
            # If doc is a string, parse it accordingly
            pattern = r"page_content='(.*?)' metadata=(\{.*\})"
            match = re.search(pattern, doc)
            if match:
                page_content = match.group(1)
                metadata = json.loads(match.group(2).replace("'", '"'))  # Convert single quotes to double quotes for JSON
            else:
                raise ValueError("Document string format not recognized")
        else:
            raise ValueError("Unrecognized document type")

        return page_content, metadata
    
    except Exception as e:
        print(f"Error parsing document: {e}")
        return None, None
    
def save_QA(DIRECTORY, qa_filename, qa_history) -> None:
    """
    Saves the Question and Answer (QA) history.

    """
    try:
        
        save_qa_history(DIRECTORY, qa_filename, qa_history)
    except Exception as e:
        log_message("error", f"An error occurred while saving qa history: {e}")
        raise
    
def split_user_chat_name(user_chat_history_name):
    # Split the string at the first underscore
    parts = user_chat_history_name.split('_', 1)

    # Extract the first part
    chat_question = parts[0]

    # Reconstruct the second part with the underscore
    datetime_and_user = '_' + parts[1] if len(parts) > 1 else ''
    return chat_question, datetime_and_user

def extract_timestamp_from_chat_name(chat_name):
    """Extract timestamp from chat name for sorting. Format: question_YYMMDDHHMMSS"""
    try:
        parts = chat_name.rsplit('_', 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[1]
        return "000000000000"  # Default for items without valid timestamp
    except:
        return "000000000000"

def get_user_chat_names_in_directory(directory_path, user_name, isSuper_user):
    try:
        if not os.path.exists(directory_path):
            raise FileNotFoundError(f"Directory not found: {directory_path}")
        filename_does_not_start_with = "_"
        filename_ends_with = "_" + user_name
        if isSuper_user:
            user_chat_history_names = {}
        else:
            user_chat_history_names = []

        if isSuper_user:
            users = []
            for f in os.listdir(directory_path):
                if os.path.isfile(os.path.join(directory_path, f)):
                    filename_without_extension, _ = os.path.splitext(f)
                    starts_condition = not filename_without_extension.startswith(filename_does_not_start_with)
                    user = filename_without_extension[-2:]
                    filename_parts = filename_without_extension.split("_")
                    user = filename_parts[-1]
                    if (user in users) and (starts_condition):
                        user_chat_history_names[user].append(filename_without_extension.replace("_"+user, ""))
                    else:
                        users.append(user)
                        user_chat_history_names[user] = []
                        user_chat_history_names[user].append(filename_without_extension.replace("_"+user, ""))

            # Sort each user's chat history by timestamp (latest first)
            for user in user_chat_history_names:
                user_chat_history_names[user] = sorted(
                    user_chat_history_names[user],
                    key=extract_timestamp_from_chat_name,
                    reverse=True
                )
        else:
            for f in os.listdir(directory_path):
                if os.path.isfile(os.path.join(directory_path, f)):
                    filename_without_extension, _ = os.path.splitext(f)
                    starts_condition = not filename_without_extension.startswith(filename_does_not_start_with)
                    ends_condition = filename_without_extension.endswith(filename_ends_with)
                    if starts_condition and ends_condition:
                        user_chat_history_names.append(filename_without_extension.replace(filename_ends_with, ""))

            # Sort by timestamp (latest first)
            if user_chat_history_names:
                user_chat_history_names = sorted(
                    user_chat_history_names,
                    key=extract_timestamp_from_chat_name,
                    reverse=True
                )

        return user_chat_history_names

    except FileNotFoundError as e:
        log_message("error", str(e))
        return None
    except Exception as e:
        log_message("error", f"Error listing files in directory: {e}")
        return None               

def formulate_qa_filename():
    symbols_to_remove = "[]{}\\?<>:\"/|*"
    time_stamp = get_date_time_stamp_compact()
    ss._qa_filename = extract_without_breaking_words(ss.qa_history["historical_prompts"][0], EXTRACT_N_CHARS_FROM_PROMPT) + \
                                    "_" + time_stamp + "_" + ss.user_name 
    ss._qa_filename = ''.join([char for char in ss._qa_filename if char not in symbols_to_remove])
    ss._qa_filename = ss._qa_filename + ".json"