import streamlit as st
from vars.s_state import *
import streamlit_authenticator as stauth
import pandas as pd
import pyarrow as pa
from consts.consts import *
from styles.styles import *
from utils.init_app_utils import *
from utils.chat_utils import *
from streamlit_star_rating import st_star_rating
from utils.chat_utils import *
from utils.json_utils import *
from app_helper import *
from core.gap_detection import record_user_input, get_gap

st.set_page_config(
    page_title="TRIBIQ",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

def initialize_app():
    log_message("info", "Initializing app...")
    initialize_session_states()
    init_app_settings()
    log_message("info", "App initialized.")

try:
    initialize_session_states()
    ss.authentication_status = init_authentication()

    if ss.authentication_status:
        if "app_initialized" not in st.session_state or not st.session_state.app_initialized:
            initialize_app()
            st.session_state.app_initialized = True

        # Apply pending Dark/Light theme before any rendering
        apply_pending_color_theme()

        # if not ss.custom_page_settings_applied:
        apply_custom_page_settings()
            # ss.custom_page_settings_applied = True

        show_title(app_title, app_version, copyright, teoco_logo, app_long_name)
        show_footer(footer_text)
        with st.sidebar:
            st.markdown(text_box_html.replace("{text}", ss["full_name"]), unsafe_allow_html=True)
            ss["auth_object"].logout("Exit", "sidebar")

        if not ss.accept_questions:
            log_message("error", f"Please ingest documents before asking questions! Current record count: {ss._vectorstore_record_count}")
            st.error(f"Please ingest documents before asking questions! Current record count: {ss._vectorstore_record_count}")
            st.stop()

        with st.sidebar:
            show_sidebar_content()
            show_color_settings()
            # Reserve the History block's vertical slot here, but DEFER its
            # actual render until after save_QA has written the new chat
            # JSON to disk. Otherwise a fresh chat's first answer would not
            # show up in the sidebar until the user triggered another rerun.
            _history_slot = st.empty()

        if '_form_gen' not in ss:
            ss._form_gen = 0

        # The main area shows EITHER the Q&A/chat screen OR exactly one panel
        # (HITL, Manage Knowledge, Auto Q&A, Gap Finder, Quiz). While a panel
        # is open, hide the chat input bar, the New button and the Q&A history;
        # each panel's Close button restores this Q&A screen.
        panel_open = active_main_panel() is not None

        if not panel_open:
            c1, c2 = st.columns([10, 1])
            with c1:
                with st.form(key=f"question_form_{ss._form_gen}", clear_on_submit=False, border=False):
                    question_value = st.text_input("Question",
                        placeholder="Type your question and press Enter...",
                        label_visibility="collapsed",
                        key="chat_question_input",
                        disabled=not(ss.accept_questions))
                    form_submitted = st.form_submit_button("Ask",
                        disabled=not(ss.accept_questions))
                # Hide the submit button OFF-SCREEN rather than via display:none.
                # Streamlit 1.46 emits a "Missing Submit Button" warning when
                # the only submit button is display:none — but `position:
                # absolute; left:-9999px` keeps the button in the DOM and in
                # flow detection, so the warning stays silent while the button
                # remains invisible. Users press Enter to submit.
                #
                # SCOPED via :has() to ONLY this chat question form. The previous
                # unscoped selector hid EVERY form-submit button in the app —
                # breaking the quiz, the knowledge-contribution form, and the
                # Manage-Knowledge Save/Delete buttons.
                st.markdown("""<style>
                    [data-testid="stForm"]:has(input[placeholder^="Type your question"]) [data-testid="stFormSubmitButton"] {
                        position: absolute !important;
                        left: -9999px !important;
                        width: 1px !important;
                        height: 1px !important;
                        overflow: hidden !important;
                    }
                </style>""", unsafe_allow_html=True)
            with c2:
                if st.button("New", disabled=not(ss.accept_questions)):
                    clear_QA()
        else:
            # A panel owns the main area; no chat submission this run.
            form_submitted = False
            question_value = ""

        status = st.empty()
        answer_placeholder = st.empty()

        # Recovery from interrupted streaming (e.g., websocket close mid-answer).
        # If ask_ada saved a partial/complete bot_message to ss._pending_answer
        # but process_user_prompt's add_bot_response_to_qa_history never ran,
        # reconstitute the QA entry now so the answer isn't lost.
        pending_q = ss.get('_pending_question')
        pending_a = ss.get('_pending_answer') or ''
        if (pending_q and pending_a.strip() and
            (not ss.qa_history['historical_prompts'] or
             ss.qa_history['historical_prompts'][-1] != pending_q)):
            log_message("info", f"Recovering interrupted QA (pending answer: {len(pending_a)} chars)")
            ss._user_prompt = pending_q
            pending_docs = ss.get('_pending_docs') or []
            bot_response = create_bot_response(pending_a, pending_docs, ss.chat_history, pending_q)
            add_bot_response_to_qa_history(bot_response)
            ss._pending_question = None
            ss._pending_answer = None
            ss._pending_docs = None

        # Track whether the prompt actually produced a stored QA entry. The
        # form input is cleared only when this is True; otherwise a failed
        # request would silently wipe the user's question with no answer.
        prompt_processed_ok = False
        history_len_before = len(ss.qa_history['historical_prompts'])

        try:
            if form_submitted and question_value.strip():
                ss._user_prompt = question_value
                log_message("info", "user_prompt: " + ss._user_prompt)
                process_user_prompt(status, answer_placeholder, ss.embeddings, ss.vectorstore_obj, ss.chroma_collection)
                prompt_processed_ok = (
                    len(ss.qa_history['historical_prompts']) > history_len_before
                )

        except Exception as e:
            log_message("error",f"Exception occured while trying to trigger a prompt: {e}")
            st.error(f"Sorry! An unexpected error occured while trying to generate results: {e}")
            # Persist a placeholder response so the question is not lost from
            # history just because generation failed.
            if form_submitted and question_value.strip() and \
               len(ss.qa_history['historical_prompts']) == history_len_before:
                placeholder = create_bot_response(
                    f"[Failed to generate response: {e}]",
                    [], ss.chat_history, ss._user_prompt or question_value,
                )
                add_bot_response_to_qa_history(placeholder)

        # Persist QA history to disk. Email is isolated in its own try/except
        # so an SMTP failure can no longer masquerade as a save failure.
        try:
            if len(ss.qa_history['historical_prompts']) > 0:
                if ss._qa_filename == "":
                    formulate_qa_filename() # formulated value is stored in ss._qa_filename
                save_QA(ss._QA_DIRECTORY, ss._qa_filename, ss.qa_history)
            else:
                ss._qa_filename = ""
        except Exception as e:
            log_message("error", f"Error saving user's responses: {e}")
            st.error("Sorry! Could not save your chat to history!")

        try:
            if ss.__qa_emailing_enabled and ss._qa_filename:
                send_email('rupanteoco@gmail.com', 'airesearch28@gmail.com', ss._qa_filename, ss.qa_history)
        except Exception as e:
            log_message("error", f"Error emailing QA history: {e}")

        # Render the sidebar History block now — save_QA has already written
        # the current chat to disk, so a fresh chat's first answer appears in
        # the History list immediately, on the same rerun.
        try:
            with _history_slot.container():
                show_chat_history()
        except Exception as e:
            log_message("error", f"Error rendering chat history sidebar: {e}")

        # HITL review queue — sidebar expander right after history (superuser-only).
        try:
            with st.sidebar:
                show_hitl_review_sidebar()
        except Exception as e:
            log_message("error", f"Error rendering HITL sidebar: {e}")

        # Manage Knowledge — sidebar expander after HITL (superuser-only).
        try:
            with st.sidebar:
                show_kb_manager_sidebar()
        except Exception as e:
            log_message("error", f"Error rendering Manage Knowledge sidebar: {e}")

        # Auto Q&A — sidebar expander after HITL.
        try:
            with st.sidebar:
                show_synthetic_questions_sidebar()
        except Exception as e:
            log_message("error", f"Error rendering Auto Q&A sidebar: {e}")

        # Knowledge Gap Finder — sidebar expander after Auto Q&A.
        try:
            with st.sidebar:
                show_gap_finder_sidebar()
        except Exception as e:
            log_message("error", f"Error rendering Gap Finder sidebar: {e}")

        # Quiz — sidebar expander after Gap Finder. Visible to any user.
        try:
            with st.sidebar:
                show_quiz_sidebar()
        except Exception as e:
            log_message("error", f"Error rendering Quiz sidebar: {e}")

        # If an assignment just staged a notification e-mail, confirm before
        # sending (pops the "Send email?" Yes/No modal). No-op when nothing staged.
        try:
            maybe_confirm_pending_email()
        except Exception as e:
            log_message("error", f"Error rendering email-confirm dialog: {e}")

        # HITL review panel — when a sidebar row is selected, render the full
        # review form at the top of the main area. Chat stays visible below.
        try:
            show_hitl_review_main()
        except Exception as e:
            log_message("error", f"Error rendering HITL main panel: {e}")

        # Manage Knowledge panel — list/search/edit/delete injected knowledge.
        try:
            show_kb_manager_main()
        except Exception as e:
            log_message("error", f"Error rendering Manage Knowledge main panel: {e}")

        # Auto Q&A panel — surfaces the latest auto-generated Q+A in the main area.
        try:
            show_synthetic_question_main()
        except Exception as e:
            log_message("error", f"Error rendering Auto Q&A main panel: {e}")

        # Knowledge Gap Finder panel — surfaces a gap-probing Q+A plus the
        # contribution form when the answer is flagged.
        try:
            show_gap_finder_main()
        except Exception as e:
            log_message("error", f"Error rendering Gap Finder main panel: {e}")

        # Quiz panel — renders the current quiz question + grading + next.
        try:
            show_quiz_main()
        except Exception as e:
            log_message("error", f"Error rendering Quiz main panel: {e}")

        try:
            if not panel_open:
                display_QA(ss.qa_history, ss.show_appraisal_widgets, ss.filter_appraised)
                log_message("info", ss.qa_history)
        except Exception as e:
            log_message("error", f"Error displaying Q&A page: {e}")
            st.error(f"Could not display Q&A due to an unexpected error! Please try to reload the page: {e}")

        # Inline contribution form: shown after EVERY answer (not just gaps).
        # When the answer was flagged as a gap, the copy nudges the user to
        # fill in missing info. When not flagged, the copy invites
        # corrections / additions. Either way the submission feeds the same
        # HITL queue as gap contributions.
        try:
            if not panel_open and ss.get('_latest_gap_id'):
                gap_id = ss._latest_gap_id
                is_gap = ss.get('_latest_is_gap', False)
                with st.form(key=f"gap_input_form_{gap_id}", clear_on_submit=True):
                    if is_gap:
                        st.markdown(
                            "**I couldn't fully answer that from the BillTrak documents.** "
                            "If you know the answer, share it below and I'll save it for expert review."
                        )
                        placeholder = "Do you have something to add?"
                    else:
                        st.markdown(
                            "**Anything to add?** "
                            "Share corrections, additional context, or related knowledge "
                            "and I'll save it for expert review."
                        )
                        placeholder = "Add context, corrections, or related details. Leave blank if nothing to add."
                    user_knowledge = st.text_area(
                        "Your knowledge",
                        key=f"gap_input_text_{gap_id}",
                        height=120,
                        placeholder=placeholder,
                    )
                    approver_id = render_approver_selectbox(f"gap_input_form_{gap_id}")
                    submitted = st.form_submit_button("Submit for review")
                    if submitted:
                        if not user_knowledge.strip():
                            st.warning("Please enter some text before submitting.")
                        elif not approver_id:
                            st.warning("Please select a superuser to approve this submission.")
                        else:
                            try:
                                ok = record_user_input(
                                    GAPS_DB_PATH,
                                    gap_id,
                                    user_knowledge.strip(),
                                    user_name=ss.get('full_name') or ss.get('user_name'),
                                    assigned_to=approver_id,
                                )
                                if ok:
                                    st.toast("Thanks! Saved for review.")
                                    # Notify the assigned reviewer via Outlook.
                                    _gap_row = get_gap(GAPS_DB_PATH, gap_id) or {}
                                    notify_assignee_via_outlook(
                                        assignee_user_id=approver_id,
                                        gap_id=gap_id,
                                        submitter_name=ss.get('full_name') or ss.get('user_name'),
                                        question=_gap_row.get('question', ''),
                                        contribution=user_knowledge.strip(),
                                    )
                                    ss._latest_gap_id = None
                                    ss._latest_is_gap = False
                                    # Force a rerun so the HITL sidebar
                                    # picks up the new pending entry on
                                    # this same submit — otherwise the
                                    # user has to manually reload.
                                    st.rerun()
                                else:
                                    st.warning("Could not find that gap entry to update.")
                            except Exception as e:
                                log_message('error', f"Failed to record user input: {e}")
                                st.error(f"Could not save your input: {e}")
        except Exception as e:
            log_message("error", f"Error rendering gap-input form: {e}")

        # Clear the input visually NOW via JS — set DOM value to '' and
        # dispatch a React-compatible 'input' event so Streamlit's widget
        # state also resets. We deliberately do NOT rotate the form key
        # here: rotating would retire the current form before the user's
        # next quick submission can land, dropping it silently. With the
        # input event firing, Streamlit captures the cleared state on the
        # next rerun without needing a key change. Avoids st.rerun() so the
        # sidebar History expander (no key= until Streamlit 1.36) stays open.
        if form_submitted and question_value.strip() and prompt_processed_ok:
            import streamlit.components.v1 as _components
            _components.html("""
<script>
(function(){
    const doc = window.parent.document;
    const input = doc.querySelector('input[placeholder="Type your question and press Enter..."]');
    if (input) {
        const nativeSetter = Object.getOwnPropertyDescriptor(
            window.parent.HTMLInputElement.prototype, 'value'
        ).set;
        nativeSetter.call(input, '');
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.blur();
    }
})();
</script>
""", height=0)
    else:

        show_main_area_image()

        ss.qa_history = {
            "historical_prompts": [],
            "historical_responses": [],
        }
        ss._user_prompt = ""

except Exception as e:
    log_message('error', f"Error initializing QA page: {e}")
    st.error( f"Error initializing QA page: {e}")
    st.stop()
