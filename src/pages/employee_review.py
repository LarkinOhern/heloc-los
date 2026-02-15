"""Full application review page with tabs.

Tabs: Summary | Income | Assets & Debts | Underwriting | Pricing | Documents | Audit
Also handles status changes with transition validation and employee assignment.
"""

import json
import streamlit as st

from src.config import (
    STATUS_LABELS, STATUS_COLORS, VALID_TRANSITIONS,
    PROPERTY_TYPE_LABELS, REQUIRED_DOCUMENTS,
)
from src.utils.db_helpers import (
    get_application, get_all_applications, get_borrowers,
    get_employment, get_assets, get_debts,
    get_underwriting_decisions, get_pricing_locks,
    get_documents, get_generated_documents,
    get_conditions, get_audit_log,
    update_application, add_audit_entry,
)
from src.utils.formatters import fmt_currency, fmt_date, fmt_datetime, fmt_percent, fmt_rate, now_utc


def render():
    st.header("Application Review")

    # ── Select Application ───────────────────────────────────────────────
    # If the pipeline page set review_app_id, use that. Otherwise show a
    # dropdown so employees can also navigate here directly.
    app_id = st.session_state.get("review_app_id")

    all_apps = get_all_applications()
    non_draft = [a for a in all_apps if a["status"] != "DRAFT"]

    if not non_draft:
        st.info("No submitted applications to review.")
        return

    # Build lookup for the selectbox
    app_options = {a["application_number"]: a["id"] for a in non_draft}
    app_numbers = list(app_options.keys())

    # Find the index of the pre-selected app (from pipeline click)
    default_idx = 0
    if app_id:
        for i, a in enumerate(non_draft):
            if a["id"] == app_id:
                default_idx = i
                break

    selected_number = st.selectbox(
        "Application", app_numbers, index=default_idx,
    )
    app_id = app_options[selected_number]
    st.session_state["review_app_id"] = app_id

    app = get_application(app_id)
    if not app:
        st.error("Application not found.")
        return

    # ── Status Bar & Actions ─────────────────────────────────────────────
    # Show current status prominently, with assignment and status change controls.
    _render_status_bar(app)

    st.divider()

    # ── Tabbed Content ───────────────────────────────────────────────────
    tabs = st.tabs([
        "Summary", "Income", "Assets & Debts",
        "Underwriting", "Pricing", "Documents", "Audit",
    ])

    with tabs[0]:
        _tab_summary(app)
    with tabs[1]:
        _tab_income(app)
    with tabs[2]:
        _tab_assets_debts(app)
    with tabs[3]:
        _tab_underwriting(app)
    with tabs[4]:
        _tab_pricing(app)
    with tabs[5]:
        _tab_documents(app)
    with tabs[6]:
        _tab_audit(app)


# ── Status Bar ───────────────────────────────────────────────────────────────

def _render_status_bar(app: dict):
    """Status badge, assignment, and status change controls."""
    status = app["status"]
    color = STATUS_COLORS.get(status, "#9e9e9e")
    label = STATUS_LABELS.get(status, status)
    current_user = st.session_state.get("current_user", "")

    col1, col2, col3 = st.columns([2, 2, 2])

    # Status badge
    col1.markdown(
        f'**{app["application_number"]}** &nbsp; '
        f'<span style="background-color:{color}; color:white; padding:4px 12px; '
        f'border-radius:12px; font-weight:bold;">{label}</span>',
        unsafe_allow_html=True,
    )

    # Assignment
    assigned = app["assigned_employee"]
    if assigned:
        col2.write(f"Assigned to: **{assigned}**")
    else:
        if col2.button("Assign to Me"):
            update_application(app["id"], assigned_employee=current_user)
            add_audit_entry(
                app["id"], "ASSIGNED",
                f"Assigned to {current_user}", current_user,
            )
            st.rerun()

    # Status change — only show valid transitions
    allowed = VALID_TRANSITIONS.get(status, [])
    if allowed:
        new_status = col3.selectbox(
            "Change Status",
            [""] + allowed,
            format_func=lambda x: STATUS_LABELS.get(x, "Select...") if x else "Select...",
            key="status_change",
        )
        if new_status and col3.button("Update Status"):
            update_application(app["id"], status=new_status)
            add_audit_entry(
                app["id"], "STATUS_CHANGE",
                f"Status changed from {status} to {new_status}",
                current_user,
            )
            st.rerun()


# ── Tab: Summary ─────────────────────────────────────────────────────────────

def _tab_summary(app: dict):
    """Property info, borrower overview, and key ratios at a glance."""
    borrowers = get_borrowers(app["id"])
    primary = next((b for b in borrowers if b["is_primary"]), None)
    coborrower = next((b for b in borrowers if not b["is_primary"]), None)

    # Property
    st.write("**Property**")
    col1, col2 = st.columns(2)
    col1.write(f"{app['property_address']}, {app['property_city']}, "
               f"{app['property_state']} {app['property_zip']}")
    col2.write(f"Type: {PROPERTY_TYPE_LABELS.get(app['property_type'], app['property_type'])}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Property Value", fmt_currency(app["property_value"]))
    col2.metric("Existing Mortgage", fmt_currency(app["existing_mortgage_balance"]))
    col3.metric("HELOC Requested", fmt_currency(app["heloc_amount_requested"]))

    # Quick LTV/CLTV calc for the summary
    pv = app["property_value"]
    if pv > 0:
        ltv = app["existing_mortgage_balance"] / pv
        cltv = (app["existing_mortgage_balance"] + app["heloc_amount_requested"]) / pv
        col4.metric("CLTV", fmt_percent(cltv))

    st.write(f"**Purpose:** {app['heloc_purpose'] or '—'}")
    st.write(f"**Autopay:** {'Yes' if app['autopay_enrolled'] else 'No'}")
    st.write(f"**E-Consent:** {'Yes' if app['econsent_given'] else 'No'} "
             f"({fmt_date(app['econsent_date'])})")

    st.divider()

    # Borrowers
    if primary:
        st.write("**Primary Borrower**")
        col1, col2, col3, col4 = st.columns(4)
        col1.write(f"{primary['first_name']} {primary['last_name']}")
        col2.write(f"Score: {primary['credit_score']} (self-reported)")
        col3.write(f"Email: {primary['email']}")
        col4.write(f"SSN: ***-**-{primary['ssn_last4']}")

    if coborrower:
        st.write("**Co-Borrower**")
        col1, col2, col3, col4 = st.columns(4)
        col1.write(f"{coborrower['first_name']} {coborrower['last_name']}")
        col2.write(f"Score: {coborrower['credit_score']} (self-reported)")
        col3.write(f"Email: {coborrower['email']}")
        col4.write(f"SSN: ***-**-{coborrower['ssn_last4']}")


# ── Tab: Income ──────────────────────────────────────────────────────────────

def _tab_income(app: dict):
    """Employment and income details for all borrowers."""
    borrowers = get_borrowers(app["id"])
    grand_total = 0.0

    for b in borrowers:
        label = "Primary Borrower" if b["is_primary"] else "Co-Borrower"
        st.write(f"**{label}: {b['first_name']} {b['last_name']}**")

        jobs = get_employment(b["id"])
        if jobs:
            for job in jobs:
                col1, col2, col3, col4 = st.columns(4)
                col1.write(job["employer_name"])
                col2.write(job["position"])
                col3.write(job["income_type"].replace("_", " ").title())
                col4.write(f"{fmt_currency(job['monthly_income'])}/mo")
                grand_total += job["monthly_income"]
        else:
            st.caption("No income sources recorded.")
        st.divider()

    st.metric("Total Monthly Income (All Borrowers)", fmt_currency(grand_total))


# ── Tab: Assets & Debts ─────────────────────────────────────────────────────

def _tab_assets_debts(app: dict):
    """Assets and debt obligations."""
    borrowers = get_borrowers(app["id"])
    primary = next((b for b in borrowers if b["is_primary"]), None)
    if not primary:
        st.warning("No primary borrower found.")
        return

    # Assets
    st.write("**Assets**")
    assets = get_assets(primary["id"])
    if assets:
        for a in assets:
            col1, col2, col3 = st.columns([2, 2, 2])
            col1.write(a["institution"])
            col2.write(a["account_type"].title())
            col3.write(fmt_currency(a["balance"]))
        st.metric("Total Assets", fmt_currency(sum(a["balance"] for a in assets)))
    else:
        st.caption("No assets recorded.")

    st.divider()

    # Debts
    st.write("**Monthly Obligations**")
    debts = get_debts(primary["id"])
    if debts:
        for d in debts:
            col1, col2, col3, col4 = st.columns(4)
            col1.write(d["creditor"])
            col2.write(d["debt_type"].replace("_", " ").title())
            col3.write(f"{fmt_currency(d['monthly_payment'])}/mo")
            col4.write(f"Bal: {fmt_currency(d['balance'])}")
        st.metric("Total Monthly Debts", fmt_currency(sum(d["monthly_payment"] for d in debts)))
    else:
        st.caption("No debts recorded.")


# ── Tab: Underwriting ────────────────────────────────────────────────────────

def _tab_underwriting(app: dict):
    """Underwriting decisions history. The actual engine is wired in Phase 4."""
    decisions = get_underwriting_decisions(app["id"])

    if app["status"] in ("SUBMITTED", "IN_REVIEW", "UNDERWRITING"):
        st.info("Underwriting engine will be available in Phase 4. "
                "Use status changes to simulate for now.")

    if not decisions:
        st.caption("No underwriting decisions recorded yet.")
        return

    for dec in decisions:
        decision_label = dec["decision"].replace("_", " ").title()
        st.write(f"**Decision: {decision_label}** — {fmt_datetime(dec['decided_at'])}")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("LTV", fmt_percent(dec["ltv"]))
        col2.metric("CLTV", fmt_percent(dec["cltv"]))
        col3.metric("DTI", fmt_percent(dec["dti"]))
        col4.metric("Credit Score", dec["highest_credit_score"])

        reasons = json.loads(dec["reasons"]) if dec["reasons"] else []
        if reasons:
            st.write("**Reasons:**")
            for r in reasons:
                st.write(f"- {r}")

        conditions = json.loads(dec["conditions"]) if dec["conditions"] else []
        if conditions:
            st.write("**Conditions:**")
            for c in conditions:
                st.write(f"- {c}")

        st.divider()


# ── Tab: Pricing ─────────────────────────────────────────────────────────────

def _tab_pricing(app: dict):
    """Pricing/rate lock history. The pricing engine is wired in Phase 5."""
    locks = get_pricing_locks(app["id"])

    st.info("Pricing engine will be available in Phase 5.")

    if not locks:
        st.caption("No pricing calculations yet.")
        return

    for lock in locks:
        st.write(f"**Final Rate: {fmt_rate(lock['final_rate'])}**")
        col1, col2, col3 = st.columns(3)
        col1.write(f"Prime: {fmt_rate(lock['prime_rate'])}")
        col2.write(f"Margin: {fmt_rate(lock['margin'])}")
        col3.write(f"Monthly Payment: {fmt_currency(lock['monthly_payment'])}")

        if lock["rate_locked"]:
            st.success(f"Rate locked on {fmt_date(lock['lock_date'])} — "
                       f"expires {fmt_date(lock['lock_expiration'])}")
        st.divider()


# ── Tab: Documents ───────────────────────────────────────────────────────────

def _tab_documents(app: dict):
    """Uploaded and generated documents."""
    # Uploaded
    st.write("**Uploaded Documents**")
    docs = get_documents(app["id"])
    uploaded_types = {d["doc_type"] for d in docs}

    for req in REQUIRED_DOCUMENTS:
        col1, col2 = st.columns([3, 3])
        col1.write(req["label"])
        if req["type"] in uploaded_types:
            doc = next(d for d in docs if d["doc_type"] == req["type"])
            col2.write(f"{doc['filename']} ({fmt_datetime(doc['uploaded_at'])})")
        else:
            col2.caption("Not uploaded")

    st.divider()

    # Generated
    st.write("**Generated Documents**")
    gen_docs = get_generated_documents(app["id"])
    if gen_docs:
        for doc in gen_docs:
            col1, col2 = st.columns([3, 3])
            col1.write(doc["doc_type"].replace("_", " ").title())
            col2.write(f"{doc['filename']} ({fmt_datetime(doc['generated_at'])})")
    else:
        st.caption("No generated documents yet.")


# ── Tab: Audit ───────────────────────────────────────────────────────────────

def _tab_audit(app: dict):
    """Full audit trail for this application."""
    entries = get_audit_log(app["id"])
    if not entries:
        st.caption("No audit entries.")
        return

    for entry in entries:
        col1, col2, col3 = st.columns([2, 2, 4])
        col1.caption(fmt_datetime(entry["performed_at"]))
        col2.write(f"**{entry['action'].replace('_', ' ').title()}**")
        col3.write(entry["details"])
        if entry["performed_by"]:
            col3.caption(f"By: {entry['performed_by']}")
