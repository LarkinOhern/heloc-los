"""Application status tracker with visual progress stepper and audit timeline."""

import streamlit as st

from src.config import STATUS_LABELS, STATUS_COLORS, STATUSES
from src.utils.db_helpers import (
    get_applications_by_email, get_application, get_borrowers,
    get_audit_log, get_conditions,
)
from src.utils.formatters import fmt_currency, fmt_date, fmt_datetime

# The "happy path" progression for the stepper display
PROGRESS_STEPS = ["SUBMITTED", "IN_REVIEW", "UNDERWRITING", "APPROVED", "CLOSING", "FUNDED"]


def render():
    st.header("Application Status")
    st.caption(
        "Track the progress of your HELOC application. Each step in the process "
        "is shown below, along with a timeline of all activity on your file."
    )
    email = st.session_state.get("borrower_email", "")
    if not email:
        st.warning("Enter your email in the sidebar.")
        return

    apps = get_applications_by_email(email)
    # Exclude drafts — those belong on the Apply page
    apps = [a for a in apps if a["status"] != "DRAFT"]

    if not apps:
        st.info("No submitted applications found for this email. "
                "Go to **Apply** to start a new application.")
        return

    # If multiple apps, let them pick one
    if len(apps) == 1:
        app = apps[0]
    else:
        options = {a["application_number"]: a for a in apps}
        selected = st.selectbox("Select Application", list(options.keys()))
        app = options[selected]

    _render_status(app)


def _render_status(app: dict):
    status = app["status"]
    color = STATUS_COLORS.get(status, "#9e9e9e")
    label = STATUS_LABELS.get(status, status)

    # Header with status badge
    st.subheader(app["application_number"])
    st.markdown(
        f'<span style="background-color:{color}; color:white; padding:4px 12px; '
        f'border-radius:12px; font-weight:bold;">{label}</span>',
        unsafe_allow_html=True,
    )
    st.write("")

    # ── Progress Stepper ─────────────────────────────────────────────────
    if status in ("DENIED", "WITHDRAWN"):
        st.warning(f"This application has been **{label.lower()}**.")
    else:
        _render_stepper(status)

    st.divider()

    # ── Key Details ──────────────────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    col1.metric("HELOC Amount", fmt_currency(app["heloc_amount_requested"]))
    col2.metric("Property Value", fmt_currency(app["property_value"]))
    col3.metric("Submitted", fmt_date(app["submitted_at"]))

    # ── Conditions (if any) ──────────────────────────────────────────────
    if status in ("APPROVED_WITH_CONDITIONS", "CLOSING"):
        conditions = get_conditions(app["id"])
        open_conds = [c for c in conditions if c["status"] == "OPEN"]
        if open_conds:
            st.divider()
            st.write("**Outstanding Conditions**")
            for c in open_conds:
                st.write(f"- {c['description']} ({c['condition_type'].replace('_', ' ').title()})")

    # ── Audit Timeline ───────────────────────────────────────────────────
    st.divider()
    st.write("**Activity Timeline**")
    entries = get_audit_log(app["id"])
    if entries:
        for entry in entries:
            col1, col2 = st.columns([1, 3])
            col1.caption(fmt_datetime(entry["performed_at"]))
            col2.write(f"**{entry['action'].replace('_', ' ').title()}** — {entry['details']}")
    else:
        st.caption("No activity recorded yet.")


def _render_stepper(current_status: str):
    """Render a horizontal progress stepper showing where the app is in the pipeline."""
    # Map APPROVED_WITH_CONDITIONS to APPROVED slot for display
    display_status = "APPROVED" if current_status == "APPROVED_WITH_CONDITIONS" else current_status

    try:
        current_idx = PROGRESS_STEPS.index(display_status)
    except ValueError:
        current_idx = -1

    cols = st.columns(len(PROGRESS_STEPS))
    for i, step in enumerate(PROGRESS_STEPS):
        step_label = STATUS_LABELS.get(step, step)
        if i < current_idx:
            # Completed
            cols[i].markdown(
                f'<div style="text-align:center; padding:8px; background-color:#e8f5e9; '
                f'border-radius:8px; border:2px solid #4caf50;">'
                f'<strong style="color:#4caf50;">{step_label}</strong></div>',
                unsafe_allow_html=True,
            )
        elif i == current_idx:
            # Current
            color = STATUS_COLORS.get(current_status, "#2196f3")
            cols[i].markdown(
                f'<div style="text-align:center; padding:8px; background-color:{color}; '
                f'border-radius:8px; border:2px solid {color};">'
                f'<strong style="color:white;">{step_label}</strong></div>',
                unsafe_allow_html=True,
            )
        else:
            # Future
            cols[i].markdown(
                f'<div style="text-align:center; padding:8px; background-color:#f5f5f5; '
                f'border-radius:8px; border:2px solid #e0e0e0;">'
                f'<strong style="color:#9e9e9e;">{step_label}</strong></div>',
                unsafe_allow_html=True,
            )
