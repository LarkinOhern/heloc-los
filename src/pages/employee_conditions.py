"""Conditions management — add, satisfy, and waive conditions on applications.

Conditions are requirements that must be met before closing or funding.
For example: "Provide proof of homeowners insurance" or "Satisfy outstanding lien."

Three kinds:
- Prior to closing / prior to funding: borrower-facing, may request a document.
- Internal review: created from underwriting-engine warnings. The officer
  clears them; borrowers never see them.
"""

import streamlit as st

from src.config import STATUS_LABELS, REQUIRED_DOCUMENTS
from src.utils.db_helpers import (
    get_all_applications, get_application, get_conditions, get_documents,
    create_condition, update_condition, add_audit_entry,
)
from src.utils.formatters import fmt_datetime, now_utc, md_escape
from src.utils.permissions import can_work, read_only_reason

CONDITION_TYPE_LABELS = {
    "PRIOR_TO_CLOSING": "Prior to closing",
    "PRIOR_TO_FUNDING": "Prior to funding",
    "INTERNAL_REVIEW": "Internal review",
}
DOC_LABELS = {d["type"]: d["label"] for d in REQUIRED_DOCUMENTS}
MIN_WAIVER_REASON = 15


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
    st.caption(f"Status: **{status_label}** · Assigned to: **{app['assigned_employee'] or 'unassigned'}**")

    # Only the assigned officer (or an admin) may change conditions (C-02).
    editable = can_work(app)
    if not editable:
        st.info(read_only_reason(app))

    st.divider()

    # ── Existing Conditions ──────────────────────────────────────────────
    conditions = get_conditions(app_id)
    docs = get_documents(app_id)
    current_user = st.session_state.get("current_user", "")

    open_conds = [c for c in conditions if c["status"] == "OPEN"]
    resolved_conds = [c for c in conditions if c["status"] != "OPEN"]

    # Open conditions — these are actionable
    if open_conds:
        st.write(f"**Open Conditions ({len(open_conds)})**")
        for c in open_conds:
            _render_open_condition(app_id, c, docs, editable, current_user)
    else:
        st.success("No open conditions.")

    # Resolved conditions — for reference
    if resolved_conds:
        with st.expander(f"Resolved Conditions ({len(resolved_conds)})"):
            for c in resolved_conds:
                col1, col2, col3 = st.columns([3, 1.5, 2])
                col1.write(md_escape(c["description"]))
                col2.write({"SATISFIED": "Satisfied", "WAIVED": "Waived"}.get(c["status"], c["status"]))
                col3.caption(f"By {c['resolved_by']} on {fmt_datetime(c['resolved_at'])}")
                if c.get("resolution_note"):
                    col1.caption(f"Note: {md_escape(c['resolution_note'])}")

    if not editable:
        return

    st.divider()

    # ── Add New Condition ────────────────────────────────────────────────
    st.write("**Add Condition**")
    with st.form("add_condition", clear_on_submit=True):
        description = st.text_input("Condition Description",
                                     placeholder="e.g., Provide proof of homeowners insurance")
        col1, col2 = st.columns(2)
        cond_type = col1.selectbox(
            "Condition Type",
            ["PRIOR_TO_CLOSING", "PRIOR_TO_FUNDING"],
            format_func=CONDITION_TYPE_LABELS.get,
        )
        doc_type = col2.selectbox(
            "Document that satisfies it (optional)",
            [""] + list(DOC_LABELS),
            format_func=lambda x: DOC_LABELS.get(x, "None"),
            help="The borrower sees which upload is requested, and you see when it arrives.",
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
                doc_type=doc_type or None,
            )
            add_audit_entry(
                app_id, "CONDITION_ADDED",
                f"Condition added: {description.strip()} ({cond_type})"
                + (f", requests {DOC_LABELS[doc_type]}" if doc_type else ""),
                current_user,
            )
            st.rerun()


def _render_open_condition(app_id, c, docs, editable, current_user):
    internal = c["condition_type"] == "INTERNAL_REVIEW"
    col1, col2, col3, col4 = st.columns([3, 1.5, 1, 1])
    col1.write(md_escape(c["description"]))
    col2.caption(CONDITION_TYPE_LABELS.get(c["condition_type"], c["condition_type"]))

    # Document linkage (C-06): show whether the requested upload has arrived.
    if c.get("doc_type"):
        got = [d for d in docs if d["doc_type"] == c["doc_type"]]
        label = DOC_LABELS.get(c["doc_type"], c["doc_type"])
        if got:
            latest = got[-1]
            col1.success(f"Document received: {latest['filename']} "
                         f"({fmt_datetime(latest['uploaded_at'])})")
        else:
            col1.caption(f"Waiting for borrower to upload: {label}")

    if not editable:
        return

    if col3.button("Mark reviewed" if internal else "Satisfy", key=f"satisfy_{c['id']}"):
        update_condition(c["id"], status="SATISFIED",
                         resolved_by=current_user, resolved_at=now_utc())
        add_audit_entry(
            app_id, "CONDITION_SATISFIED",
            f"Condition {'reviewed' if internal else 'satisfied'}: {c['description']}",
            current_user,
        )
        st.rerun()

    # Waiving needs a written reason (C-04). Internal review items are
    # cleared with "Mark reviewed" instead.
    if internal:
        return
    waiving_key = f"waiving_{c['id']}"
    if col4.button("Waive", key=f"waive_{c['id']}"):
        st.session_state[waiving_key] = True
    if st.session_state.get(waiving_key):
        with st.container(border=True):
            reason = st.text_input(
                "Reason for waiving (kept in the audit trail)",
                key=f"waive_reason_{c['id']}",
                placeholder="e.g., Appraisal waived: AVM value within 5% of stated value",
            )
            b1, b2 = st.columns([1, 4])
            if b1.button("Confirm waiver", key=f"confirm_waive_{c['id']}"):
                if len(reason.strip()) < MIN_WAIVER_REASON:
                    st.error(f"Enter a reason of at least {MIN_WAIVER_REASON} characters "
                             f"so a reviewer can tell why this was waived.")
                else:
                    update_condition(c["id"], status="WAIVED", resolved_by=current_user,
                                     resolved_at=now_utc(), resolution_note=reason.strip())
                    add_audit_entry(
                        app_id, "CONDITION_WAIVED",
                        f"Condition waived: {c['description']}. Reason: {reason.strip()}",
                        current_user,
                    )
                    st.session_state.pop(waiving_key, None)
                    st.rerun()
            if b2.button("Cancel", key=f"cancel_waive_{c['id']}"):
                st.session_state.pop(waiving_key, None)
                st.rerun()
