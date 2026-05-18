import base64
from consts.consts import blinking_icon_color

def get_base64_image(path):
    with open(path, "rb") as img_file:
        b64_data = base64.b64encode(img_file.read()).decode()
    return f"data:image/png;base64,{b64_data}"

css_template = """
<style>
  :root {{
    --user-bg-color: {user_bg_color}; /* User message background color */
    --user-fg-color: {user_fg_color}; /* User message foreground color */
    --bot-bg-color: {bot_bg_color};  /* Bot message background color */
    --bot-fg-color: {bot_fg_color};  /* Bot message foreground color */
    --user-font-family: '{user_font_family}'; /* Font family for user messages */
    --user-font-size: {user_font_size}px; /* Font size for user messages */
    --bot-font-family: '{bot_font_family}'; /* Font family for bot messages */
    --bot-font-size: {bot_font_size}px; /* Font size for bot messages */
  }}
  
  .chat-message {{
    display: flex;
    align-items: flex-start; /* Align items at the start to match the avatar's top */
    padding: 8px 12px;
    margin: 5px 0;
    border-radius: 20px; /* Makes the rectangle round */
    background-color: var(--user-bg-color);
    color: var(--user-fg-color);
    font-family: var(--user-font-family);
    font-size: var(--user-font-size);
  }}
  
  .chat-message.bot {{
    background-color: var(--bot-bg-color);
    color: var(--bot-fg-color);
    font-family: var(--bot-font-family);
    font-size: var(--bot-font-size);
  }}
  
  .chat-message .avatar {{
    flex-shrink: 0; /* Prevent the avatar from shrinking */
    width: 40px; /* Adjust size as needed */
    height: 40px; /* Adjust size as needed */
    border-radius: 50%;
    margin-right: 12px; /* Space between avatar and message */
  }}
  
  .chat-message .avatar img {{
    width: 100%;
    height: 100%;
    border-radius: 50%;
    object-fit: cover;
  }}
  
  .chat-message .message {{
    max-width: calc(100% - 60px); /* Adjust based on avatar size + margin */
    word-wrap: break-word; /* Ensure the text wraps within the container */
    align-self: center; /* Align the text with the avatar */
  }}
  
.latex {
    color: orange; /* Change the color as needed */
}
</style>
"""

css_template_static = """
<style>
  :root {{
    --user-bg-color: #4e4e51; /* User message background color */
    --user-fg-color: #c0d5e6; /* User message foreground color */
    --bot-bg-color: #374151;  /* Bot message background color */
    --bot-fg-color: #E2E8EA;  /* Bot message foreground color */
    --user-font-family: 'Segoe UI'; /* Font family for user messages */
    --user-font-size: 12px; /* Font size for user messages */
    --bot-font-family: 'Segoe UI'; /* Font family for bot messages */
    --bot-font-size: 12px; /* Font size for bot messages */
  }}
  
  .chat-message {{
    display: flex;
    align-items: flex-start; /* Align items at the start to match the avatar's top */
    padding: 8px 12px;
    margin: 5px 0;
    border-radius: 20px; /* Makes the rectangle round */
    background-color: var(--user-bg-color);
    color: var(--user-fg-color);
    font-family: var(--user-font-family);
    font-size: var(--user-font-size);
  }}
  
  .chat-message.bot {{
    background-color: var(--bot-bg-color);
    color: var(--bot-fg-color);
    font-family: var(--bot-font-family);
    font-size: var(--bot-font-size);
  }}
  
  .chat-message .avatar {{
    flex-shrink: 0; /* Prevent the avatar from shrinking */
    width: 40px; /* Adjust size as needed */
    height: 40px; /* Adjust size as needed */
    border-radius: 50%;
    margin-right: 12px; /* Space between avatar and message */
  }}
  
  .chat-message .avatar img {{
    width: 100%;
    height: 100%;
    border-radius: 50%;
    object-fit: cover;
  }}
  
  .chat-message .message {{
    max-width: calc(100% - 60px); /* Adjust based on avatar size + margin */
    word-wrap: break-word; /* Ensure the text wraps within the container */
    align-self: center; /* Align the text with the avatar */
  }}
  
.latex {
    color: orange; /* Change the color as needed */
}
</style>
"""

css_old = """
<style>

.chat-message {
    padding: 0.5rem; 
    border-radius: 0.5rem; 
    margin-bottom: 1rem; 
    display: flex;
    align-items: flex-start; /* Align items to the top */
    flex-wrap: wrap; /* Allows items to wrap instead of forcing them into a single line */
    width: 100%; /* Adjust based on your layout needs */
}

.chat-message.user {
    background-color: #475063;
}
.chat-message.bot {
    background-color: #2b313e;
    font-size: 15px;
}
.chat-message .avatar {
    width: auto; /* Set width to auto to fit content */
    padding-right: 0; /* Remove right padding */
    margin-right: 5px; /* Adjust right margin */
}
.chat-message .avatar img {
    max-width: 30px;
    max-height: 30px;
    border-radius: 50%;
    object-fit: cover;
}

.chat-message .message {
    flex-grow: 1; /* Allow message to take up remaining space */
    padding-left: 5px; /* Minimal left padding next to image */
    color: #F5F5F5;
    overflow-wrap: break-word; /* Ensures content breaks to prevent overflow */
    word-wrap: break-word; /* Deprecated but included for broader compatibility */
    max-width: 100%; /* Ensure the container does not exceed its parent's width */
}

.small-font {
    font-size:15px !important;
}

.latex {
    color: orange; /* Change the color as needed */
}

.plain-text {
    color: lightblue;
}
.number {
    color: cyan;
}
.equation-number {
    color: yellow;
}

.stCodeBlock {
    background-color: #2b313e; /* Same background color as bot template */
    color: #fff; /* Text color */
    padding: 0.5rem; /* Padding similar to bot template */
    border-radius: 0.5rem; /* Rounded corners like bot template */
    font-size: 15px; /* Font size */
    /* Add any other styling that matches your bot template */
}

.code-block {
    background-color: #f4f4f4 !important; /* Light grey background */
    color: yellow !important; /* Yellow text color */
    padding: 10px !important;
    border-radius: 5px !important;
    white-space: pre-wrap !important; /* Allows text to wrap, preserving white spaces and line breaks */
    word-break: break-word !important; /* Breaks the word to prevent overflow */
}

</style>
"""

relevant_css_keys = [
    'user_bg_color', 'user_fg_color', 'bot_bg_color', 'bot_fg_color',
    'user_font_family', 'user_font_size', 'bot_font_family', 'bot_font_size'
]

# Get base64 version of the image
user_icon_b64 = get_base64_image("static/icons/user.png")

# Use it in your template
user_template = f"""
<div class="chat-message user">
    <div class="avatar">
        <img src="{user_icon_b64}">
    </div>
    <div class="message">{{{{MSG}}}}</div>
</div>
"""

bot_icon_b64 = get_base64_image("static/icons/assistant.png")

bot_template_old = f"""
<div class="chat-message bot">
    <div class="avatar">
        <img src="{bot_icon_b64}">
    </div>
    <div class="message">{{{{MSG}}}}</div>
</div>
"""

bot_template_code_block = f"""
<div class="chat-message bot">
    <div class="avatar">
        <img src="{bot_icon_b64}">
    </div>
    <div class="message">
        <pre class="code-block">{{{{MSG}}}}</pre>
    </div>
</div>
"""
bot_template = f"""
<div class="chat-message bot">
    <div class="avatar">
        <img src="{bot_icon_b64}">
    </div>
    <div class="message">{{{{MSG}}}}</div>
</div>
"""

bot_template_ex = """
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.1.3/dist/css/bootstrap.min.css" integrity="sha384-MCw98/SFnGE8fJT3GXwEOngsV7Zt27NXFoaoApmYm81iuXoPkFOJwJ8ERdknLPMO" crossorigin="anonymous">
        <script src="https://code.jquery.com/jquery-3.3.1.slim.min.js" integrity="sha384-q8i/X+965DzO0rT7abK41JStQIAqVgRVzpbzo5smXKp4YfRvH+8abtTE1Pi6jizo" crossorigin="anonymous"></script>
        <script src="https://cdn.jsdelivr.net/npm/popper.js@1.14.3/dist/umd/popper.min.js" integrity="sha384-ZMP7rVo3mIykV+2+9J3UJ46jBk0WLaUAdn689aCwoqbBJiSnjAK/l8WvCWPIPm49" crossorigin="anonymous"></script>
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@4.1.3/dist/js/bootstrap.min.js" integrity="sha384-ChfqqxuZUCnJSK3+MXmPNIyE6ZbWh2IMqE241rYiqJxyMiZ6OW/JmZQ5stwEULTy" crossorigin="anonymous"></script>
        <script type="text/x-mathjax-config">
            MathJax.Hub.Config({
                tex2jax: {
                    inlineMath: [['$', '$']],
                    processEscapes: true
                }
            });
        </script>
        <script type="text/javascript" async
            src="https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.7/MathJax.js?config=TeX-MML-AM_CHTML">
        </script>
        <style>
            .br-main-container{
                background-color: #0e1117;
                min-height: 138px;
                max-height: auto;
            }
            .br-inner-container{
                background-color: #2b313e;
                border-radius: 20px;
                padding: 10px;
                display:flex;
                flex-direction:column;
                align-items:flex-start;
                
            }
            .br-img-container{
                padding-bottom: 10px;
            }
            .br-ans-container{
                color: #e7cb6d;
                width: 100%;
            }
        </style>
        <div class="br-main-container" style="padding: 2px">
            <div class = "br-inner-container">
                <div class = "br-img-container">
                    <img src="https://i.imgur.com/ZXLTfXT.png" style="width: 32px">
                <div>
                <div class = "br-ans-container">
                    <p style="font-size: 85%">{{answer}}</p>
                    {{documents}}
                </div>               
            </div>
        </div>
        """

blinking_circle = """
<style>
@keyframes blink-animation-circle {
    0% { fill: #000; }
    50% { fill: white; }
    100% { fill: #000; }
}
.blinking-circle-icon {
    animation: blink-animation-circle 0.5s infinite;
}
</style>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 512 512" class="blinking-circle-icon">
    <!-- Example path, replace with your specific SVG path -->
    <path d="M256,0C114.617,0,0,114.617,0,256s114.617,256,256,256s256-114.617,256-256S397.383,0,256,0z M256,472
        c-119.295,0-216-96.705-216-216S136.705,40,256,40s216,96.705,216,216S375.295,472,256,472z"/>
</svg>
"""

blinking_image = f"""
<style>
@keyframes blink-animation-image {{
    0% {{ fill: #000; }}
    50% {{ fill: {blinking_icon_color}; }}
    100% {{ fill: #000; }}
}}
.blinking-image-icon {{
    animation: blink-animation-image 0.5s infinite;
}}
</style>

<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 512 512" class="blinking-image-icon">
    <!-- Example path, replace with your specific SVG path -->
    <path d="M64 64C46.3 64 32 78.3 32 96V329.4l67.7-67.7c15.6-15.6 40.9-15.6 56.6 0L224 329.4 355.7 197.7c15.6-15.6 40.9-15.6 56.6 0L480 265.4V96c0-17.7-14.3-32-32-32H64zM32 374.6V416c0 17.7 14.3 32 32 32h41.4l96-96-67.7-67.7c-3.1-3.1-8.2-3.1-11.3 0L32 374.6zM389.7 220.3c-3.1-3.1-8.2-3.1-11.3 0L150.6 448H448c17.7 0 32-14.3 32-32V310.6l-90.3-90.3zM0 96C0 60.7 28.7 32 64 32H448c35.3 0 64 28.7 64 64V416c0 35.3-28.7 64-64 64H64c-35.3 0-64-28.7-64-64V96zm160 48a16 16 0 1 0 -32 0 16 16 0 1 0 32 0zm-64 0a48 48 0 1 1 96 0 48 48 0 1 1 -96 0z"/>
</svg>
"""

blinking_pencil = f"""
<style>
@keyframes blink-animation-pencil {{
    0% {{ fill: #000; }}
    50% {{ fill: {blinking_icon_color}; }}
    100% {{ fill: #000; }}
}}
.blinking-pencil-icon {{
    animation: blink-animation-pencil 0.5s infinite;
}}
</style>

<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 512 512" class="blinking-pencil-icon">
    <!-- Example path, replace with your specific SVG path -->
    <path d="M0 512l4.4-17.6L40 352 380.7 11.3 392 0l11.3 11.3 97.4 97.4L512 120l-11.3 11.3L160 472 17.6 507.6 0 512zM160 408v41.4l251-251L313.7 101 62.6 352H104h8v8 40h40 8v8zm-16 48V416H104 96v-8V368H56c-1.2 0-2.3-.3-3.3-.7L22 490l122.7-30.7c-.5-1-.7-2.1-.7-3.3zM422.3 187l67-67L392 22.6l-67 67L422.3 187zM317.7 173.1l-144 144-5.7 5.7-11.3-11.3 5.7-5.7 144-144 5.7-5.7 11.3 11.3-5.7 5.7z"/>
</svg>
"""


color = "yellow"
duration = 1
width = 16
height = 16
object = "pencil"
blinking_pencil_ex = f"""
<style>
@keyframes blink-animation-{object} {{
    0% {{ fill: #000; }}
    50% {{ fill: {color}; }}
    100% {{ fill: #000; }}
}}
.blinking-{object}-icon {{
    animation: blink-animation-{object} {duration}s infinite;
}}
</style>

<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 512 512" class="blinking-{object}-icon">
    <!-- Example path, replace with your specific SVG path -->
    <path d="M0 512l4.4-17.6L40 352 380.7 11.3 392 0l11.3 11.3 97.4 97.4L512 120l-11.3 11.3L160 472 17.6 507.6 0 512zM160 408v41.4l251-251L313.7 101 62.6 352H104h8v8 40h40 8v8zm-16 48V416H104 96v-8V368H56c-1.2 0-2.3-.3-3.3-.7L22 490l122.7-30.7c-.5-1-.7-2.1-.7-3.3zM422.3 187l67-67L392 22.6l-67 67L422.3 187zM317.7 173.1l-144 144-5.7 5.7-11.3-11.3 5.7-5.7 144-144 5.7-5.7 11.3 11.3-5.7 5.7z"/>
</svg>
"""

blinking_lambda = f"""
<style>
@keyframes blink-animation-lambda {{
    0% {{ fill: #000; }}
    50% {{ fill: {blinking_icon_color}; }}
    100% {{ fill: #000; }}
}}
.blinking-lambda-icon {{
    animation: blink-animation-lambda 0.5s infinite;
}}
</style>

<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 512 512" class="blinking-lambda-icon">
    <!-- Example path, replace with your specific SVG path -->
    <path d="M8 32H0V48H8 147l27.7 57.5L11.8 480H29.2L183.8 124.5l169 351L355 480h5 80 8V464h-8H365L159.2 36.5 157 32h-5H8z"/>
</svg>
"""

blinking_book_open = f"""
<style>
@keyframes blink-animation-book-open {{
    0% {{ fill: #000; }}
    50% {{ fill: {blinking_icon_color}; }}
    100% {{ fill: #000; }}
}}
.blinking-book-open-icon {{
    animation: blink-animation-book-open 0.5s infinite;
}}
</style>

<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 640 512" class="blinking-book-open-icon">
    <!-- Example path, replace with your specific SVG path -->
    <path d="M80 386.9l232 46.4V50.3L80 18.4V386.9zm248 46.4l232-46.4V18.4L328 50.3v383zM320 35.2l240-33L576 0V16.2 400L320 451.2 64 400V16.2 0L80 2.2l240 33zM16 31l16 2.2V49.4L16 47.2V431.7l304 60.8 304-60.8V47.2l-16 2.2V33.2L624 31l16-2.2V45 444.8l-320 64L0 444.8V45 28.8L16 31z"/>
</svg>
"""

