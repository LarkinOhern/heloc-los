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
    page_icon="🏠",
    layout="wide",
)

# Initialize database on first run
init_db()

# Render auth sidebar (sets role in session state)
render_auth_sidebar()

role = st.session_state.get("role", "Borrower")

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
    page = st.sidebar.radio(
        "Navigation",
        ["Pipeline", "Review Application", "Conditions"],
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
    page = st.sidebar.radio(
        "Navigation",
        ["Pipeline", "Review Application", "Conditions", "Admin Config"],
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
