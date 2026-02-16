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
    page_title="EquityEngine",
    page_icon="\U0001f3e0",
    layout="wide",
)

# ── Global Styles ───────────────────────────────────────────────────────────
from src.utils.styles import inject_css
inject_css()

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

# Bump _DB_VERSION to force re-initialization (e.g., to re-seed after changes).
_DB_VERSION = 3

@st.cache_resource
def _init_once(_version):
    init_db()
    seed_database()

_init_once(_DB_VERSION)

# Render auth sidebar (sets role in session state)
render_auth_sidebar()

role = st.session_state.get("role", "Borrower")


# ── Borrower Landing Page ─────────────────────────────────────────────────
def _render_borrower_landing():
    """Welcome page for borrowers who haven't entered their email yet."""
    # Check if user wants to see the Learn More page
    if st.session_state.get("show_learn_more"):
        from src.pages import heloc_learn_more
        heloc_learn_more.render()
        if st.button("Back to Home"):
            st.session_state["show_learn_more"] = False
            st.rerun()
        return

    st.markdown(
        '<h1 style="color:#1565c0; margin-bottom:0;">Welcome to '
        '<span style="color:#0d47a1;">EquityEngine</span></h1>',
        unsafe_allow_html=True,
    )
    st.markdown("#### Your home equity, working for you.")
    st.write("")

    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown(
            """
A **Home Equity Line of Credit (HELOC)** lets you borrow against the equity
you've built in your home -- giving you flexible, low-cost access to funds
when you need them.

**Common uses:**
- Home renovations and improvements
- Debt consolidation at a lower rate
- Education expenses
- Major purchases or emergency reserves

With EquityEngine, applying is simple. Our guided application walks you
through each step, and you can save your progress and come back anytime.
            """
        )

    with col2:
        st.markdown(
            """
<div style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
            padding: 24px; border-radius: 12px; text-align: center;
            border: 1px solid #90caf9;">
    <h3 style="color: #0d47a1; margin-top: 0;">Ready to get started?</h3>
    <p style="color: #1565c0; font-size: 16px;">
        Enter your email in the sidebar to begin your application or
        resume where you left off.
    </p>
    <p style="color: #666; font-size: 14px; margin-bottom: 0;">
        Takes about 10 minutes to complete.
    </p>
</div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")
    if st.button("Learn more about HELOCs"):
        st.session_state["show_learn_more"] = True
        st.rerun()


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
        _render_borrower_landing()
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
