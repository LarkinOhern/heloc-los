"""Who may act on an application (finding C-02).

Loan officers work only the files assigned to them; an unassigned file has
to be claimed first. Admins can act on any file and reassign it. Reading is
open to every employee; these checks gate the actions.
"""

import streamlit as st


def current_actor() -> tuple[str, str]:
    """(username, role) of the signed-in employee."""
    return st.session_state.get("current_user", ""), st.session_state.get("role", "")


def can_work(app: dict) -> bool:
    user, role = current_actor()
    if role == "Admin":
        return True
    return bool(app["assigned_employee"]) and app["assigned_employee"] == user


def read_only_reason(app: dict) -> str:
    """Why the signed-in employee can't change this file ('' if they can)."""
    if can_work(app):
        return ""
    owner = app["assigned_employee"]
    if not owner:
        return "This file is unassigned. Assign it to yourself to work it."
    return f"Assigned to **{owner}**. Only {owner} or an admin can change this file."
