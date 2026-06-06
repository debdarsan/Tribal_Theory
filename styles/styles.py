# All styling constants and functions for streamlit
import streamlit as st
from consts.consts import *
from html_css_templates import *
from vars.s_state import ss
import re

text_box_html = f"""
    <style>
        .text-box {{
            background-color: rgba(255, 255, 255, 0.1); /* Semi-transparent white background */
            border-radius: 10px; /* Rounded corners */
            padding: 5px; /* Some padding around the text */
            border: 1.5px solid #262730 !important;
            display: block;
            max-width: 100%; /* Maximum width of the box */
            margin: 5px 5px 15px 0px; /* Margin around the box, zero on the left side */
            text-align: center !important; /* Align text to the left */
        }}
    </style>
    <div class="text-box">
        {{text}}
    </div>
"""

# Inject the custom CSS with st.markdown for the answer container
def apply_custom_container_style(r, g, b, t) -> None:
    custom_container_css = f"""
    <style>
    .translucent-container {{
        background-color: rgba({r}, {g}, {b}, {t}); /* {t*100}% transparent */
    }}
    </style>
    """
    st.markdown(custom_container_css, unsafe_allow_html=True)
    
def set_sidebar_size():
    st.markdown(
        """
       <style>
       [data-testid="stSidebar"][aria-expanded="true"]{
           min-width: 450px;
           max-width: 450px;
       }
       """,
        unsafe_allow_html=True,
    )

def hide_top_right_menu() -> None:
        """
        Hide the Streamlit hamburger / deploy / status chrome and make the
        page header transparent so the grey bar disappears — without
        hiding the header element itself, since it contains the sidebar
        collapse/expand chevron.
        """
        hide_hamburger_menu = """
                <style>
                #MainMenu {visibility: hidden;}
                footer {visibility: hidden;}

                /* Make the header transparent (no grey bar) but keep it
                   in the DOM and clickable so the chevron still works. */
                header[data-testid="stHeader"],
                header.stAppHeader,
                header {
                    background: transparent !important;
                    box-shadow: none !important;
                }

                /* Hide ONLY the specific chrome pieces. Do NOT add wrapper
                   test-ids like stToolbar or stHeaderActionElements — in
                   Streamlit 1.46 those wrappers also contain the sidebar
                   chevron, and hiding them takes the chevron with them. */
                [data-testid="stMainMenu"],
                [data-testid="stDeployButton"],
                [data-testid="stStatusWidget"] {
                    visibility: hidden !important;
                }
                </style>
                """
        st.markdown(hide_hamburger_menu, unsafe_allow_html=True)
    
def hide_footer_caption() -> None:
    """
    Hides the 'made with streamlit' footer.
    """
    hide_footer = """<style>
            footer {visibility: hidden;}
            </style> 
        """
    st.markdown(hide_footer, unsafe_allow_html=True)
 
def hide_sidebar_menu() -> None:
    """
    Hides the streamlit sidebar menu.
    """
    hide_sidebar= """
    <style>
    [data-testid="stSidebar"][aria-expanded="true"] > div:first-child {
        visibility:hidden;
        width: 0px;
    }
    [data-testid="stSidebar"][aria-expanded="false"] > div:first-child {
        visibility:hidden;
    }
    </style>
    """
    st.markdown(hide_sidebar, unsafe_allow_html=True)
  
def set_streamlit_theme() -> None:
    """
    Sets the streamlit theme.
    """
    streamlit_theme = """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@100&display=swap');

    html, body, [class*="css"]  {
        font-family: "Source Sans Pro", sans-serif;
    }
    </style>
    """
    st.markdown(streamlit_theme, unsafe_allow_html=True)

def apply_roboto_font() -> None:
    """
    Applies the Roboto font to the app.
    """
    roboto_font = """
			<style>
			@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400&display=swap');

			html, body, [class*="css"]  {
			font-family: 'Roboto'; font-size: 15px; font-weight: 400 !important; font-style: normal !important;
			}
			</style>
			"""
    st.markdown(roboto_font, unsafe_allow_html=True)
    
def define_divider() -> None:
    """
    Defines a custom button style.
    """
    custom_divider_css = """
    <style>
        /* Reduce space around dividers */
        .stDivider {
            margin-top: 1px;
            margin-bottom: 1px;
        }
    """
    st.markdown(custom_divider_css, unsafe_allow_html=True)
    
def define_expander() -> None:
    """
    Defines a custom button style.
    """
    custom_expander_css = """
    <style>
        .st-eb { /* Targets expander button, which is the label of the expander */
            font-size: 15px !important; /* Smaller font size */
        }
    </style>
    """
    st.markdown(custom_expander_css, unsafe_allow_html=True)
    
def create_footer(footer_text):
    footer = f"""
    <style>
    a:link , a:visited{{
    color: blue;
    background-color: transparent;
    text-decoration: underline;
    }}

    a:hover,  a:active {{
    color: red;
    background-color: transparent;
    text-decoration: underline;
    }}

    .footer {{
    position: fixed;
    left: 0;
    bottom: 0;
    width: 100%;
    background-color: transparent;
    color: #888;
    text-align: center;
    font-size: 14px;
    }}
    </style>
    <div class='footer'>
    <p>{footer_text}</p>
    </div>
    """
    return footer

def apply_table_styles(table_outline_color: str = "#007BFF",             header_bg_color: str = "#007BFF",
                       header_text_color: str = "white", row_zebra_color: str = "#f2f2f2",
                       text_align: str = "left", padding: str = "8px") -> None:
    """
    Apply custom CSS styles to tables.

    :param table_outline_color: Color of the table borders and cell borders.
    :param header_bg_color: Background color for the table header.
    :param header_text_color: Text color for the table header.
    :param row_zebra_color: Background color for even rows for zebra striping.
    :param text_align: Horizontal alignment of the text in the cells.
    :param padding: Padding inside the cells.
    """
    st.markdown(f"""
    <style>
    table {{
        border-collapse: collapse;
        width: 100%;
    }}
    th, td {{
        border: 1px solid {table_outline_color};
        text-align: {text_align};
        padding: {padding};
    }}
    th {{
        background-color: {header_bg_color};
        color: {header_text_color};
        font-weight: 600;
        border-bottom: 2px solid rgba(128, 128, 128, 0.5);
    }}
    tr:nth-child(even) {{background-color: {row_zebra_color};}}
    </style>
    """, unsafe_allow_html=True)

def write_centered_gif(gif_path: str, width: int = 300, height: int = 300) -> None:
    # CSS for centering
    centering_css = """
        <style>
        .centered-gif {
            display: flex;
            justify-content: center;
            margin-top: -100px;  /* Adjust this value to control space between header and GIF */
        }
        </style>
    """
    st.markdown(centering_css, unsafe_allow_html=True)
    st.markdown(f"<div class='centered-gif'><img src='{gif_path}'></div>", unsafe_allow_html=True)
    
def define_custom_button() -> None:
    """
    Defines custom button layout style. Colors are handled by apply_dynamic_colors().
    """
    custom_button_css = """
    <style>
        div.stButton > button {
            font-size: 5px !important; /* Set font size */
            text-align: left !important; /* Align text to the left */
            min-height: 8px !important; /* Reduce minimum height */
            padding: 0px 5px !important; /* Reduce padding */
            transition: background-color 0.3s, color 0.3s !important; /* Smooth transition for hover effect */
            display: flex !important; /* Use flexbox to align content */
            align-items: center !important; /* Center items vertically */
            justify-content: flex-start !important; /* Align items to the start (left) */
        }
    </style>
    """
    st.markdown(custom_button_css, unsafe_allow_html=True)
    
def create_scroll_to_top_button():
    button_html = """
    <style>
    .scroll-to-top {
        position: fixed; /* Fixed position relative to the viewport */
        right: 20px; /* Positioned from the right of the viewport */
        top: 20px; /* Positioned from the top of the viewport */
        cursor: pointer;
        border: 1px solid #ccc; /* Border for visibility */
        border-radius: 50%; /* Circular shape */
        width: 30px;
        height: 30px;
        text-align: center;
        vertical-align: middle;
        line-height: 30px; /* Center the arrow vertically */
        font-size: 24px;
        z-index: 999; /* High z-index to ensure it's on top */
    }
    </style>
    <div>
        <a href="#page-top" class="scroll-to-top">&#8681;</a> <!-- Unicode up arrow for scroll-to-top -->
    </div>
    """
    return button_html

def create_scroll_to_bottom_button():
    button_html = """
    <style>
    .scroll-to-bottom {
        position: fixed; /* Use fixed for viewport-relative positioning */
        right: 20px;
        bottom: 60px;
        top: 10px;
        color: white;
        border: 1px solid #ccc; /* Border for visibility */
        border-radius: 50%; /* Circular shape */
        width: 30px;
        height: 30px;
        text-align: center;
        vertical-align: middle;
        line-height: 30px; /* Center the arrow vertically */
        font-size: 24px;
        z-index: 999; /* High z-index to ensure it's on top */
    }
    </style>
    <div>
        <a href="#page-bottom" class="scroll-to-bottom">&#8679;</a> <!-- Unicode down arrow -->
    </div>
    """
    return button_html

def show_title(app_title, app_version, copyright, teoco_logo, app_long_name):
    title_text_color = ss.get('__text_color', '#F5F5F5')
    with st.sidebar:
        st.markdown(f"""
                    <h1 style='text-align: center; color: #8B1F2B; margin-top: -10px; padding-top: 0; padding-bottom: 0;'>{app_title}</h1>
                    <div style='color: {title_text_color}; font-size: 12px; text-align: center; width: 100%;'>{app_version}</div>
                    <div style='color: {title_text_color}; font-size: 12px; text-align: center; width: 100%;'>Manual version: {manual_version}</div>
                    <div style='height: 0px;'></div> <!-- This adds vertical space -->
                    <div style='color: {title_text_color}; font-size: 12px; text-align: center; width: 100%;'>{copyright}</div>
                    """, unsafe_allow_html=True)
        st.divider()
    st.markdown("""
    <style>
    .centered-gif {{
        display: flex;
        justify-content: center;
        margin-top: -20px; !important
    }}
    </style>
    <div class='centered-gif'><img src='{0}' height='50'></div>
    """.format(teoco_logo), unsafe_allow_html=True)
    # Adjusted header with reduced top margin
    long_name_color = ss.get('__text_color', '#F5F5F5')
    st.markdown(f"<div style='text-align: center; color: {long_name_color}; margin-top: 10px; padding-top: 0; font-size: 16px;'>{app_long_name}</div>", unsafe_allow_html=True)

    return None
    
def show_footer(footer_text):
    # Create and display the footer
    st.markdown(create_footer(footer_text), unsafe_allow_html=True)
    return None

def show_book_open_close_gif():
    
    write_centered_gif(f'{book_open_close_gif_path}')

def create_scroll_to_top_button():
    button_html = """
    <style>
    .scroll-to-top {
        position: fixed; /* Fixed position relative to the viewport */
        right: 20px; /* Positioned from the right of the viewport */
        top: 20px; /* Positioned from the top of the viewport */
        cursor: pointer;
        border: 1px solid #ccc; /* Border for visibility */
        border-radius: 50%; /* Circular shape */
        width: 30px;
        height: 30px;
        text-align: center;
        vertical-align: middle;
        line-height: 30px; /* Center the arrow vertically */
        font-size: 24px;
        z-index: 999; /* High z-index to ensure it's on top */
    }
    </style>
    <div>
        <a href="#page-top" class="scroll-to-top">&#8681;</a> <!-- Unicode up arrow for scroll-to-top -->
    </div>
    """
    return button_html

def create_scroll_to_bottom_button():
    button_html = """
    <style>
    .scroll-to-bottom {
        position: fixed; /* Use fixed for viewport-relative positioning */
        right: 20px;
        bottom: 60px;
        top: 10px;
        color: white;
        border: 1px solid #ccc; /* Border for visibility */
        border-radius: 50%; /* Circular shape */
        width: 30px;
        height: 30px;
        text-align: center;
        vertical-align: middle;
        line-height: 30px; /* Center the arrow vertically */
        font-size: 24px;
        z-index: 999; /* High z-index to ensure it's on top */
    }
    </style>
    <div>
        <a href="#page-bottom" class="scroll-to-bottom">&#8679;</a> <!-- Unicode down arrow -->
    </div>
    """
    return button_html

def show_main_area_image():
    st.markdown("""
    <style>
    .centered-image {{
        display: flex;
        justify-content: center;
        
    }}
    </style>
    <div class='centered-image'><img src='{0}' height=600></div>
    """.format(main_page_image_path), unsafe_allow_html=True)

def apply_dynamic_colors() -> None:
    main_color = ss.get('__main_area_color', '#0e1117')
    sidebar_color = ss.get('__sidebar_color', '#262730')
    text_color = ss.get('__text_color', '#F5F5F5')
    question_textbox = ss.get('__question_textbox_color', '#262730')
    question_bg = ss.get('__question_bg_color', '#475063')
    answer_bg = ss.get('__answer_bg_color', '#2b313e')
    expander_color = ss.get('__expander_color', '#262730')
    username_bg = ss.get('__username_bg_color', '#1a1a2e')
    button_color = ss.get('__button_color', '#262730')
    button_label_color = ss.get('__button_label_color', '#F5F5F5')
    button_hover = ss.get('__button_hover_color', '#8B1F2B')

    dynamic_css = f"""
    <style>

    /* ===== GLOBAL BACKGROUND ===== */
    html, body,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="stMain"] > div,
    [data-testid="stMain"] [data-testid="stVerticalBlock"] {{
        background-color: {main_color} !important;
    }}

    /* ===== SIDEBAR ===== */
    [data-testid="stSidebar"] > div:first-child {{
        background-color: {sidebar_color} !important;
    }}

    [data-testid="stSidebar"] *,
    [data-testid="stMain"] [data-testid="stMarkdownContainer"],
    .chat-message .message {{
        color: {text_color} !important;
    }}

    /* Synth panel override: the question + answer + source cards must show
       BLACK text regardless of the active BIDA theme. Multiple selector
       variants to win specificity against any wrapper Streamlit may inject. */
    .synth-panel-text, .synth-panel-text *,
    .synth-source-pre, .synth-source-pre *,
    .synth-source-header, .synth-source-header *,
    body .synth-panel-text, body .synth-panel-text *,
    body .synth-source-pre, body .synth-source-pre *,
    body .synth-source-header, body .synth-source-header *,
    [data-testid="stApp"] .synth-panel-text, [data-testid="stApp"] .synth-panel-text *,
    [data-testid="stApp"] .synth-source-pre, [data-testid="stApp"] .synth-source-pre *,
    [data-testid="stApp"] .synth-source-header, [data-testid="stApp"] .synth-source-header *,
    [data-testid="stMain"] [data-testid="stMarkdownContainer"] .synth-panel-text,
    [data-testid="stMain"] [data-testid="stMarkdownContainer"] .synth-panel-text *,
    [data-testid="stMain"] [data-testid="stMarkdownContainer"] .synth-source-pre,
    [data-testid="stMain"] [data-testid="stMarkdownContainer"] .synth-source-pre *,
    [data-testid="stMain"] [data-testid="stMarkdownContainer"] .synth-source-header,
    [data-testid="stMain"] [data-testid="stMarkdownContainer"] .synth-source-header *,
    [data-testid="stMain"] [data-testid="stMarkdown"] .synth-panel-text,
    [data-testid="stMain"] [data-testid="stMarkdown"] .synth-panel-text *,
    [data-testid="stMain"] [data-testid="stMarkdown"] .synth-source-pre,
    [data-testid="stMain"] [data-testid="stMarkdown"] .synth-source-pre *,
    [data-testid="stMain"] [data-testid="stMarkdown"] .synth-source-header,
    [data-testid="stMain"] [data-testid="stMarkdown"] .synth-source-header * {{
        color: #000000 !important;
    }}

    /* ===== INPUT ===== */
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stTextArea"] div[data-baseweb="textarea"],
    [data-testid="stTextArea"] div[data-baseweb="base-input"] {{
        background-color: #ffffff !important;
        color: #1a1a2e !important;
    }}
    /* Thin dark-red outline on text-input controls (the BaseWeb wrapper holds
       the border; some inputs render with no visible outline otherwise). */
    [data-testid="stTextInput"] div[data-baseweb="input"],
    [data-testid="stTextInput"] div[data-baseweb="base-input"] {{
        border: 1px solid darkred !important;
        border-radius: 6px !important;
    }}
    /* Let text areas grow with their content so the white box ELONGATES as
       text is typed/pasted, instead of scrolling inside a fixed height.
       field-sizing:content is supported in modern Chrome; height:auto
       overrides Streamlit's inline fixed height. */
    [data-testid="stTextArea"] textarea {{
        field-sizing: content !important;
        height: auto !important;
        min-height: 120px !important;
        max-height: 70vh !important;
    }}

    /* ===== CHAT ===== */
    .chat-message.user {{ background-color: {question_bg} !important; }}
    .chat-message.bot {{ background-color: {answer_bg} !important; }}

    /* ===== EXPANDER (SAFE SCOPED) ===== */
    [data-testid="stExpander"] {{
        background-color: {expander_color} !important;
        border-radius: 8px !important;
    }}

    /* Only style the header */
    [data-testid="stExpander"] summary {{
        color: {text_color} !important;
        background-color: {expander_color} !important;
    }}

    /* Only style the CONTENT area (not everything inside blindly) */
    [data-testid="stExpanderDetails"] {{
        background-color: {expander_color} !important;
        color: {text_color} !important;
    }}

    div.stButton > button,
    [data-testid="stSidebar"] button,
    [data-testid="stFormSubmitButton"] button,
    button[data-testid^="stBaseButton"] {{
        background-color: {button_color} !important;
        color: {button_label_color} !important;
        border-color: {button_label_color} !important;

        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        padding: 0.4rem 0.75rem !important;
        border-radius: 8px !important;
    }}

    /* Restore normal sizing for form-submit buttons — the global
       div.stButton > button rule from define_custom_button() collapses
       them to font-size:5px / min-height:8px (suitable for the tiny
       chat-history list buttons in the sidebar but invisible in form
       contexts). Higher specificity beats that. */
    [data-testid="stFormSubmitButton"] button,
    [data-testid="stForm"] [data-testid="stFormSubmitButton"] button,
    div[data-testid="stFormSubmitButton"] > button {{
        font-size: 14px !important;
        min-height: 36px !important;
        padding: 0.4rem 0.9rem !important;
        text-align: center !important;
        justify-content: center !important;
        border: 1px solid {button_label_color} !important;
    }}

    /* ===== BUTTON HOVER ===== */
    div.stButton > button:hover,
    [data-testid="stSidebar"] button:hover,
    [data-testid="stFormSubmitButton"] button:hover,
    button[data-testid^="stBaseButton"]:hover {{
        background-color: {button_hover} !important;
        color: #FFFFFF !important;
        border-color: {button_hover} !important;
    }}

    /* ===== INNER CONTENT FIX (targeted, not destructive) ===== */
    button span,
    button p,
    button [data-testid="stMarkdownContainer"],
    button [data-testid="stMarkdownContainer"] * {{
        color: inherit !important;
        background-color: transparent !important;
    }}

    /* ===== HOVER TEXT ===== */
    button:hover span,
    button:hover p,
    button:hover [data-testid="stMarkdownContainer"],
    button:hover [data-testid="stMarkdownContainer"] * {{
        color: #FFFFFF !important;
    }}
    
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stTextArea"] div[data-baseweb="textarea"],
    [data-testid="stTextArea"] div[data-baseweb="base-input"] {{
        background-color: #ffffff !important;
        color: #1a1a2e !important;
        caret-color: #1a1a2e !important;
    }}

    /* ===== EXPANDER BUTTON FIX ===== */
    [data-testid="stExpander"] button,
    [data-testid="stExpander"] button * {{
        color: {button_label_color} !important;
    }}

    [data-testid="stExpander"] button:hover,
    [data-testid="stExpander"] button:hover * {{
        color: #FFFFFF !important;
    }}

    /* ===== CHECKBOX ===== */
    [data-baseweb="checkbox"] span[role="checkbox"] {{
        border-color: {text_color} !important;
    }}

    /* ===== RED TEXT OVERRIDE ===== */
    span[style*="rgb(255, 75, 75)"],
        span[style*="#ff4b4b"],
        span[style*="#FF4B4B"] {{
            color: #8B1F2B !important;
    }}

    /* ===== SELECT BOX ===== */
    [data-baseweb="select"] > div,
    [data-baseweb="select"] span {{
        background-color: {main_color} !important;
        color: {text_color} !important;
    }}

    /* ===== DROPDOWN / OVERLAY ===== */
    [data-baseweb="popover"],
    [data-baseweb="popover"] *,
    ul[data-baseweb="menu"],
    div[role="listbox"],
    ul[data-baseweb="menu"] li,
    div[role="option"] {{
        background-color: {main_color} !important;
        color: {text_color} !important;
    }}

    /* ===== DROPDOWN HOVER ===== */
    ul[data-baseweb="menu"] li:hover,
    div[role="option"]:hover {{
        background-color: {button_hover} !important;
        color: #FFFFFF !important;
    }}

    </style>
    """
    st.markdown(dynamic_css, unsafe_allow_html=True)

def apply_custom_page_settings() -> None:
    hide_top_right_menu()
    # Write custom CSS
    st.write(css_old, unsafe_allow_html=True)
    hide_footer_caption()
    define_custom_button()
    define_divider()
    define_expander()
    set_streamlit_theme()
    apply_roboto_font()
    apply_table_styles(table_outline_color = ss.get('__text_color', '#F5F5F5'), header_bg_color = ss.get('__main_area_color', '#0e1117'),
                       header_text_color = header_text_color, row_zebra_color = ss.get('__sidebar_color', '#262730'),
                       text_align = text_align, padding = padding)
    apply_custom_container_style(custom_container_red, custom_container_green, custom_container_blue, custom_container_alpha)
    apply_dynamic_colors()
    # apply_custom_code_block_css()
    #set_expander_color_white()