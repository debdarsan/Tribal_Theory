import streamlit as st
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from html_css_templates import css_template_static

st.markdown(css_template_static, unsafe_allow_html=True)
# Your existing bot template
bot_template = '''
<div class="chat-message bot">
    <div class="avatar">
        <img src="https://i.imgur.com/ZXLTfXT.png">
    </div>
    <div class="message">{MSG}</div>
</div>
'''

# Add a file uploader for .md files
uploaded_file = st.file_uploader("Upload a Markdown file", type="md")

# If a file is uploaded, process it
if uploaded_file is not None:
    # Read the file and store the content in a variable
    md_content = uploaded_file.read().decode("utf-8")
    md_content = bot_template.replace("{MSG}", md_content)
    # Display the markdown content in the Streamlit app
    st.markdown(md_content, unsafe_allow_html=True)
