"""Session-based role selector (no real auth)."""

import streamlit as st
from src.config import EMPLOYEES


def render_auth_sidebar():
    """Render the role selector in the sidebar. Sets session_state keys."""
    st.sidebar.markdown(
        '<div style="text-align:center; padding:8px 0 4px;">'
        '<span style="font-size:24px; font-weight:700; color:#1565c0;">Equity</span>'
        '<span style="font-size:24px; font-weight:700; color:#0d47a1;">Engine</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.sidebar.caption("Prototype -- No Authentication")

    role = st.sidebar.selectbox(
        "Select Role",
        ["Borrower", "Loan Officer", "Admin"],
        key="role_selector",
    )
    st.session_state["role"] = role

    if role == "Borrower":
        email = st.sidebar.text_input(
            "Your Email",
            key="borrower_email_input",
            placeholder="borrower@example.com",
        )
        st.session_state["borrower_email"] = email.strip().lower()
        st.session_state["current_user"] = email.strip().lower()

    elif role in ("Loan Officer", "Admin"):
        employee_options = [
            e for e in EMPLOYEES
            if (role == "Admin" and e["role"] == "Admin")
            or (role == "Loan Officer" and e["role"] == "Loan Officer")
        ]
        if not employee_options:
            employee_options = EMPLOYEES

        display_names = [e["display_name"] for e in employee_options]
        selected = st.sidebar.selectbox(
            "Employee",
            display_names,
            key="employee_selector",
        )
        emp = next(e for e in employee_options if e["display_name"] == selected)
        st.session_state["current_user"] = emp["username"]
        st.session_state["employee_display_name"] = emp["display_name"]
        st.session_state["employee_role"] = emp["role"]

    st.sidebar.divider()
