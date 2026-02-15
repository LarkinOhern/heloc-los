"""Conditions management — add, satisfy, and waive conditions on applications.

Conditions are requirements that must be met before closing or funding.
For example: "Provide proof of homeowners insurance" or "Satisfy outstanding lien."
"""

import streamlit as st

from src.config import STATUS_LABELS
from src.utils.db_helpers import (
    get_all_applications, get_application, get_conditions,
    create_condition, update_condition, add_audit_entry,
)
from src.utils.formatters import fmt_datetime, now_utc


def render():
    st.header("Conditions Management")

    # ── Select Application ───────────────────────────────────────────────
    # Reuse the same review_app_id from session if the employee navigated
    # here from the pipeline or review page.
    all_apps = get_all_applications()
    non_draft = [a for a in all_apps if a["status"] != "DRAFT"]

    if not non_draft:
        st.info("No submitted applications to manage.")
        return

    app_options = {a["application_number"]: a["id"] for a in non_draft}
    app_numbers = list(app_options.keys())

    # Pre-select from session if available
    default_idx = 0
    review_id = st.session_state.get("review_app_id")
    if review_id:
        for i, a in enumerate(non_draft):
            if a["id"] == review_id:
                default_idx = i
                break

    selected_number = st.selectbox("Application", app_numbers, index=default_idx)
    app_id = app_options[selected_number]
    app = get_application(app_id)

    status_label = STATUS_LABELS.get(app["status"], app["status"])
    st.caption(f"Status: **{status_label}**")

    st.divider()

    # ── Existing Conditions ──────────────────────────────────────────────
    conditions = get_conditions(app_id)
    current_user = st.session_state.get("current_user", "")

    open_conds = [c for c in conditions if c["status"] == "OPEN"]
    resolved_conds = [c for c in conditions if c["status"] != "OPEN"]

    # Open conditions — these are actionable
    if open_conds:
        st.write(f"**Open Conditions ({len(open_conds)})**")
        for c in open_conds:
            col1, col2, col3, col4 = st.columns([3, 1.5, 1, 1])
            col1.write(c["description"])
            col2.caption(c["condition_type"].replace("_", " ").title())

            if col3.button("Satisfy", key=f"satisfy_{c['id']}"):
                update_condition(
                    c["id"],
                    status="SATISFIED",
                    resolved_by=current_user,
                    resolved_at=now_utc(),
                )
                add_audit_entry(
                    app_id, "CONDITION_SATISFIED",
                    f"Condition satisfied: {c['description']}", current_user,
                )
                st.rerun()

            if col4.button("Waive", key=f"waive_{c['id']}"):
                update_condition(
                    c["id"],
                    status="WAIVED",
                    resolved_by=current_user,
                    resolved_at=now_utc(),
                )
                add_audit_entry(
                    app_id, "CONDITION_WAIVED",
                    f"Condition waived: {c['description']}", current_user,
                )
                st.rerun()
    else:
        st.success("No open conditions.")

    # Resolved conditions — for reference
    if resolved_conds:
        with st.expander(f"Resolved Conditions ({len(resolved_conds)})"):
            for c in resolved_conds:
                col1, col2, col3 = st.columns([3, 1.5, 2])
                col1.write(c["description"])
                if c["status"] == "SATISFIED":
                    col2.write("Satisfied")
                else:
                    col2.write("Waived")
                col3.caption(f"By {c['resolved_by']} on {fmt_datetime(c['resolved_at'])}")

    st.divider()

    # ── Add New Condition ────────────────────────────────────────────────
    st.write("**Add Condition**")
    with st.form("add_condition"):
        description = st.text_input("Condition Description",
                                     placeholder="e.g., Provide proof of homeowners insurance")
        cond_type = st.selectbox(
            "Condition Type",
            ["PRIOR_TO_CLOSING", "PRIOR_TO_FUNDING"],
            format_func=lambda x: x.replace("_", " ").title(),
        )
        submitted = st.form_submit_button("Add Condition")

    if submitted:
        if not description.strip():
            st.error("Description is required.")
        else:
            create_condition(
                app_id,
                condition_type=cond_type,
                description=description.strip(),
                added_by=current_user,
            )
            add_audit_entry(
                app_id, "CONDITION_ADDED",
                f"Condition added: {description.strip()} ({cond_type})",
                current_user,
            )
            st.rerun()
