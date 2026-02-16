"""Main entry point — role routing and sidebar navigation."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from src.database import init_db
from src.auth import render_auth_sidebar
from src.pages import (
    borrower_apply,
    borrower_status,
    borrower_documents,
    employee_pipeline,
    employee_review,
    employee_conditions,
    admin_config,
)

st.set_page_config(
    page_title="HELOC LOS",
    page_icon="\U0001f3e0",
    layout="wide",
)

# ── Demo Disclaimer ─────────────────────────────────────────────────────────
st.sidebar.warning(
    "**DEMO APPLICATION** -- For educational and evaluation purposes only. "
    "Do NOT enter real personally identifiable information (SSN, DOB, real "
    "names, etc.). All data is fictitious sample data."
)

# Initialize database and seed sample data if empty.
# @st.cache_resource ensures this runs ONCE per app lifecycle, not on every
# Streamlit rerun.  Without this, init_db + seed_settings trigger 15+ Turso
# sync calls on every page load (~2-3s each = 40+ second loads).
from src.seed import seed_database

@st.cache_resource
def _init_once():
    init_db()
    seed_database()

_init_once()

# Render auth sidebar (sets role in session state)
render_auth_sidebar()

role = st.session_state.get("role", "Borrower")


def _get_nav_default(options: list[str]) -> int:
    """Check for a pending navigation request and return the index to default to."""
    target = st.session_state.pop("_pending_nav", None)
    if target and target in options:
        return options.index(target)
    return 0


# ── Borrower Pages ───────────────────────────────────────────────────────────
if role == "Borrower":
    email = st.session_state.get("borrower_email", "")
    if not email:
        st.title("Welcome to HELOC LOS")
        st.write("Please enter your email address in the sidebar to get started.")
    else:
        page = st.sidebar.radio(
            "Navigation",
            ["Apply", "Status", "Documents"],
            key="borrower_nav",
        )
        if page == "Apply":
            borrower_apply.render()
        elif page == "Status":
            borrower_status.render()
        elif page == "Documents":
            borrower_documents.render()

# ── Loan Officer Pages ──────────────────────────────────────────────────────
elif role == "Loan Officer":
    lo_options = ["Pipeline", "Review Application", "Conditions"]
    page = st.sidebar.radio(
        "Navigation",
        lo_options,
        index=_get_nav_default(lo_options),
        key="lo_nav",
    )
    st.sidebar.caption(
        f"Logged in as: {st.session_state.get('employee_display_name', '')}"
    )
    if page == "Pipeline":
        employee_pipeline.render()
    elif page == "Review Application":
        employee_review.render()
    elif page == "Conditions":
        employee_conditions.render()

# ── Admin Pages ──────────────────────────────────────────────────────────────
elif role == "Admin":
    admin_options = ["Pipeline", "Review Application", "Conditions", "Admin Config"]
    page = st.sidebar.radio(
        "Navigation",
        admin_options,
        index=_get_nav_default(admin_options),
        key="admin_nav",
    )
    st.sidebar.caption(
        f"Logged in as: {st.session_state.get('employee_display_name', '')}"
    )
    if page == "Pipeline":
        employee_pipeline.render()
    elif page == "Review Application":
        employee_review.render()
    elif page == "Conditions":
        employee_conditions.render()
    elif page == "Admin Config":
        admin_config.render()
