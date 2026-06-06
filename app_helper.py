import streamlit as st
import time
from utils.logging_utils import *
import os
from dotenv import load_dotenv
from utils.bida_prompt_utils import *
# from decouple import config
from utils.sys_utils import *
from vars.s_state import *
from utils.summarizer_utils import *
from html_css_templates import *
from utils.chat_utils import *
from utils.stopwatch_utils import *
from utils.query_vectorstore_utils import (
    return_docs_from_vectorstore_parallel,
    return_docs_from_both_collections_parallel,
    combine_text_and_image_docs
)
from utils.acronym_utils import *
from utils.string_utils import extract_without_breaking_words, enhance_question_for_llm
from consts.consts import COLOR_ELEMENT_LABELS, COLOR_LABEL_TO_KEY, COLOR_ELEMENT_DEFAULTS, COLOR_DARK_DEFAULTS, COLOR_LIGHT_DEFAULTS
from core.llm_client import call_llm
from core.rag import retrieve, compose_messages
from core.gap_detection import GapMetadata, parse_metadata_trailer, record_gap
import torch

GAPS_DB_PATH = "gaps.db"

torch.classes.__path__ = []
    
def resize_image_in_html(html_message):
    """
    Adjust the image in the HTML message to be responsive.
    """
    img_tag_pattern = re.compile(r'<img src=\'([^\']+)\' alt=\'([^\']*)\' height=(\d+)>')
    matches = img_tag_pattern.findall(html_message)
    
    if not matches:
        return html_message
    
    for match in matches:
        src, alt, height = match
        resized_tag = f"<img src='{src}' alt='{alt}' style='width: 100%; height: auto;'>"
        html_message = html_message.replace(f"<img src='{src}' alt='{alt}' height={height}>", resized_tag)
    
    return html_message

def ask_ada(answer_placeholder, chunks, question, chat_history, keep_chat_history):
    """Stream LLM text chunks to a Streamlit placeholder with inline <img>
    and $LaTeX$ accumulation, then commit the final answer to chat_history.

    `chunks` is an Iterator[str] from core.llm_client.call_llm(stream=True).
    The OpenAI request, retries, and prompt assembly all happen upstream in
    process_user_prompt → core.rag / core.llm_client.
    """
    bot_message = ''
    st.write(css_old, unsafe_allow_html=True)

    try:
        blinking_symbol = blinking_pencil
        current_text_with_symbol = bot_message + blinking_symbol
        answer_placeholder.markdown(bot_template.replace("{{MSG}}", current_text_with_symbol), unsafe_allow_html=True)

        accumulating = False
        accumulator = ""
        special_token = None

        # Throttle UI updates + save partial answer for crash recovery.
        # Updating the placeholder per-character floods the Streamlit
        # websocket (~4k messages for a 4k-token answer) and increases the
        # chance of disconnect mid-stream.
        CHAR_UPDATE_INTERVAL = 30
        chars_since_update = 0
        ss._pending_question = question
        ss._pending_answer = ""

        # Pattern matches a FULLY-FORMED <img> tag (V6 alt text may contain
        # '>' characters, so plain "accumulator endswith '>'" terminates early).
        _IMG_COMPLETE_RE = re.compile(
            r"<img\s+src='[^']+'(?:\s+alt='.*?')?\s*(?:height=\d+\s*)?>",
            re.DOTALL,
        )

        for partial_msg in chunks:
            if partial_msg:
                for char in partial_msg:
                    force_update = False
                    if accumulating:
                        accumulator += char
                        if special_token == "<img" and char == '>' and _IMG_COMPLETE_RE.fullmatch(accumulator):
                            try:
                                bot_message += convert_img_tags_to_embedded(accumulator)
                            except Exception as _e:
                                log_message('warning', f"Inline img base64 conversion failed: {_e}")
                                bot_message += accumulator
                            blinking_symbol = blinking_pencil
                            accumulating = False
                            accumulator = ""
                            special_token = None
                            force_update = True
                        elif special_token == "$" and char == '$':
                            bot_message += f'<span class="latex">{accumulator}</span>'
                            blinking_symbol = blinking_pencil
                            accumulating = False
                            accumulator = ""
                            special_token = None
                            force_update = True
                    else:
                        if char == '<':
                            accumulating = True
                            accumulator += char
                            special_token = "<img"
                            blinking_symbol = blinking_image
                            force_update = True
                        elif char == '$':
                            accumulating = True
                            accumulator += char
                            special_token = "$"
                            blinking_symbol = blinking_lambda
                            force_update = True
                        else:
                            bot_message += char
                            chars_since_update += 1

                    if force_update or chars_since_update >= CHAR_UPDATE_INTERVAL:
                        current_text_with_symbol = bot_message + blinking_symbol
                        answer_placeholder.markdown(bot_template.replace("{{MSG}}", current_text_with_symbol), unsafe_allow_html=True)
                        ss._pending_answer = bot_message
                        chars_since_update = 0

        # Safety: if the stream ended while still accumulating an <img> or $LaTeX$
        # (e.g., model truncated mid-tag, or the tag didn't match our regex),
        # flush the accumulator so its content isn't silently dropped.
        if accumulating and accumulator:
            log_message(
                'warning',
                f"Stream ended mid-{special_token} with {len(accumulator)} unflushed chars"
            )
            if special_token == "<img":
                try:
                    bot_message += convert_img_tags_to_embedded(accumulator)
                except Exception:
                    bot_message += accumulator
            else:
                bot_message += accumulator
            accumulator = ""
            accumulating = False

        current_text_with_symbol = bot_message + blinking_symbol
        answer_placeholder.markdown(bot_template.replace("{{MSG}}", current_text_with_symbol), unsafe_allow_html=True)
        ss._pending_answer = bot_message
        answer_placeholder.empty()

        bot_message = bot_message.strip()
        # Strip the [[META]] trailer the LLM emitted (per system_prompt) before
        # the answer goes into chat history or the persistent UI. The brief
        # visibility of the trailer during streaming is acceptable.
        bot_message, gap_metadata = parse_metadata_trailer(bot_message)
        ss._pending_answer = bot_message

        log_message("info", "*********************")
        log_message("info", f"Answer: {bot_message}")
        log_message("info", f"Gap metadata: confidence={gap_metadata.confidence} missing={gap_metadata.missing_info!r}")
        log_message("info", "*********************")
        if keep_chat_history:
            chat_history.append(("user", question))
            # Strip embedded base64 image data before storing in chat_history.
            # Otherwise the next turn's prompt embeds tens of KB of base64 per
            # screenshot (chat_history is serialized inline into the prompt),
            # the model can mimic that pattern and start emitting base64 of
            # its own which gets cut off by max_completion_tokens — leaving
            # the response with an unclosed <img src='data:...> tag.
            history_clean = re.sub(
                r"<img\s+src='data:image/[^']+'[^>]*>",
                "[image]",
                bot_message,
                flags=re.DOTALL,
            )
            if ss.__summarize_chat_history:
                summarized_bot_message = summarize_based_on_question(question, history_clean)
                log_message("info", f"Summarized Answer: {summarized_bot_message}")
                log_message("info", "*")
                chat_history.append(("assistant", summarized_bot_message))
            else:
                chat_history.append(("assistant", history_clean))

        return bot_message, 1, gap_metadata

    except Exception as e:
        log_message('error', f"ask_ada streaming error: {e}")
        failure_message = "Failed to get response after multiple retries. Please try again later."
        answer_placeholder.markdown(f'<div class="message">{failure_message}</div>', unsafe_allow_html=True)
        return failure_message, -1, GapMetadata()

def save_llm_parameters():
    try:
        settings_keys = {key: ss[key] for key in ss.keys() if key.startswith('__')}
        with open(settings_json_file_name, "w", encoding='utf') as settings_file:
            json.dump(settings_keys, settings_file, indent = 4)
        log_message("info", f"settings saved: model name: {ss.__qa_model_name}, temperature: {ss.__temperature}, max tokens: {ss.__max_tokens},\
                    Max tokens chat history: {ss.__max_tokens_chat_history}, Frequency penalty: {ss.__frequency_penalty}, Presence Penalty: {ss.__presence_penalty}, n: {ss.__n}, \
                    Top_p: {ss.__top_p}, stop: {ss.__stop}, streaming: {ss.__streaming}")
        st.toast("Settings Applied!")
    except Exception as e: 
        log_message("error", f"Error saving settings to file {settings_json_file_name}: {e}")

def show_status(status_placeholder, status_message, animation_gif_path):
    text_color = ss.get("__text_color")

    status_placeholder.markdown(
        f"""
        <div class="status-box" style="display: flex; align-items: center;">
            <img src="{animation_gif_path}" style="margin-right: 10px; margin-bottom: 10px;">
            <p style="color: {text_color};">{status_message}</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    
def show_sidebar_content():
    with st.expander("Settings", expanded=False):
        ss.show_appraisal_widgets = st.checkbox(label="Mode") #, on_change=handleToggle)
        if ss.show_appraisal_widgets:
            st.markdown("<div style='color: #8B1F2B; font-size: 12px; text-align: left; margin-top: 0px; width: 100%;'>Chat and Appraise</div>", unsafe_allow_html=True)
            ss.filter_appraised = st.checkbox("Filter", value=False)
            if ss.filter_appraised:
                st.markdown("<div style='color: #8B1F2B; font-size: 12px; text-align: left; margin-top: 0px; width: 100%;'>Skip Completed</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='color: #8B1F2B; font-size: 12px; text-align: left; margin-top: 0px; width: 100%;'>Show All</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='color: #8B1F2B; font-size: 12px; text-align: left; margin-top: 0px; width: 100%;'>Only Chat</div>", unsafe_allow_html=True)

        if ss.role == "superuser":
            model_names = ["gpt-5.4", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo", "gpt-3.5-turbo-16k"]
            st.divider()
            st.write("$\\footnotesize{\\textsf{LLM Properties}}$")
            ss.__qa_emailing_enabled = st.checkbox(':red[Email QA]', value=ss.__qa_emailing_enabled)
            ss.__qa_history_enabled = st.checkbox(':red[Enable Chat history]', value=ss.__qa_history_enabled)
            if ss.__qa_history_enabled:
                ss.__summarize_chat_history = st.checkbox(':red[Summarize Chat history]', value=ss.__summarize_chat_history)
            # Get current model index, default to 0 if not found
            current_model_index = model_names.index(ss.__qa_model_name) if ss.__qa_model_name in model_names else 0
            ss.__qa_model_name = st.selectbox(':red[QA model]', options=model_names, index=current_model_index)
            ss.__temperature = st.slider(':red[Temperature]', min_value=0.0, max_value=1.0, step=0.05, value=ss.__temperature)
            ss.__max_tokens = st.slider(':red[Max tokens]', min_value=1000, max_value=4000, step=100, value=ss.__max_tokens)
            ss.__max_tokens_chat_history = st.slider(':red[Max tokens chat history]', min_value=1000, max_value=4000, step=100, value=ss.__max_tokens_chat_history)
            ss.__top_p = st.slider(':red[Top_p]', min_value=0.0, max_value=1.0, step=0.05, value=ss.__top_p)
            ss.__presence_penalty = st.slider(':red[Presence_penalty]', min_value=0.0, max_value=2.0, step=0.05, value=ss.__presence_penalty)
            ss.__frequency_penalty = st.slider(':red[Frequency_penalty]', min_value=0.0, max_value=2.0, step=0.05, value=ss.__frequency_penalty)
            if st.button(label = "Apply"):
                save_llm_parameters()
                st.rerun()

def apply_pending_color_theme():
    """Apply pending Dark/Light theme. Must be called BEFORE any rendering
    (show_title, apply_dynamic_colors, show_color_settings) so that all
    session state values are current when CSS and HTML are generated."""
    pending = ss.get('_pending_theme', None)
    if pending == 'dark':
        for key, default in COLOR_DARK_DEFAULTS.items():
            ss[key] = default
            ss[f"color_picker_{key}"] = default
        ss._pending_theme = None
        save_llm_parameters()
    elif pending == 'light':
        for key, default in COLOR_LIGHT_DEFAULTS.items():
            ss[key] = default
            ss[f"color_picker_{key}"] = default
        ss._pending_theme = None
        save_llm_parameters()

def show_color_settings():
    with st.expander("Appearance", expanded=False):
        # Per-element customization (dropdown + color picker + Apply) is
        # restricted to superusers — regular users only need a way to
        # toggle between the Dark and Light presets.
        is_superuser = ss.get("role") == "superuser"

        if is_superuser:
            selected_label = st.selectbox(
                "Element",
                options=COLOR_ELEMENT_LABELS,
                key="sel_color_element"
            )
            ss_key = COLOR_LABEL_TO_KEY[selected_label]
            current_color = ss.get(ss_key, COLOR_ELEMENT_DEFAULTS[ss_key])
            picked = st.color_picker(
                selected_label,
                value=current_color,
                key=f"color_picker_{ss_key}"
            )
            ss[ss_key] = picked

            col_apply, col_dark, col_light = st.columns(3)
            with col_apply:
                if st.button(label="Apply", key="color_apply"):
                    save_llm_parameters()
                    st.rerun()
        else:
            col_dark, col_light = st.columns(2)

        with col_dark:
            if st.button(label="Dark", key="color_dark"):
                ss._pending_theme = 'dark'
                st.rerun()
        with col_light:
            if st.button(label="Light", key="color_light"):
                ss._pending_theme = 'light'
                st.rerun()

def show_quiz_sidebar():
    """Sidebar Quiz expander — for any signed-in user. Tests on the
    HITL-validated knowledge. Clicking Start picks a random question and
    surfaces it in the main area; subsequent grades + Next questions cycle
    through the validated pool until the user ends the quiz."""
    from core.quiz import get_user_stats, list_quiz_items, pick_next_question

    user_name = ss.get('full_name') or ss.get('user_name') or 'unknown'
    user_key = ss.get('user_name') or user_name  # storage key uses user_id

    try:
        stats = get_user_stats(GAPS_DB_PATH, user_key)
    except Exception as e:
        log_message('error', f"quiz stats lookup failed: {e}")
        stats = {"total": 0, "correct": 0, "accuracy": None}

    with st.expander("Quiz", expanded=False):
        if stats["total"]:
            acc_pct = (stats["accuracy"] or 0) * 100
            st.markdown(
                f'<p style="color:#9aa0a6;font-size:0.85em;margin:0.25rem 0;">'
                f'Lifetime: {stats["correct"]} / {stats["total"]} '
                f'({acc_pct:.0f}%)</p>',
                unsafe_allow_html=True,
            )

        active = ss.get('_quiz_active', False)
        if not active:
            if st.button("Start quiz", key="quiz_start", use_container_width=True):
                # Quiz pool = synthetic_questions generated from the vectorstore
                # (via Auto Q&A / Gap Finder). Each row already has a cached
                # answer that we grade against.
                items = list_quiz_items(GAPS_DB_PATH)
                if not items:
                    st.warning(
                        "No quiz questions yet. Open the **Auto Q&A** "
                        "(or Knowledge Gap Finder) expander and click "
                        "Generate question a few times to build a pool."
                    )
                else:
                    close_all_main_panels()
                    ss._quiz_active = True
                    ss._quiz_items = items
                    ss._quiz_seen_ids = set()
                    ss._quiz_session_score = (0, 0)
                    ss._quiz_last_result = None
                    pick = pick_next_question(items)
                    ss._quiz_current = pick
                    st.rerun()
        else:
            session_correct, session_total = ss.get('_quiz_session_score', (0, 0))
            st.markdown(
                f'<p style="color:#9aa0a6;font-size:0.85em;margin:0.25rem 0;">'
                f'This session: {session_correct} / {session_total}</p>',
                unsafe_allow_html=True,
            )
            if st.button("End quiz", key="quiz_end", use_container_width=True):
                ss._quiz_active = False
                ss._quiz_current = None
                ss._quiz_last_result = None
                st.rerun()


def show_quiz_main() -> bool:
    """Render the quiz question + grading + Next-question loop in the main
    area while a quiz session is active. Returns True if rendered."""
    if not ss.get('_quiz_active'):
        return False
    _, _quiz_close_col = st.columns([6, 1])
    with _quiz_close_col:
        if st.button("Close", key="quiz_main_close", use_container_width=True):
            close_all_main_panels()
            st.rerun()
    current = ss.get('_quiz_current')
    if not current:
        # All questions seen — show summary
        sc, st_ = ss.get('_quiz_session_score', (0, 0))
        st.markdown(
            f'<div class="synth-panel-text" style="background-color:{ss.get("__expander_color", "#DFE2E2")};'
            f'padding:0.75rem 1rem;border-radius:6px;margin:0.5rem 0;">'
            f'<h3 style="margin:0;">Quiz complete</h3>'
            f'<p>You scored {sc} / {st_} this session.</p>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("Restart quiz", key="quiz_restart"):
            ss._quiz_seen_ids = set()
            ss._quiz_session_score = (0, 0)
            ss._quiz_last_result = None
            from core.quiz import pick_next_question
            ss._quiz_current = pick_next_question(ss.get('_quiz_items') or [])
            st.rerun()
        return True

    from core.quiz import generate_mcq_options, pick_next_question, record_attempt

    panel_bg = ss.get('__expander_color', '#DFE2E2')

    # Force dark text on the radio answer choices — the app's theme text color is
    # light, so without this the options render white-on-light (invisible).
    st.markdown(
        """
        <style>
        [data-testid="stRadio"] label,
        [data-testid="stRadio"] label p,
        [data-testid="stRadio"] label div {
            color: #1a1a2e !important;
            -webkit-text-fill-color: #1a1a2e !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div class="synth-panel-text" style="background-color:{panel_bg};'
        f'padding:0.5rem 0.75rem;border-radius:6px 6px 0 0;">'
        f'<h3 style="margin:0;">Quiz</h3>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="synth-panel-text" style="background-color:{panel_bg};'
        f'padding:0.75rem 1rem;border-radius:0 0 6px 6px;margin:0 0 0.5rem 0;">'
        f'<strong>Q:</strong> {current["question"]}'
        f'</div>',
        unsafe_allow_html=True,
    )

    last = ss.get('_quiz_last_result')
    if last is not None:
        # Show grading result + Next-question button
        ok = last.get('is_correct')
        banner_bg = "#10b981" if ok else "#ef4444"
        verdict = "Correct" if ok else "Incorrect"
        st.markdown(
            f'<div style="background-color:{banner_bg};color:#ffffff;'
            f'padding:0.5rem 0.9rem;border-radius:6px;margin:0.5rem 0;">'
            f'<strong>{verdict}.</strong> {last.get("feedback") or ""}'
            f'</div>',
            unsafe_allow_html=True,
        )
        if not ok:
            st.markdown(
                f'<div class="synth-panel-text" style="background-color:{panel_bg};'
                f'padding:0.5rem 0.75rem;border-radius:6px;margin:0.5rem 0;">'
                f'<strong>Canonical answer:</strong> {current["canonical_answer"]}'
                f'</div>',
                unsafe_allow_html=True,
            )
        if st.button("Next question", key="quiz_next", type="primary", use_container_width=True):
            seen = ss.get('_quiz_seen_ids', set())
            seen.add(current["id"])
            ss._quiz_seen_ids = seen
            ss._quiz_last_result = None
            ss._quiz_current = pick_next_question(ss.get('_quiz_items') or [], exclude_ids=seen)
            st.rerun()
    else:
        # Build multiple-choice options once per question (cached on the item).
        if not current.get('options'):
            client = ss.get('qa_model')
            model = ss.get('__qa_model_name')
            if not client or not model:
                st.error("LLM client not initialized.")
                st.markdown("---")
                return True
            with st.spinner("Preparing choices…"):
                try:
                    mcq = generate_mcq_options(
                        client=client, model=model,
                        question=current["question"],
                        correct_answer=current["canonical_answer"],
                    )
                except Exception as e:
                    log_message('error', f"MCQ generation failed: {e}")
                    mcq = {"options": [current["canonical_answer"]], "correct_index": 0}
            current['options'] = mcq['options']
            current['correct_index'] = mcq['correct_index']
            ss._quiz_current = current

        with st.form(key=f"quiz_form_{current['id']}", clear_on_submit=False):
            choice = st.radio(
                "Choose the correct answer",
                current['options'],
                index=None,
                key=f"quiz_choice_{current['id']}",
            )
            btn_submit_col, btn_next_col = st.columns(2)
            with btn_submit_col:
                submitted = st.form_submit_button("Submit answer", type="primary", use_container_width=True)
            with btn_next_col:
                skipped = st.form_submit_button("Next", use_container_width=True)
            if skipped and not submitted:
                # Skip without recording — just advance to a new question.
                seen = ss.get('_quiz_seen_ids', set())
                seen.add(current["id"])
                ss._quiz_seen_ids = seen
                ss._quiz_last_result = None
                ss._quiz_current = pick_next_question(
                    ss.get('_quiz_items') or [], exclude_ids=seen
                )
                st.rerun()
            if submitted:
                if choice is None:
                    # Explicit dark text — st.warning renders white-on-light on
                    # this theme (see CLAUDE.md "Active gotchas").
                    st.markdown(
                        '<div style="background-color:#f59e0b;color:#1a1a1a;'
                        'padding:0.5rem 0.9rem;border-radius:6px;margin:0.5rem 0;">'
                        '⚠️ Please select an option before submitting.'
                        '</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    is_correct = current['options'].index(choice) == current.get('correct_index')
                    try:
                        record_attempt(
                            GAPS_DB_PATH,
                            user_name=ss.get('user_name') or 'unknown',
                            kb_doc_id=current.get("id"),
                            question_text=current["question"],
                            canonical_answer=current["canonical_answer"],
                            user_answer=choice,
                            is_correct=is_correct,
                            llm_feedback=None,
                        )
                    except Exception as e:
                        log_message('error', f"quiz record_attempt failed: {e}")
                    sc, total = ss.get('_quiz_session_score', (0, 0))
                    ss._quiz_session_score = (sc + (1 if is_correct else 0), total + 1)
                    ss._quiz_last_result = {
                        "is_correct": is_correct,
                        "feedback": "Correct choice." if is_correct else "That's not the right option.",
                    }
                    st.rerun()

    st.markdown("---")
    return True


def _display_name_for(user_id) -> str:
    """Map a user_id (like 'dn') to its Full Name from users.xlsx. Cached
    in session state on first call. Falls back to the raw id if not found."""
    cache = ss.get('_user_id_to_full_name')
    if cache is None:
        try:
            import pandas as pd
            df = pd.read_excel('users.xlsx')
            cache = {str(uid): str(fn) for uid, fn in zip(df['User ID'], df['Full Name'])}
        except Exception:
            cache = {}
        ss._user_id_to_full_name = cache
    return cache.get(str(user_id), str(user_id))


def _list_superusers() -> list[dict]:
    """Return [{'user_id', 'full_name'}] for every superuser in users.xlsx,
    sorted by full name. Cached per session."""
    cache = ss.get('_superusers_cache')
    if cache is None:
        cache = []
        try:
            import pandas as pd
            df = pd.read_excel('users.xlsx')
            supers = df[df['Role'].astype(str).str.strip().str.lower() == 'superuser']
            cache = [
                {'user_id': str(uid), 'full_name': str(fn)}
                for uid, fn in zip(supers['User ID'], supers['Full Name'])
            ]
            cache.sort(key=lambda r: r['full_name'].lower())
        except Exception as e:
            log_message('error', f"_list_superusers failed: {e}")
            cache = []
        ss._superusers_cache = cache
    return cache


def notify_assignee_via_outlook(*, assignee_user_id: str, gap_id, submitter_name: str,
                                question: str, contribution: str):
    """Stage an Outlook notification e-mail for the assigned reviewer. The actual
    send is gated behind a 'Send email?' confirmation dialog (see
    maybe_confirm_pending_email / _email_confirm_dialog) — this only stashes the
    request in session state; the caller's st.rerun() then pops the dialog. Reads
    the reviewer's e-mail from users.xlsx; if none is on file, warns and stages
    nothing. Never raises — must not block the already-saved assignment."""
    try:
        from core.email_notify import lookup_email
        email = lookup_email(assignee_user_id, "users.xlsx")
        if not email:
            st.warning(
                f"Assignment saved, but no e-mail is on file for "
                f"'{assignee_user_id}' — no notification."
            )
            return
        ss._pending_email_confirm = {
            "assignee_user_id": assignee_user_id,
            "email": email,
            "reviewer_name": _display_name_for(assignee_user_id),
            "submitter_name": submitter_name or "a user",
            "question": question or "",
            "contribution": contribution or "",
            "gap_id": gap_id,
        }
    except Exception as e:
        log_message('error', f"notify_assignee_via_outlook staging failed: {e}")


@st.experimental_dialog("Send email?")
def _email_confirm_dialog():
    """Modal asking the assigner to confirm sending the notification e-mail.
    Reads the staged request from ss._pending_email_confirm. Yes → send via
    Outlook; No → skip. Either way clears the pending state and reruns."""
    info = ss.get('_pending_email_confirm') or {}
    st.markdown(
        f"<div style='color:#1a1a2e;'>Send a notification e-mail to "
        f"<strong>{info.get('reviewer_name', '')}</strong> "
        f"(<code>{info.get('email', '')}</code>) about this assigned Q&amp;A?</div>",
        unsafe_allow_html=True,
    )
    c_yes, c_no = st.columns(2)
    with c_yes:
        if st.button("Yes, send", type="primary", use_container_width=True,
                     key="_email_confirm_yes"):
            try:
                from core.email_notify import notify_assignment
                ok, msg = notify_assignment(
                    assignee_user_id=info.get('assignee_user_id'),
                    reviewer_name=info.get('reviewer_name', ''),
                    submitter_name=info.get('submitter_name', ''),
                    question=info.get('question', ''),
                    contribution=info.get('contribution', ''),
                    gap_id=info.get('gap_id'),
                    users_xlsx_path="users.xlsx",
                )
                st.toast(msg if ok else f"E-mail not sent: {msg}")
            except Exception as e:
                log_message('error', f"_email_confirm_dialog send failed: {e}")
                st.toast(f"E-mail not sent: {e}")
            ss._pending_email_confirm = None
            st.rerun()
    with c_no:
        if st.button("No", use_container_width=True, key="_email_confirm_no"):
            ss._pending_email_confirm = None
            st.toast("Notification e-mail not sent.")
            st.rerun()


def maybe_confirm_pending_email():
    """If an assignment staged a pending e-mail, pop the 'Send email?' dialog.
    Call once per run from the main app body so it works regardless of which
    panel is open. No-op when nothing is staged."""
    if ss.get('_pending_email_confirm'):
        _email_confirm_dialog()


def render_approver_selectbox(form_key: str):
    """Render a required 'assign approver' selectbox inside a contribution
    form. Returns the selected superuser's User ID, or None if unselected /
    no superusers exist. The caller validates non-None before saving."""
    supers = _list_superusers()
    if not supers:
        st.warning("No superusers are configured to review submissions.")
        return None
    PLACEHOLDER = "— Select an approver —"
    labels = [PLACEHOLDER] + [f"{s['full_name']} ({s['user_id']})" for s in supers]
    choice = st.selectbox(
        "Assign to approver (required)",
        labels,
        key=f"{form_key}_approver",
    )
    if choice == PLACEHOLDER:
        return None
    return supers[labels.index(choice) - 1]['user_id']


# --- Main-area panel switching -------------------------------------------
# The main area shows EITHER the default Q&A/chat screen OR exactly one panel
# (HITL review, Manage Knowledge, Auto Q&A, Gap Finder, Quiz). Opening a panel
# hides the chat input, New button, Q&A history and any other panel; each panel
# has a Close button that calls close_all_main_panels() to restore the Q&A view.
_MAIN_PANEL_FLAGS = (
    "_hitl_selected_id", "_kb_manager_open",
    "_selected_auto_qa_q_id", "_selected_gap_finder_q_id", "_quiz_active",
)


def active_main_panel():
    """Return the session-state key of the open main-area panel, or None when
    the default Q&A/chat screen should be shown."""
    for flag in _MAIN_PANEL_FLAGS:
        if ss.get(flag):
            return flag
    return None


def close_all_main_panels():
    """Clear every main-area panel so the Q&A/chat screen is restored. Called
    when opening a panel (mutual exclusivity) and by each panel's Close button."""
    ss._hitl_selected_id = None
    ss._kb_manager_open = False
    ss._selected_auto_qa_q_id = None
    ss._selected_gap_finder_q_id = None
    ss._quiz_active = False
    ss._quiz_current = None
    ss._quiz_last_result = None


def show_hitl_review_sidebar():
    """Sidebar HITL queue: clickable list. Clicking a row sets the selected
    gap_id in session state; show_hitl_review_main() then renders the full
    review form in the main area. Superuser-only."""
    if ss.get('role') != 'superuser':
        return

    from core.gap_detection import list_pending_reviews

    try:
        # Only items the submitter assigned to THIS superuser appear here.
        pending = list_pending_reviews(GAPS_DB_PATH, assigned_to=ss.get('user_name'))
    except Exception as e:
        log_message('error', f"HITL sidebar list_pending failed: {e}")
        return

    label = f"HITL Review ({len(pending)} pending)" if pending else "HITL Review"
    with st.expander(label, expanded=False):
        if not pending:
            st.caption("Nothing to review.")
            return
        selected_id = ss.get('_hitl_selected_id')
        for row in pending:
            gap_id = row['id']
            q = row['question'] or ''
            short = q if len(q) <= 50 else q[:50] + '…'
            btn_label = ("● " + short) if gap_id == selected_id else short
            help_text = f"from {row['user_input_by'] or '?'} · {row['user_input_at']}"
            if st.button(
                btn_label,
                key=f"sb_hitl_select_{gap_id}",
                help=help_text,
                use_container_width=True,
            ):
                close_all_main_panels()
                ss._hitl_selected_id = gap_id
                st.rerun()


def show_hitl_review_main() -> bool:
    """Render the full review form for the currently-selected HITL item in
    the main area. Returns True if a panel was rendered (so caller can
    skip rendering the chat). No-op + returns False if nothing selected or
    user is not a superuser."""
    sel_id = ss.get('_hitl_selected_id')
    if not sel_id or ss.get('role') != 'superuser':
        return False

    from core.gap_detection import (
        commit_approved_to_validated,
        get_gap,
        record_review_decision,
    )

    row = get_gap(GAPS_DB_PATH, sel_id)
    if not row:
        ss._hitl_selected_id = None
        return False

    # Defensive CSS so the edit/comment inputs are readable on any theme.
    st.markdown(
        """
        <style>
        div[data-testid="stTextArea"] textarea,
        div[data-testid="stTextInput"] input { color: #1a1a2e !important; background-color: #ffffff !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    text_color = ss.get('__text_color', '#f5f5f5')
    muted_color = '#9aa0a6'

    header_col, close_col = st.columns([6, 1])
    with header_col:
        st.markdown(
            f'<h3 style="color:{text_color};margin-bottom:0.25rem;">HITL Review · #{sel_id}</h3>',
            unsafe_allow_html=True,
        )
    with close_col:
        if st.button("Close", key=f"hitl_main_close_{sel_id}", use_container_width=True):
            ss._hitl_selected_id = None
            st.rerun()

    st.markdown(
        f'<p style="color:{text_color};margin:0.25rem 0;">'
        f'<strong>Question asked:</strong> {row["question"]}</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="color:{muted_color};font-size:0.85em;margin:0.25rem 0;">'
        f'Submitted by `{row["user_input_by"] or "?"}` on {row["user_input_at"]} · '
        f'model confidence: {row.get("confidence")} · '
        f'text docs at query time: {row.get("num_text_docs")}</p>',
        unsafe_allow_html=True,
    )
    if row.get('missing_info'):
        st.info(f"**Identified gap:** {row['missing_info']}")

    _is_gap_row = bool(row.get("is_gap"))
    _ans_label = (
        "Original LLM answer (rejected as insufficient)"
        if _is_gap_row
        else "Original LLM answer (user added context anyway)"
    )
    with st.expander(_ans_label, expanded=False):
        st.code((row.get('answer') or '')[:3000], language=None)

    st.markdown("**User contribution** (edit if you want to refine before approving):")
    edited = st.text_area(
        "Knowledge",
        value=row['user_input'] or '',
        height=160,
        key=f"hitl_main_edit_{sel_id}",
        label_visibility="collapsed",
    )
    comment = st.text_input(
        "Reviewer comment (optional)",
        key=f"hitl_main_comment_{sel_id}",
        placeholder="Why approve / reject? Logged for audit.",
    )

    reviewer_name = ss.get('full_name') or ss.get('user_name') or 'unknown'
    col_a, col_r, _ = st.columns([1, 1, 4])
    with col_a:
        if st.button("✓ Approve & commit to KB", type="primary", key=f"hitl_main_approve_{sel_id}", use_container_width=True):
            original = (row['user_input'] or '').strip()
            final_edited = edited.strip() if edited.strip() != original else None
            try:
                ok = record_review_decision(
                    GAPS_DB_PATH, sel_id, "approved",
                    reviewer_name=reviewer_name,
                    edited_text=final_edited,
                    comment=comment.strip() or None,
                )
                if not ok:
                    st.warning("Row missing.")
                else:
                    embeddings = ss.get('embeddings')
                    main_vdb = ss.get('vectorstore_obj')
                    chroma_client = getattr(main_vdb, '_client', None) if main_vdb else None
                    chroma_client_settings = getattr(main_vdb, '_client_settings', None) if main_vdb else None
                    if embeddings is None:
                        st.warning("Approved (KB commit deferred — embeddings not ready)")
                    else:
                        doc_id = commit_approved_to_validated(
                            chroma_dir="Chroma_VectorStore",
                            embeddings=embeddings,
                            db_path=GAPS_DB_PATH,
                            gap_id=sel_id,
                            chroma_client=chroma_client,
                            chroma_client_settings=chroma_client_settings,
                        )
                        st.toast(f"Approved #{sel_id} → {doc_id}")
                    ss._hitl_selected_id = None
                    st.rerun()
            except Exception as e:
                log_message('error', f"HITL approve failed: {e}")
                st.error(f"Approve failed: {e}")
    with col_r:
        if st.button("✗ Reject", key=f"hitl_main_reject_{sel_id}", use_container_width=True):
            try:
                record_review_decision(
                    GAPS_DB_PATH, sel_id, "rejected",
                    reviewer_name=reviewer_name,
                    comment=comment.strip() or None,
                )
                st.toast(f"Rejected #{sel_id}")
                ss._hitl_selected_id = None
                st.rerun()
            except Exception as e:
                log_message('error', f"HITL reject failed: {e}")
                st.error(f"Reject failed: {e}")

    st.markdown("---")
    return True


def show_kb_manager_sidebar():
    """Sidebar entry point for the injected-knowledge manager. Superuser-only.
    Clicking 'Open' sets a session flag; show_kb_manager_main() renders the
    list + search + edit/delete UI in the main area."""
    if ss.get('role') != 'superuser':
        return

    vstore = ss.get('validated_vdb')
    try:
        count = vstore._collection.count() if vstore is not None else 0
    except Exception:
        count = 0

    label = f"Manage Knowledge ({count})" if count else "Manage Knowledge"
    with st.expander(label, expanded=False):
        st.caption("Edit or delete expert-approved knowledge already in the KB.")
        if st.button("Open knowledge manager", key="kb_mgr_open", use_container_width=True):
            close_all_main_panels()
            ss._kb_manager_open = True
            st.rerun()


def show_kb_manager_main() -> bool:
    """Main-area panel listing every injected (validated) knowledge entry with
    a search bar; each entry is editable (re-embeds on save) and deletable.
    Superuser-only. Returns True if a panel was rendered."""
    if not ss.get('_kb_manager_open') or ss.get('role') != 'superuser':
        return False

    from core.gap_detection import (
        list_validated_entries,
        update_validated_entry,
        delete_validated_entry,
    )

    vstore = ss.get('validated_vdb')
    if vstore is None:
        st.warning("Validated knowledge collection is not available.")
        return True

    # White text boxes with dark text. Buttons are intentionally left to the
    # app's natural style (apply_dynamic_colors) so Save/Delete/Close match the
    # white, bordered chat-history buttons. The Save/Delete buttons render
    # because app.py no longer hides every form-submit button off-screen.
    st.markdown(
        """
        <style>
        div[data-testid="stTextArea"] textarea,
        div[data-testid="stTextInput"] input {
            color: #1a1a2e !important;
            background-color: #ffffff !important;
            -webkit-text-fill-color: #1a1a2e !important;
        }
        /* Field labels ("Question" / "Answer") inherit the light theme text
           color and render white-on-light; force them dark so they're visible
           inside the View / edit expander. */
        div[data-testid="stTextArea"] label,
        div[data-testid="stTextArea"] label p,
        div[data-testid="stTextInput"] label,
        div[data-testid="stTextInput"] label p,
        div[data-testid="stWidgetLabel"],
        div[data-testid="stWidgetLabel"] p {
            color: #1a1a2e !important;
            -webkit-text-fill-color: #1a1a2e !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    text_color = ss.get('__text_color', '#f5f5f5')
    muted_color = '#9aa0a6'

    header_col, close_col = st.columns([6, 1])
    with header_col:
        st.markdown(
            f'<h3 style="color:{text_color};margin-bottom:0.25rem;">Manage Injected Knowledge</h3>',
            unsafe_allow_html=True,
        )
    with close_col:
        if st.button("Close", key="kb_mgr_close", use_container_width=True):
            ss._kb_manager_open = False
            st.rerun()

    search = st.text_input(
        "Search knowledge",
        key="kb_mgr_search",
        placeholder="Filter by words in the question or answer.",
    )

    try:
        entries = list_validated_entries(vstore, search=search or None)
    except Exception as e:
        log_message('error', f"KB manager list failed: {e}")
        st.error(f"Could not load knowledge entries: {e}")
        return True

    if not entries:
        st.markdown(
            f'<p style="color:{muted_color};">'
            + ("No entries match your search." if search else "No injected knowledge yet.")
            + '</p>',
            unsafe_allow_html=True,
        )
        st.markdown("---")
        return True

    # --- Pagination -------------------------------------------------------
    PAGE_SIZE = 3
    total = len(entries)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)

    # Reset to page 1 whenever the search filter changes, so we never land on a
    # now-empty page.
    if ss.get('_kb_mgr_last_search') != (search or ''):
        ss._kb_mgr_page = 0
        ss._kb_mgr_last_search = search or ''
    page = max(0, min(ss.get('_kb_mgr_page', 0), total_pages - 1))
    ss._kb_mgr_page = page

    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    page_entries = entries[start:end]

    st.markdown(
        f'<p style="color:{muted_color};font-size:0.85em;">'
        f'Showing {start + 1}–{end} of {total} entr'
        f'{"y" if total == 1 else "ies"} · page {page + 1} of {total_pages}.</p>',
        unsafe_allow_html=True,
    )

    for e in page_entries:
        doc_id = e['id']
        meta = e['metadata']
        title = e['question'] or '(no question)'
        title_short = title if len(title) <= 55 else title[:55] + '…'
        contributor = meta.get('original_contributor') or '?'
        reviewer = meta.get('reviewer') or '?'

        # Each entry is its own form so Save/Delete submit independently. The
        # question title sits on an always-visible row; the editable fields AND
        # the Save/Delete buttons live inside the View / edit expander.
        with st.form(key=f"kb_mgr_form_{doc_id}", clear_on_submit=False):
            st.markdown(
                f'<p style="color:{text_color};margin:0.45rem 0;font-weight:600;">'
                f'{title_short}</p>',
                unsafe_allow_html=True,
            )

            with st.expander("View / edit", expanded=False):
                st.markdown(
                    f'<p style="color:{muted_color};font-size:0.8em;margin:0;">'
                    f'id `{doc_id}` · contributed by {contributor} · approved by {reviewer}</p>',
                    unsafe_allow_html=True,
                )
                q_edit = st.text_input(
                    "Question", value=e['question'], key=f"kb_mgr_q_{doc_id}",
                )
                a_edit = st.text_area(
                    "Answer", value=e['answer'], height=160, key=f"kb_mgr_a_{doc_id}",
                )
                save_col, del_col = st.columns(2)
                with save_col:
                    save = st.form_submit_button("Save", type="primary", use_container_width=True)
                with del_col:
                    delete = st.form_submit_button("Delete", use_container_width=True)

            if save:
                if not a_edit.strip():
                    st.warning("Answer cannot be empty.")
                else:
                    try:
                        update_validated_entry(
                            vstore,
                            doc_id=doc_id,
                            new_answer=a_edit.strip(),
                            new_question=q_edit.strip() or None,
                            db_path=GAPS_DB_PATH,
                        )
                        st.toast(f"Updated {doc_id}")
                        st.rerun()
                    except Exception as ex:
                        log_message('error', f"KB manager update failed: {ex}")
                        st.error(f"Update failed: {ex}")
            if delete:
                try:
                    delete_validated_entry(vstore, doc_id=doc_id, db_path=GAPS_DB_PATH)
                    st.toast(f"Deleted {doc_id}")
                    st.rerun()
                except Exception as ex:
                    log_message('error', f"KB manager delete failed: {ex}")
                    st.error(f"Delete failed: {ex}")

    # Pagination controls at the bottom (below the entry list).
    if total_pages > 1:
        prev_col, _spacer, next_col = st.columns([1, 2, 1])
        with prev_col:
            if st.button("◀ Prev", key="kb_mgr_prev_bot", disabled=(page <= 0),
                         use_container_width=True):
                ss._kb_mgr_page = page - 1
                st.rerun()
        with next_col:
            if st.button("Next ▶", key="kb_mgr_next_bot", disabled=(page >= total_pages - 1),
                         use_container_width=True):
                ss._kb_mgr_page = page + 1
                st.rerun()

    st.markdown("---")
    return True


def _inject_sidebar_input_css():
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] div[data-testid="stTextInput"] input,
        [data-testid="stSidebar"] div[data-testid="stTextArea"] textarea {
            color: #1a1a2e !important;
            background-color: #ffffff !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _generate_and_answer_synth_q(*, purpose: str, sel_state_key: str, topic: str):
    """Generate ONE synthetic question for `purpose`, compute + persist its
    answer, open it as the active main panel, and rerun. Shared by the sidebar
    'Generate question' button and each panel's 'Next' button so both paths
    behave identically. Reads client/model/vdb/embeddings from session state."""
    from core.question_generation import (
        PURPOSE_DEMO,
        answer_synthetic_question,
        answer_with_source,
        generate_one_question_for_topic,
        save_answer_and_record_gap,
        save_question_answer,
    )
    from utils.bida_prompt_utils import content_summary, system_prompt

    client = ss.get('qa_model')
    model = ss.get('__qa_model_name')
    vdb = ss.get('vectorstore_obj')
    embeddings = ss.get('embeddings')
    if not all([client, model, vdb, embeddings]):
        st.error("App not initialized — open the main chat once first.")
        return

    with st.spinner("Generating question…"):
        try:
            qresult = generate_one_question_for_topic(
                client=client, model=model, vdb=vdb,
                db_path=GAPS_DB_PATH,
                topic=(topic or "").strip(),
                purpose=purpose,
            )
        except Exception as e:
            log_message('error', f"single question gen failed ({purpose}): {e}")
            st.error(f"Generation failed: {e}")
            qresult = None

    if qresult and not qresult["in_scope"]:
        st.markdown(
            f'<div style="background-color:#f59e0b;color:#1a1a1a;'
            f'padding:0.5rem 0.9rem;border-radius:6px;margin:0.5rem 0;">'
            f'⚠️ {qresult["reason"]}'
            f'</div>',
            unsafe_allow_html=True,
        )
    elif qresult and qresult.get("question_id"):
        qid = qresult["question_id"]
        with st.spinner("Answering…"):
            try:
                import json as _json
                if purpose == PURPOSE_DEMO and qresult.get("source_chunk_content"):
                    # Auto Q&A: answer DIRECTLY from the source chunk.
                    ar = answer_with_source(
                        client=client, model=model,
                        question_text=qresult["question_text"],
                        source_text=qresult["source_chunk_content"],
                        system_prompt_template=system_prompt,
                        content_summary=content_summary,
                        max_tokens=ss.get('__max_tokens', 2000),
                        temperature=ss.get('__temperature', 0.2),
                    )
                    # Persist the source chunk so the panel can render
                    # it under the answer (matching the chat UX).
                    src_docs_json = _json.dumps([{
                        "page_content": qresult["source_chunk_content"],
                        "metadata": qresult.get("source_chunk_metadata") or {},
                    }])
                    save_question_answer(
                        GAPS_DB_PATH, qid,
                        ar['answer'], ar['confidence'], ar['missing_info'],
                        num_text_docs=ar['num_text_docs'],
                        num_image_docs=ar['num_image_docs'],
                        source_docs_json=src_docs_json,
                    )
                else:
                    # Gap Finder (or topic-targeted): full retrieval.
                    ar = answer_synthetic_question(
                        client=client, model=model,
                        embeddings=embeddings, vdb=vdb,
                        validated_vdb=ss.get('validated_vdb'),
                        bm25_index=ss.get('bm25_index'),
                        bm25_corpus_docs=ss.get('bm25_corpus_docs'),
                        reranker_model=ss.get('reranker_model'),
                        system_prompt_template=system_prompt,
                        content_summary=content_summary,
                        question_text=qresult["question_text"],
                        max_tokens=ss.get('__max_tokens', 2000),
                        temperature=ss.get('__temperature', 0.2),
                    )
                    src_docs_json = _json.dumps(ar.get('source_docs') or [])
                    save_answer_and_record_gap(
                        GAPS_DB_PATH, qid,
                        ar['answer'], ar['confidence'], ar['missing_info'],
                        num_text_docs=ar['num_text_docs'],
                        num_image_docs=ar['num_image_docs'],
                        user_name=ss.get('full_name') or ss.get('user_name'),
                        model=model,
                        source_docs_json=src_docs_json,
                    )
            except Exception as e:
                log_message('error', f"auto-answer failed ({purpose}): {e}")
                st.error(f"Answer step failed: {e}")
        close_all_main_panels()
        ss[sel_state_key] = qid
        st.rerun()
    elif qresult and qresult.get("reason"):
        st.warning(qresult["reason"])


def _synth_qa_generate_and_answer(*, purpose: str, sel_state_key: str,
                                  topic_key: str, gen_button_key: str,
                                  expander_label: str, placeholder: str, help_text: str):
    """Shared sidebar UI for both Auto Q&A and Gap Finder. Differences are
    only in the prompt purpose, session-state keys, and copy."""
    from core.question_generation import (
        PURPOSE_DEMO,
        answer_synthetic_question,
        answer_with_source,
        generate_one_question_for_topic,
        save_answer_and_record_gap,
        save_question_answer,
    )
    from utils.bida_prompt_utils import content_summary, system_prompt

    with st.expander(expander_label, expanded=False):
        client = ss.get('qa_model')
        model = ss.get('__qa_model_name')
        vdb = ss.get('vectorstore_obj')
        embeddings = ss.get('embeddings')
        if not all([client, model, vdb, embeddings]):
            st.caption("App not initialized — open the main chat once first.")
            return

        topic = st.text_input(
            "Topic (optional)",
            placeholder=placeholder,
            key=topic_key,
            help=help_text,
        )

        if st.button("Generate question", key=gen_button_key, use_container_width=True):
            _generate_and_answer_synth_q(
                purpose=purpose, sel_state_key=sel_state_key, topic=topic,
            )


def show_synthetic_questions_sidebar():
    """Auto Q&A — generate a question whose answer is grounded in the docs.
    No gap-finding focus; suppresses gap-contribution UI in the main panel."""
    if ss.get('role') != 'superuser':
        return
    from core.question_generation import PURPOSE_DEMO
    _inject_sidebar_input_css()
    _synth_qa_generate_and_answer(
        purpose=PURPOSE_DEMO,
        sel_state_key='_selected_auto_qa_q_id',
        topic_key='synq_topic',
        gen_button_key='synq_generate',
        expander_label="Auto Q&A",
        placeholder="e.g., workflow stages — leave blank for auto-pick",
        help_text=(
            "Generates a question that the documents CAN answer. Showcases "
            "what's already in the knowledge base. Leave the topic blank to "
            "let the system pick from random chunks."
        ),
    )


def show_gap_finder_sidebar():
    """Knowledge Gap Finder — generate a question designed to probe the LIMITS
    of the docs (edge cases / what-ifs / unspecified details). Surfaces gaps
    so they can be filled via the contribution form in the main panel."""
    if ss.get('role') != 'superuser':
        return
    from core.question_generation import PURPOSE_GAP_FINDER
    _inject_sidebar_input_css()
    _synth_qa_generate_and_answer(
        purpose=PURPOSE_GAP_FINDER,
        sel_state_key='_selected_gap_finder_q_id',
        topic_key='gapq_topic',
        gen_button_key='gapq_generate',
        expander_label="Knowledge Gap Finder",
        placeholder="e.g., dispute resolution edges — leave blank for auto-pick",
        help_text=(
            "Generates a question designed to find WEAKNESSES in the documents — "
            "edge cases, missing details, what-ifs. If the answer comes back "
            "low-confidence, you get an inline form to contribute the missing "
            "knowledge for HITL review."
        ),
    )


def _render_text_sources_html(source_docs: list) -> str:
    """Foldable <details> block listing text source documents. All text is
    rendered black on the BIDA expander color (matches the question/answer
    cards) via class-based CSS overrides defined in styles/styles.py.
    Body uses convert_markdown_to_html so embedded tables/lists/bold render
    properly instead of showing raw HTML tags."""
    if not source_docs:
        return ""
    import html as _htmllib
    from utils.chat_utils import convert_markdown_to_html
    panel_bg = ss.get('__expander_color', '#DFE2E2')
    summary_style = (
        f"background-color:{panel_bg};padding:0.4rem 0.75rem;"
        "border-radius:6px;cursor:pointer;font-weight:600;list-style:none;"
        "display:inline-block;margin:0.5rem 0;"
    )
    html = [
        f'<details class="synth-source-pre" style="margin:0.5rem 0;">'
        f'<summary class="synth-source-header" style="{summary_style}">▸ Text Sources ({len(source_docs)})</summary>'
        f'<div class="synth-source-pre" style="padding:0.5rem 0.75rem;background-color:{panel_bg};'
        f'border-radius:6px;margin-top:0.25rem;">'
    ]
    for i, doc in enumerate(source_docs, 1):
        page_content = (doc.get('page_content') or '') if isinstance(doc, dict) else ''
        metadata = (doc.get('metadata') or {}) if isinstance(doc, dict) else {}
        # Pick the best label for the source:
        # - HITL-validated entries: "Information added by <contributor>"
        # - Document chunks: the File metadata field
        # - Anything else: generic "Information added by user"
        if metadata.get('source') == 'hitl_validated':
            contributor = metadata.get('original_contributor') or 'user'
            source_doc_name = f"Information added by {contributor}"
        else:
            source_doc_name = metadata.get('File') or 'Information added by user'
        html.append(
            f'<p style="font-size:15px;margin:0.5rem 0 0.25rem 0;">'
            f'<span style="font-weight:700;">'
            f'{i}. {_htmllib.escape(str(source_doc_name))}</span></p>'
        )
        context_parts = []
        for field in ("File", "Section", "Subsection", "Subsubsection", "Subsubsubsection"):
            val = metadata.get(field, "")
            if val and str(val).strip():
                context_parts.append(str(val).strip())
        if context_parts:
            ctx_str = _htmllib.escape(", ".join(context_parts))
            html.append(
                f'<p style="font-size:12px;margin:0;">'
                f'<span style="font-weight:600;">Context:</span> {ctx_str}</p>'
            )
        source_text = page_content.strip()
        if source_text.startswith("Context:") and context_parts:
            last_meta = context_parts[-1]
            if last_meta in source_text:
                pos = source_text.find(last_meta) + len(last_meta)
                source_text = source_text[pos:].lstrip(", ").strip()
            else:
                source_text = source_text[8:].strip()
        source_text = source_text.replace('\\"', '"').replace("\\'", "'").replace('\\$', '$')
        # Render as styled <pre> with inline color — markdown conversion
        # output gets faded by inherited theme CSS that we can't reach with
        # a <style> tag (Streamlit strips those from user HTML).
        try:
            rendered = convert_markdown_to_html(source_text, font_size="14px")
        except Exception:
            rendered = _htmllib.escape(source_text)
        html.append(rendered)
    html.append("</div></details>")
    return "".join(html)


def _render_synth_qa_panel(*, sel_state_key: str, show_gap_ui: bool, header_label: str) -> bool:
    """Shared main-area renderer for both Auto Q&A and Gap Finder panels.
    `show_gap_ui` controls whether the amber gap banner + contribution form
    appears when the answer was flagged. Returns True if a panel rendered."""
    sel_id = ss.get(sel_state_key)
    if not sel_id or ss.get('role') != 'superuser':
        return False

    from core.gap_detection import record_user_input
    from core.question_generation import (
        answer_synthetic_question,
        get_synthetic_question,
        save_answer_and_record_gap,
    )
    from utils.bida_prompt_utils import content_summary, system_prompt

    row = get_synthetic_question(GAPS_DB_PATH, sel_id)
    if not row:
        ss[sel_state_key] = None
        return False

    # Match the BIDA sidebar expander color so the panel feels native;
    # text is forced black for guaranteed contrast on that light surface.
    panel_bg = ss.get('__expander_color', '#DFE2E2')
    text_color = "#000000"
    muted_color = "#4b5563"

    # Map each panel to its sidebar topic widget + generation purpose so the
    # "Next" button can generate a fresh question of the same kind (respecting
    # any topic the user typed in the sidebar).
    from core.question_generation import PURPOSE_DEMO, PURPOSE_GAP_FINDER
    _panel_meta = {
        '_selected_auto_qa_q_id': ('synq_topic', PURPOSE_DEMO),
        '_selected_gap_finder_q_id': ('gapq_topic', PURPOSE_GAP_FINDER),
    }

    # Title header only — Next / Close buttons are rendered at the BOTTOM of the panel.
    st.markdown(
        f'<div class="synth-panel-text" style="background-color:{panel_bg};'
        f'padding:0.5rem 0.75rem;border-radius:6px 6px 0 0;margin-bottom:0;">'
        f'<h3 style="margin:0;">{header_label}</h3>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div class="synth-panel-text" style="background-color:{panel_bg};'
        f'padding:0.5rem 0.75rem;border-radius:0 0 6px 6px;margin:0 0 0.5rem 0;">'
        f'<strong>[{row["question_type"]}]</strong> {row["text"]}'
        f'</div>',
        unsafe_allow_html=True,
    )


    # Inject the chat CSS + bot template so the synthetic answer matches the
    # main chat styling (avatar + themed bubble), not a bare st.markdown blob.
    st.write(css_old, unsafe_allow_html=True)

    cached_answer = row.get('answer_text')
    if cached_answer:
        st.markdown(
            f'<div class="synth-panel-text" style="background-color:{panel_bg};'
            f'padding:0.75rem 1rem;border-radius:6px;margin:0.5rem 0;'
            f'border-left:4px solid #8B1F2B;line-height:1.5;">'
            f'{cached_answer}</div>',
            unsafe_allow_html=True,
        )
        # Render source docs as a foldable <details> block (matches main chat).
        import json as _json
        try:
            cached_sources = _json.loads(row.get('answer_source_docs_json') or '[]')
        except Exception:
            cached_sources = []
        sources_html = _render_text_sources_html(cached_sources)
        if sources_html:
            st.markdown(sources_html, unsafe_allow_html=True)
        elif row.get('answer_num_text_docs') is not None:
            # Fallback for rows answered before source persistence existed.
            st.markdown(
                f'<p style="color:{muted_color};font-size:0.85em;margin:0.25rem 0;">'
                f'text sources: {row["answer_num_text_docs"]}</p>',
                unsafe_allow_html=True,
            )
        n_image = row.get('answer_num_image_docs')
        if n_image:
            st.markdown(
                f'<p style="color:{muted_color};font-size:0.85em;margin:0.25rem 0;">'
                f'related images: {n_image}</p>',
                unsafe_allow_html=True,
            )
    if not cached_answer:
        client = ss.get('qa_model')
        model = ss.get('__qa_model_name')
        vdb = ss.get('vectorstore_obj')
        embeddings = ss.get('embeddings')
        if not all([client, model, vdb, embeddings]):
            st.error("App not ready (missing qa_model / vdb / embeddings).")
            st.markdown("---")
            return True

        with st.spinner("Computing answer…"):
            try:
                result = answer_synthetic_question(
                    client=client, model=model,
                    embeddings=embeddings, vdb=vdb,
                    validated_vdb=ss.get('validated_vdb'),
                    bm25_index=ss.get('bm25_index'),
                    bm25_corpus_docs=ss.get('bm25_corpus_docs'),
                    reranker_model=ss.get('reranker_model'),
                    system_prompt_template=system_prompt,
                    content_summary=content_summary,
                    question_text=row['text'],
                    max_tokens=ss.get('__max_tokens', 2000),
                    temperature=ss.get('__temperature', 0.2),
                )
                # Cache answer + auto-record gap (if classified) and link.
                linked_gap_id = save_answer_and_record_gap(
                    GAPS_DB_PATH, sel_id,
                    result['answer'],
                    result['confidence'],
                    result['missing_info'],
                    num_text_docs=result['num_text_docs'],
                    num_image_docs=result['num_image_docs'],
                    user_name=ss.get('full_name') or ss.get('user_name'),
                    model=model,
                )
                st.markdown(
                    f'<div class="synth-panel-text" style="background-color:{panel_bg};'
                    f'padding:0.75rem 1rem;border-radius:6px;margin:0.5rem 0;'
                    f'border-left:4px solid #8B1F2B;line-height:1.5;">'
                    f'{result["answer"]}</div>',
                    unsafe_allow_html=True,
                )
                # Re-fetch the row so we render the just-persisted sources
                # the same way as the cached path. Keeps both branches consistent.
                row = get_synthetic_question(GAPS_DB_PATH, sel_id) or row
                import json as _json2
                try:
                    fresh_sources = _json2.loads(row.get('answer_source_docs_json') or '[]')
                except Exception:
                    fresh_sources = []
                fresh_html = _render_text_sources_html(fresh_sources)
                if fresh_html:
                    st.markdown(fresh_html, unsafe_allow_html=True)
                if result['num_image_docs'] > 0:
                    st.markdown(
                        f'<p style="color:{muted_color};font-size:0.85em;margin:0.25rem 0;">'
                        f'related images: {result["num_image_docs"]}</p>',
                        unsafe_allow_html=True,
                    )
                # Refresh `row` so the gap-input form below sees the new gap_id.
                row = get_synthetic_question(GAPS_DB_PATH, sel_id) or row
            except Exception as e:
                log_message('error', f"answer_synthetic_question failed: {e}")
                st.error(f"Failed: {e}")

    # Gap-input form — only rendered when this panel is configured to surface
    # gaps (Knowledge Gap Finder). Auto-Q&A suppresses this UI even if the
    # answer happens to be classified as a gap.
    gap_id_link = row.get('gap_id')
    if show_gap_ui and gap_id_link:
        st.markdown(
            '<div style="background-color:#f59e0b;color:#1a1a1a;'
            'padding:0.5rem 0.9rem;border-radius:6px;margin:0.5rem 0;">'
            '⚠️ <strong>Flagged as a knowledge gap.</strong> '
            'If you know the answer, share it below for HITL review.'
            '</div>',
            unsafe_allow_html=True,
        )
        _gap_form_key = f"{sel_state_key}_gap_input_{sel_id}"
        with st.form(key=_gap_form_key, clear_on_submit=True):
            knowledge = st.text_area(
                "Your knowledge",
                height=120,
                placeholder="Do you have something to add?",
                key=f"{sel_state_key}_gap_text_{sel_id}",
            )
            approver_id = render_approver_selectbox(_gap_form_key)
            submitted = st.form_submit_button("Submit for review")
            if submitted:
                if not knowledge.strip():
                    st.warning("Please enter some text before submitting.")
                elif not approver_id:
                    st.warning("Please select a superuser to approve this submission.")
                else:
                    try:
                        ok = record_user_input(
                            GAPS_DB_PATH,
                            gap_id_link,
                            knowledge.strip(),
                            user_name=ss.get('full_name') or ss.get('user_name'),
                            assigned_to=approver_id,
                        )
                        if ok:
                            st.toast(f"Saved for review (gap #{gap_id_link})")
                            notify_assignee_via_outlook(
                                assignee_user_id=approver_id,
                                gap_id=gap_id_link,
                                submitter_name=ss.get('full_name') or ss.get('user_name'),
                                question=row.get('text', ''),
                                contribution=knowledge.strip(),
                            )
                            st.rerun()
                        else:
                            st.warning("Could not find linked gap entry.")
                    except Exception as e:
                        log_message('error', f"synth gap input save failed: {e}")
                        st.error(f"Could not save: {e}")

    # Next / Close buttons at the BOTTOM of the panel.
    _bot_next_col, _bot_close_col = st.columns(2)
    with _bot_next_col:
        if st.button("Next", key=f"{sel_state_key}_next_bot_{sel_id}", use_container_width=True):
            _topic_key, _purpose = _panel_meta[sel_state_key]
            _generate_and_answer_synth_q(
                purpose=_purpose, sel_state_key=sel_state_key,
                topic=ss.get(_topic_key, ""),
            )
    with _bot_close_col:
        if st.button("Close", key=f"{sel_state_key}_close_bot_{sel_id}", use_container_width=True):
            ss[sel_state_key] = None
            st.rerun()

    st.markdown("---")
    return True


def show_synthetic_question_main() -> bool:
    """Auto Q&A panel — gap UI suppressed."""
    return _render_synth_qa_panel(
        sel_state_key='_selected_auto_qa_q_id',
        show_gap_ui=False,
        header_label="Auto Q&A",
    )


def show_gap_finder_main() -> bool:
    """Knowledge Gap Finder panel — surfaces gaps for HITL contribution."""
    return _render_synth_qa_panel(
        sel_state_key='_selected_gap_finder_q_id',
        show_gap_ui=True,
        header_label="Knowledge Gap Finder",
    )


def get_current_chat_display_name():
    """Get the display name for the current active chat from session state."""
    try:
        if ss._qa_filename and len(ss.qa_history.get('historical_prompts', [])) > 0:
            # Extract display name from filename (remove .json and username)
            # Format: question_timestamp_username.json
            filename = ss._qa_filename
            if filename.endswith('.json'):
                filename = filename[:-5]  # Remove .json
            parts = filename.rsplit('_', 1)  # Split from right to get [question_timestamp, username]
            if len(parts) >= 1:
                # Return question_timestamp (without username)
                return parts[0]
    except Exception as e:
        log_message("error", f"Error getting current chat display name: {e}")
    return None

def show_chat_history():
    # Initialize rename state if not exists
    if 'rename_mode' not in ss:
        ss.rename_mode = None

    # Get current active chat name (for highlighting and deduplication)
    current_chat_name = get_current_chat_display_name()

    if ss.role != "superuser":
        # Regular user - show only their own history
        saved_history = get_user_chat_names_in_directory(ss._QA_DIRECTORY, ss.user_name, False)
        # Ensure saved_history is a list (not None)
        saved_history = saved_history if saved_history else []

        # Check if we have an active chat that should be shown
        has_active_chat = current_chat_name and len(ss.qa_history.get('historical_prompts', [])) > 0
        has_saved_history = len(saved_history) > 0

        # Show expander if there's either an active chat or saved history
        if has_active_chat or has_saved_history:
            # Keep the expander open while a download is staged, otherwise
            # the Streamlit 1.35 expander resets to closed on rerun (no key
            # support) and the download_button gets hidden.
            expand_dl_regular = bool(getattr(ss, 'zip_requested_regular', False))
            try:
                with st.expander("Download History", expanded=expand_dl_regular):
                    # Format selection
                    download_format_regular = st.radio(
                        "Format",
                        options=["JSON", "HTML (with embedded images)"],
                        key="download_format_radio_regular",
                        horizontal=True
                    )

                    # Option to include only today's chats
                    only_today_regular = st.checkbox("Only today's chats", value=False, key="only_today_checkbox_regular")

                    # Note: button click already triggers a rerun; an extra
                    # st.rerun() here would compound the expander reset.
                    if st.button('Download', key="download_btn_regular", use_container_width=True):
                        ss.zip_requested_regular = True
                        ss.zip_only_today_regular = only_today_regular
                        ss.zip_format_regular = download_format_regular

                    if getattr(ss, 'zip_requested_regular', False) and saved_history:
                        from utils.sys_utils import create_markdown_zip, zip_files_multi_user
                        from utils.date_time_utils import get_date_time_stamp

                        zip_format = getattr(ss, 'zip_format_regular', 'JSON')
                        only_today = getattr(ss, 'zip_only_today_regular', False)

                        # Create a dict format for the user's history (to match the multi-user function)
                        user_history_dict = {ss.user_name: saved_history}

                        if zip_format == "JSON":
                            zip_name = ss.user_name + "_chat_history_" + get_date_time_stamp() + ".zip"
                            zip_buffer, zip_name = zip_files_multi_user(
                                ss._QA_DIRECTORY,
                                user_history_dict,
                                zip_name,
                                selected_user=ss.user_name,
                                only_today=only_today
                            )
                        else:
                            # HTML format with embedded images
                            zip_name = ss.user_name + "_chat_history_" + get_date_time_stamp() + "_html.zip"
                            zip_buffer, zip_name = create_markdown_zip(
                                ss._QA_DIRECTORY,
                                user_history_dict,
                                zip_name,
                                selected_user=ss.user_name,
                                embed_images=True,
                                output_format="html",
                                only_today=only_today
                            )

                        if zip_buffer and zip_name:
                            st.download_button(
                                label="Download zip",
                                data=zip_buffer,
                                file_name=zip_name,
                                mime='application/zip'
                            )
                            ss.zip_requested_regular = False
            except Exception as e:
                ss.zip_requested_regular = False
                st.error(f"Unable to download chat history: {e}")
                log_message("error", f"Error occurred while trying to download history: {e}")

            with st.expander("History", expanded=False):
                # Search filter
                search_text = st.text_input("Search history", key="history_search_regular", placeholder="Type to filter...")

                # Build the list of chats to display
                chats_to_display = []

                # First, add all saved history chats
                for chat_name in saved_history:
                    is_current = (current_chat_name and chat_name == current_chat_name)
                    chats_to_display.append((chat_name, is_current))

                # If active chat is not in saved history, add it at the top
                if has_active_chat:
                    current_in_history = current_chat_name in saved_history
                    if not current_in_history:
                        # Insert current chat at the beginning
                        chats_to_display.insert(0, (current_chat_name, True))

                for chat_name, is_current in chats_to_display:
                    chat_question, datetime_and_user = split_user_chat_name(chat_name)
                    full_chat_name = chat_question + datetime_and_user

                    # Apply search filter
                    if search_text and search_text.lower() not in chat_question.lower():
                        continue

                    # Check if this item is in rename mode
                    rename_key = f"regular_{datetime_and_user}"
                    if ss.rename_mode == rename_key:
                        # Show rename input
                        col_input, col_save, col_cancel = st.columns([4, 1, 1])
                        with col_input:
                            new_name = st.text_input("New name", value=chat_question, key=f"rename_input_{rename_key}", label_visibility="collapsed")
                        with col_save:
                            if st.button("✓", key=f"save_rename_{rename_key}", help="Save"):
                                if rename_history(ss._QA_DIRECTORY, full_chat_name, new_name, ss.user_name):
                                    st.toast("Chat renamed successfully")
                                    ss.rename_mode = None
                                    st.rerun()
                        with col_cancel:
                            if st.button("✕", key=f"cancel_rename_{rename_key}", help="Cancel"):
                                ss.rename_mode = None
                                st.rerun()
                    else:
                        # Normal display - highlight current chat
                        col1, col2, col3 = st.columns([5, 1, 1])
                        with col1:
                            # Show LATEST question from thread (not first) — for multi-turn clarity
                            latest_q = _sidebar_label_for_chat(ss._QA_DIRECTORY, full_chat_name, ss.user_name, chat_question)
                            button_label = extract_without_breaking_words(latest_q, HISTORY_BUTTON_CHAR_LIMIT)
                            if is_current:
                                button_label = "● " + button_label  # Add indicator for current chat
                            if st.button(button_label, key=f"load_{datetime_and_user}", help=latest_q, use_container_width=True):
                                try:
                                    load_history(ss._QA_DIRECTORY, full_chat_name, ss.user_name, ss.__qa_history_enabled)
                                except Exception as e:
                                    st.error(f"Unable to load selected chat history: {e}")
                                    log_message("error", f"Error occurred while trying to load history: {e}")
                        with col2:
                            if st.button("🖉", key=f"rename_{datetime_and_user}", help="Rename this chat"):
                                ss.rename_mode = rename_key
                                st.rerun()
                        with col3:
                            if st.button("🗑", key=f"del_{datetime_and_user}", help="Delete this history"):
                                if delete_history(ss._QA_DIRECTORY, full_chat_name, ss.user_name):
                                    st.toast("History deleted")
                                    st.rerun()

    else:
        # Superuser - show all users' history with filter options
        saved_history_dict = get_user_chat_names_in_directory(ss._QA_DIRECTORY, ss.user_name, True)
        # Ensure saved_history_dict is a dict (not None)
        saved_history_dict = saved_history_dict if saved_history_dict else {}

        # Check if we have an active chat that should be shown
        has_active_chat = current_chat_name and len(ss.qa_history.get('historical_prompts', [])) > 0
        has_saved_history = len(saved_history_dict) > 0

        if has_active_chat or has_saved_history:
            expand_dl_super = bool(getattr(ss, 'zip_requested', False))
            try:
                with st.expander("Download History", expanded=expand_dl_super):
                    # User selection dropdown
                    download_users = list(saved_history_dict.keys()) if saved_history_dict else []
                    download_user_options = ["All Users"] + download_users
                    selected_download_user = st.selectbox(
                        "Select user",
                        options=download_user_options,
                        key="download_user_filter"
                    )

                    # Format selection
                    download_format = st.radio(
                        "Format",
                        options=["JSON", "HTML (with embedded images)"],
                        key="download_format_radio",
                        horizontal=True
                    )

                    # Option to include only today's chats
                    only_today = st.checkbox("Only today's chats", value=False, key="only_today_checkbox")

                    col_json, col_md = st.columns(2)
                    with col_json:
                        # Button click already triggers a rerun; an extra
                        # st.rerun() here would compound the expander reset.
                        if st.button('Download', use_container_width=True):
                            ss.zip_requested = True
                            ss.zip_selected_user = selected_download_user
                            ss.zip_only_today = only_today
                            ss.zip_format = download_format

                    if ss.zip_requested and saved_history_dict:
                        from utils.sys_utils import create_markdown_zip
                        from utils.date_time_utils import get_date_time_stamp

                        zip_format = getattr(ss, 'zip_format', 'JSON')
                        selected_user = getattr(ss, 'zip_selected_user', "All Users")

                        if zip_format == "JSON":
                            zip_buffer, zip_name = download_chat_history(
                                ss._QA_DIRECTORY,
                                ss.user_name,
                                saved_history_dict,
                                only_today=getattr(ss, 'zip_only_today', False),
                                selected_user=selected_user
                            )
                        else:
                            # HTML format with embedded images
                            if selected_user == "All Users":
                                zip_name = "all_users_chat_history_" + get_date_time_stamp() + "_html.zip"
                            else:
                                zip_name = selected_user + "_chat_history_" + get_date_time_stamp() + "_html.zip"

                            zip_buffer, zip_name = create_markdown_zip(
                                ss._QA_DIRECTORY,
                                saved_history_dict,
                                zip_name,
                                selected_user=selected_user,
                                embed_images=True,
                                output_format="html",
                                only_today=getattr(ss, 'zip_only_today', False)
                            )

                        if zip_buffer and zip_name:
                            st.download_button(
                                        label="Download zip",
                                        data=zip_buffer,
                                        file_name=zip_name,
                                        mime='application/zip'
                                    )
                            ss.zip_requested = False  # Reset the flag
            except Exception as e:
                ss.zip_requested = False
                st.error(f"Unable to download chat history: {e}")
                log_message("error", f"Error occurred while trying to download history: {e}")

            with st.expander("History", expanded=False):
                # User filter selectbox
                all_users = list(saved_history_dict.keys())

                # Add current user if they have an active chat but no saved history yet
                if has_active_chat and ss.user_name not in all_users:
                    all_users = [ss.user_name] + all_users

                user_options = ["All Users"] + all_users
                selected_user = st.selectbox(
                    "Filter by user",
                    options=user_options,
                    key="history_user_filter",
                    format_func=lambda u: u if u == "All Users" else _display_name_for(u),
                )

                # Search filter
                search_text = st.text_input("Search history", key="history_search_super", placeholder="Type to filter...")

                # Filter users based on selection
                users_to_show = all_users if selected_user == "All Users" else [selected_user]

                for user in users_to_show:
                    # Build chats to display for this user
                    chats_to_display = []
                    user_saved_chats = saved_history_dict.get(user, [])

                    # First, add all saved chats for this user
                    for chat_name in user_saved_chats:
                        is_current = (current_chat_name and chat_name == current_chat_name and user == ss.user_name)
                        chats_to_display.append((chat_name, is_current))

                    # If this is the current user and active chat is not in saved history, add it at the top
                    if has_active_chat and user == ss.user_name:
                        if current_chat_name not in user_saved_chats:
                            chats_to_display.insert(0, (current_chat_name, True))

                    # Skip user if no chats to display
                    if not chats_to_display:
                        continue

                    history_text_color = ss.get('__text_color', '#F5F5F5')
                    st.markdown(f'<span style="color: {history_text_color}; font-size: 18px;">{_display_name_for(user)}</span>', unsafe_allow_html=True)

                    for chat_name, is_current in chats_to_display:
                        chat_question, datetime_and_user = split_user_chat_name(chat_name)
                        full_chat_name = chat_question + datetime_and_user

                        # Apply search filter
                        if search_text and search_text.lower() not in chat_question.lower():
                            continue

                        # Check if this item is in rename mode
                        rename_key = f"super_{user}_{datetime_and_user}"
                        if ss.rename_mode == rename_key:
                            # Show rename input
                            col_input, col_save, col_cancel = st.columns([4, 1, 1])
                            with col_input:
                                new_name = st.text_input("New name", value=chat_question, key=f"rename_input_{rename_key}", label_visibility="collapsed")
                            with col_save:
                                if st.button("✓", key=f"save_rename_{rename_key}", help="Save"):
                                    if rename_history(ss._QA_DIRECTORY, full_chat_name, new_name, user):
                                        st.toast("Chat renamed successfully")
                                        ss.rename_mode = None
                                        st.rerun()
                            with col_cancel:
                                if st.button("✕", key=f"cancel_rename_{rename_key}", help="Cancel"):
                                    ss.rename_mode = None
                                    st.rerun()
                        else:
                            # Normal display - highlight current chat
                            col1, col2, col3 = st.columns([5, 1, 1])
                            with col1:
                                # Show LATEST question from thread (not first) — for multi-turn clarity
                                latest_q = _sidebar_label_for_chat(ss._QA_DIRECTORY, full_chat_name, user, chat_question)
                                button_label = extract_without_breaking_words(latest_q, HISTORY_BUTTON_CHAR_LIMIT)
                                if is_current:
                                    button_label = "● " + button_label  # Add indicator for current chat
                                if st.button(button_label, key=f"load_{user}_{datetime_and_user}", help=latest_q, use_container_width=True):
                                    try:
                                        load_history(ss._QA_DIRECTORY, full_chat_name, user, ss.__qa_history_enabled)
                                    except Exception as e:
                                        st.error(f"Unable to load selected chat history: {e}")
                                        log_message("error", f"Error occurred while trying to load history: {e}")
                            with col2:
                                if st.button("🖉", key=f"rename_{user}_{datetime_and_user}", help="Rename this chat"):
                                    ss.rename_mode = rename_key
                                    st.rerun()
                            with col3:
                                if st.button("🗑", key=f"del_{user}_{datetime_and_user}", help="Delete this history"):
                                    if delete_history(ss._QA_DIRECTORY, full_chat_name, user):
                                        st.toast("History deleted")
                                        st.rerun()
                    st.divider()
                    
def _sidebar_label_for_chat(qa_directory, chat_name, user, fallback_question):
    """Return the most recent prompt from the saved chat JSON for use as a
    sidebar button label. Falls back to the filename-derived first question
    (fallback_question) if the JSON is unavailable or has no prompts.

    Reason: chat files are labelled by the FIRST question in their thread.
    For multi-turn threads, showing the LATEST question is more useful —
    the user sees their current context.
    """
    try:
        from utils.json_utils import load_qa_history
        filename = f"{chat_name}_{user}.json"
        data = load_qa_history(qa_directory, filename)
        if data and data.get('historical_prompts'):
            return data['historical_prompts'][-1]
    except Exception:
        pass
    return fallback_question


def add_bot_response_to_qa_history(bot_response):
    log_message("info", "Adding to history")

    ss.qa_history["historical_prompts"].append(ss._user_prompt)

    # Initialize 'stars' and 'comment' within the bot_response
    bot_response_with_appraisal = bot_response.copy()  # Create a copy to modify
    bot_response_with_appraisal["Rating"] = 3  # Default star rating
    bot_response_with_appraisal["Comment"] = ""  # Default comment
    bot_response_with_appraisal["QA_User"] = ss.user_name
                    
    # Append the modified bot response
    ss.qa_history["historical_responses"].append(bot_response_with_appraisal)
    ss._user_prompt = ""
    log_message("info", ss.qa_history)

def concatenate_docs_with_labels(text_docs, image_docs):
    """
    Concatenate text and image documents with clear section labels.

    Args:
        text_docs: List of text Document objects
        image_docs: List of image Document objects

    Returns:
        Formatted source text with labeled sections
    """
    sections = []

    # Text documents section
    if text_docs:
        text_contents = []
        for doc in text_docs:
            text_contents.append(doc.page_content)
        sections.append("[DOCUMENT TEXT]:\n" + "\n\n".join(text_contents))

    # Image documents section (screenshots with full context)
    # Option C: Display actual before text + image + actual after text
    if image_docs:
        image_contents = []
        for doc in image_docs:
            static_url = doc.metadata.get('static_url', '')
            qualitative_ocr = doc.metadata.get('qualitative_ocr', '')
            source_doc = doc.metadata.get('source_doc', '')
            preceding_text = doc.metadata.get('preceding_text', '')
            following_text = doc.metadata.get('following_text', '')

            # Build context-rich display: before text + image + after text
            image_block = f"Screenshot from {source_doc}:\n"
            if preceding_text:
                image_block += f"\n[PRECEDING CONTEXT]:\n{preceding_text}\n"
            image_block += f"\n[IMAGE]: {static_url}\n"
            image_block += f"[DESCRIPTION]: {qualitative_ocr}\n"
            if following_text:
                image_block += f"\n[FOLLOWING CONTEXT]:\n{following_text}"

            image_contents.append(image_block)
        sections.append("[RELEVANT SCREENSHOTS]:\n" + "\n\n---\n\n".join(image_contents))

    return "\n\n---\n\n".join(sections)


def process_user_prompt(status, answer_placeholder, embeddings, vdb, chroma_collection):
    stopwatch = Stopwatch()
    if is_greeting(ss._user_prompt) == 0:
        show_status(status, "Reading...", book_open_close_small_gif_path)

        stopwatch.start()
        image_vdb = getattr(ss, 'image_vdb', None)
        bm25_index = getattr(ss, 'bm25_index', None)
        bm25_corpus_docs = getattr(ss, 'bm25_corpus_docs', None)
        bm25_image_index = getattr(ss, 'bm25_image_index', None)
        bm25_image_corpus_docs = getattr(ss, 'bm25_image_corpus_docs', None)
        reranker_model = getattr(ss, 'reranker_model', None)

        validated_vdb = getattr(ss, 'validated_vdb', None)
        # Drop manual chunks whose reranker score doesn't beat 0 (= clearly
        # irrelevant). Stops "what is xtrak" from listing workflow chunks as
        # sources when the actual answer comes from a validated entry.
        retrieved = retrieve(
            ss._user_prompt,
            embeddings=embeddings, vdb=vdb, image_vdb=image_vdb,
            bm25_index=bm25_index, bm25_corpus_docs=bm25_corpus_docs,
            bm25_image_index=bm25_image_index, bm25_image_corpus_docs=bm25_image_corpus_docs,
            reranker_model=reranker_model,
            validated_vdb=validated_vdb,
            manual_score_threshold=0.0,
        )
        text_docs = retrieved.text_docs
        image_docs = retrieved.image_docs
        docs = combine_text_and_image_docs(text_docs, image_docs) if image_docs else text_docs
        ss._current_image_docs = image_docs

        elapsed_time = stopwatch.stop()
        log_message("info", f"Document Retrieval total time:{elapsed_time}")

        stopwatch.start()
        # Build source_text with validated docs ALWAYS in their own labeled
        # [VALIDATED EXPERT KNOWLEDGE] blocks, even when mixed with manual
        # chunks. The system_prompt's VALIDATED section then makes the LLM
        # emit "Source: approved by NAMES" whenever validated content drives
        # the answer — we use that downstream to filter displayed sources.
        validated_text_docs = [d for d in text_docs if d.metadata.get('source') == 'hitl_validated']
        manual_text_docs = [d for d in text_docs if d.metadata.get('source') != 'hitl_validated']

        validated_blocks = []
        if validated_text_docs:
            n = len(validated_text_docs)
            for idx, d in enumerate(validated_text_docs, 1):
                reviewer = d.metadata.get('reviewer') or 'unknown reviewer'
                reviewed_at = d.metadata.get('reviewed_at') or ''
                raw = d.page_content
                answer_only = raw.split("Answer:", 1)[1].strip() if "Answer:" in raw else raw
                approved_line = f"Approved by: {reviewer}"
                if reviewed_at:
                    approved_line += f" on {reviewed_at}"
                header = (
                    f"[VALIDATED EXPERT KNOWLEDGE {idx}/{n}]" if n > 1
                    else "[VALIDATED EXPERT KNOWLEDGE]"
                )
                validated_blocks.append(f"{header}\n{answer_only}\n[{approved_line}]")

        if image_docs:
            manual_part = concatenate_docs_with_labels(manual_text_docs, image_docs)
        elif manual_text_docs:
            manual_part = concatenate_docs_page_contents(manual_text_docs)
        else:
            manual_part = ""

        source_text_parts = []
        if validated_blocks:
            source_text_parts.append("\n\n".join(validated_blocks))
        if manual_part:
            source_text_parts.append(manual_part)
        source_text = "\n\n---\n\n".join(source_text_parts) if source_text_parts else ""

        # Scrub the complex V6 alt attribute ONLY from <img> tags whose alt
        # starts with V6 markers ([CONTEXT:/[IMAGE:/[FOLLOWING:). Those alts
        # can contain raw HTML from preceding_text (table markup, smart
        # quotes) that breaks quote balancing — the LLM copies the malformed
        # tag verbatim and downstream parsing fails.
        #
        # Small inline menu icons (height=9, simple/no alt) are left
        # UNTOUCHED: the LLM needs their surrounding alt as context to
        # write the navigation path that follows the icon.
        _pre_v6_count = len(re.findall(
            r"<img\s+src='\./app/static/[^']+'\s+alt='\[(?:CONTEXT|IMAGE|FOLLOWING)",
            source_text,
        ))
        source_text = re.sub(
            r"<img\s+src='(\./app/static/[^']+)'\s+alt='\[(?:CONTEXT|IMAGE|FOLLOWING).*?\]\s*'(?:\s*height=\d+)?\s*>",
            r"<img src='\1'>",
            source_text,
            flags=re.DOTALL,
        )
        source_text = re.sub(
            r"<img\s+src='(\./app/static/[^']+)'\s+alt='\[(?:CONTEXT|IMAGE|FOLLOWING)[^>]*>",
            r"<img src='\1'>",
            source_text,
        )
        if _pre_v6_count:
            log_message('info', f"Simplified {_pre_v6_count} V6 <img> tags (inline icons left intact)")

        elapsed_time = stopwatch.stop()
        log_message("info", f"Document Concatenation time:{elapsed_time}")

        stopwatch.start()
        acronyms = get_acronyms(source_text)
        if acronyms:
            additional_information = integrate_acronym_meaning_in_response(
                acronyms, True, method="from_csv", source_document_name="AD-CHAT docs",
            )
        else:
            additional_information = ""
        elapsed_time = stopwatch.stop()
        log_message("info", f"Acronym integration time:{elapsed_time}")

        show_status(status, "Answering...", book_open_close_small_gif_path)
        ss._pending_docs = docs

        stopwatch.start()
        # Sync settings.json into ss before reading the LLM params below;
        # picks up any slider changes the superuser made during this session.
        load_session_state(ss, json_file_name='settings.json')

        # Defensive scrub of chat history before it enters the prompt — older
        # sessions or pre-fix runs may still hold base64-bloated entries.
        if ss.__qa_history_enabled and ss.chat_history:
            _DATA_URI_IMG = re.compile(r"<img\s+src='data:image/[^']+'[^>]*>", re.DOTALL)
            history_for_prompt = [
                (role, _DATA_URI_IMG.sub('[image]', text))
                for role, text in ss.chat_history
            ]
        else:
            history_for_prompt = []

        enhanced_question = enhance_question_for_llm(ss._user_prompt)
        messages = compose_messages(
            question=enhanced_question,
            system_prompt_template=system_prompt,
            source_text=source_text,
            additional_information=additional_information,
            chat_history=history_for_prompt,
            content_summary=content_summary,
        )

        try:
            chunks = call_llm(
                ss.qa_model,
                messages,
                ss.__qa_model_name,
                max_tokens=ss.__max_tokens,
                temperature=ss.__temperature,
                top_p=ss.__top_p,
                frequency_penalty=ss.__frequency_penalty,
                presence_penalty=ss.__presence_penalty,
                stop=ss.__stop,
                n=ss.__n,
                seed=42,
                stream=True,
            )
        except RuntimeError as e:
            log_message('error', f"call_llm exhausted retries: {e}")
            answer = "Failed to get response after multiple retries. Please try again later."
            answer_placeholder.markdown(
                f'<div class="message">{answer}</div>', unsafe_allow_html=True,
            )
            gap_metadata = GapMetadata(confidence=0.0, missing_info="LLM call failed after retries")
        else:
            # ask_ada streams chunks to the UI, accumulates inline <img>/$LaTeX$,
            # strips the [[META]] trailer, and appends to chat_history.
            answer, _exit_code, gap_metadata = ask_ada(
                answer_placeholder, chunks, ss._user_prompt, ss.chat_history,
                ss.__qa_history_enabled,
            )

        # Persist a gap signal — non-fatal if SQLite write fails. Stash the
        # row id + is_gap flag in session state so app.py can render an
        # inline "do you know this?" form below the answer when relevant.
        ss._latest_gap_id = None
        ss._latest_is_gap = False
        try:
            from core.gap_detection import is_gap as _is_gap_fn
            gap_id = record_gap(
                GAPS_DB_PATH,
                question=ss._user_prompt,
                answer=answer,
                metadata=gap_metadata,
                num_text_docs=len(text_docs),
                num_image_docs=len(image_docs),
                user_name=getattr(ss, 'user_name', None),
                model=ss.__qa_model_name,
            )
            ss._latest_gap_id = gap_id
            ss._latest_is_gap = _is_gap_fn(gap_metadata, len(text_docs), len(image_docs))
        except Exception as e:
            log_message('warning', f"Gap recording failed (non-fatal): {e}")

        elapsed_time = stopwatch.stop()
        log_message("info", f"OpenAI response time:{elapsed_time}")

        stopwatch.start()
        manage_chat_history(ss.chat_history, ss.__max_tokens_chat_history)
        elapsed_time = stopwatch.stop()
        log_message("info", f"Chat history management time:{elapsed_time}")

        # Source-display filter:
        # 1. If the LLM emitted "Source: approved by ..." (system_prompt
        #    instructs this whenever VALIDATED EXPERT KNOWLEDGE drove the
        #    answer), drop manual chunks — they didn't contribute.
        # 2. Same for a clear "not enough info" refusal — manual didn't help.
        # Normalize curly apostrophes (LLM frequently emits U+2019).
        _ans_norm = (answer or "").lower().replace("’", "'")
        _validated_signal = "source: approved by" in _ans_norm
        _refusal_markers = (
            "i don't have enough information",
            "i do not have enough information",
            "not enough information from billtrak",
            "the billtrak documents do not",
            "the billtrak documents don't",
        )
        _refusal_signal = any(m in _ans_norm for m in _refusal_markers)
        if _validated_signal or _refusal_signal:
            docs = [d for d in docs if d.metadata.get('source') == 'hitl_validated']

        stopwatch.start()
        bot_response = create_bot_response(answer, docs, ss.chat_history, ss._user_prompt)
        elapsed_time = stopwatch.stop()
        log_message("info", f"Bot response creation time:{elapsed_time}")
    else:
        bot_response = {
            "result": is_greeting(ss._user_prompt),
            "greet_flag": True,
            "chat_history": ss.qa_history["historical_responses"][-1]["chat_history"] if len(ss.qa_history["historical_responses"]) > 0 else []
        }

    status.markdown("", unsafe_allow_html=True)
    status.empty()
    add_bot_response_to_qa_history(bot_response)
    ss._pending_question = None
    ss._pending_answer = None
    ss._pending_docs = None