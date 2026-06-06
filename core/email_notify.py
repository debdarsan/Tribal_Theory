"""Outlook e-mail notification for HITL assignments.

When a Q&A contribution is assigned to a reviewer (superuser), we send a
notification e-mail to that reviewer automatically via Outlook — `send_assignment_email`
calls Outlook's `.Send()`, so no compose window/draft is shown.

The reviewer's e-mail address is read from `users.xlsx` (an "Email" column, looked
up by User ID). No Streamlit imports here so the lookup/body helpers stay unit-testable.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Header names we accept for the e-mail column, checked case-insensitively.
_EMAIL_HEADER_CANDIDATES = (
    "email", "email address", "e-mail", "e-mail address",
    "mail", "emailid", "email id", "teoco email",
)
_USERID_HEADER_CANDIDATES = ("user id", "userid", "user_id", "id")


def _norm(s) -> str:
    return str(s).strip().lower()


def lookup_email(user_id: str, users_xlsx_path: str | Path = "users.xlsx") -> Optional[str]:
    """Return the e-mail address for `user_id` from users.xlsx, or None if the
    file/column/row is missing or the cell is blank. Tolerant of several common
    header spellings for both the e-mail and the User ID columns."""
    if not user_id:
        return None
    try:
        import pandas as pd
        df = pd.read_excel(users_xlsx_path)
    except Exception as e:  # file missing, locked, openpyxl missing, etc.
        logger.error("lookup_email: could not read %s: %s", users_xlsx_path, e)
        return None

    cols = {_norm(c): c for c in df.columns}
    email_col = next((cols[h] for h in _EMAIL_HEADER_CANDIDATES if h in cols), None)
    id_col = next((cols[h] for h in _USERID_HEADER_CANDIDATES if h in cols), None)
    if email_col is None or id_col is None:
        logger.warning(
            "lookup_email: missing email/id column in %s (have %s)",
            users_xlsx_path, list(df.columns),
        )
        return None

    target = _norm(user_id)
    for _, row in df.iterrows():
        if _norm(row[id_col]) == target:
            val = row[email_col]
            email = "" if val is None else str(val).strip()
            # pandas turns blank cells into the string 'nan'.
            if email and email.lower() != "nan":
                return email
            return None
    return None


def build_assignment_body(
    *,
    reviewer_name: str,
    submitter_name: str,
    question: str,
    contribution: str,
    gap_id,
) -> tuple[str, str]:
    """Return (subject, body) for the assignment notification e-mail."""
    subject = f"[TRIBIQ] Knowledge review assigned to you (#{gap_id})"
    body = (
        f"Hi {reviewer_name or 'there'},\n\n"
        f"A knowledge contribution has been assigned to you for review in TRIBIQ.\n\n"
        f"Submitted by: {submitter_name or 'a user'}\n"
        f"Reference: gap #{gap_id}\n\n"
        f"Question:\n{question or '(not recorded)'}\n\n"
        f"Proposed answer / contribution:\n{contribution or '(empty)'}\n\n"
        f"Please open TRIBIQ and use the HITL Review panel to approve, edit, or "
        f"reject this submission.\n\n"
        f"— TRIBIQ (automated notification)"
    )
    return subject, body


def send_assignment_email(
    *,
    to_email: str,
    subject: str,
    body: str,
) -> bool:
    """Send the assignment e-mail automatically via Outlook (no draft shown).
    Returns True if Outlook accepted the send, False otherwise. Never raises —
    failures are logged and reported via the return value so a mail problem
    can't block the (already-saved) assignment."""
    if not to_email:
        return False
    try:
        import pythoncom
        import win32com.client as win32
    except Exception as e:
        logger.error("send_assignment_email: pywin32 unavailable: %s", e)
        return False

    # Streamlit runs the script in a worker thread; COM needs explicit init there.
    coinit = False
    try:
        pythoncom.CoInitialize()
        coinit = True
    except Exception:
        coinit = False
    try:
        outlook = win32.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # 0 = olMailItem
        mail.To = to_email
        mail.Subject = subject
        mail.Body = body
        mail.Send()  # send immediately, no compose window
        return True
    except Exception as e:
        logger.error("send_assignment_email: Outlook send failed: %s", e)
        return False
    finally:
        if coinit:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def notify_assignment(
    *,
    assignee_user_id: str,
    reviewer_name: str,
    submitter_name: str,
    question: str,
    contribution: str,
    gap_id,
    users_xlsx_path: str | Path = "users.xlsx",
) -> tuple[bool, str]:
    """Look up the assignee's e-mail and send the notification via Outlook
    automatically (no draft shown). Returns (ok, message) where message is a
    short human-readable status the caller can surface (e.g. via
    st.toast/st.warning). Never raises."""
    email = lookup_email(assignee_user_id, users_xlsx_path)
    if not email:
        return False, f"No e-mail on file for '{assignee_user_id}' — no notification sent."
    subject, body = build_assignment_body(
        reviewer_name=reviewer_name,
        submitter_name=submitter_name,
        question=question,
        contribution=contribution,
        gap_id=gap_id,
    )
    if send_assignment_email(to_email=email, subject=subject, body=body):
        return True, f"Notification e-mail sent to {email}."
    return False, f"Could not send a notification e-mail to {email}."
