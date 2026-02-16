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
    create_underwriting_decision, create_condition,
    create_pricing_lock,
)
from src.config_manager import get_setting
from src.engines.underwriting import UnderwritingInput, run_underwriting
from src.engines.pricing import PricingInput, calculate_pricing
from src.utils.styles import status_badge
from src.documents.generator import generate_decision_letter, generate_closing_documents
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
        f'**{app["application_number"]}** &nbsp; {status_badge(status)}',
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
            # Auto-generate closing documents when moving to CLOSING
            if new_status == "CLOSING":
                filename = generate_closing_documents(app["id"])
                add_audit_entry(
                    app["id"], "DOCUMENT_GENERATED",
                    f"Closing documents generated: {filename}",
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
    """Run underwriting engine and display decision history."""
    current_user = st.session_state.get("current_user", "")

    # ── Run Underwriting Button ──────────────────────────────────────
    # Only enable if the application is in a status where UW makes sense.
    # We check UNDERWRITING specifically but also allow IN_REVIEW since
    # an employee might want to pre-check before formally moving to UW.
    can_run = app["status"] in ("IN_REVIEW", "UNDERWRITING")

    if can_run:
        if st.button("Run Underwriting Engine", type="primary"):
            _execute_underwriting(app, current_user)
            st.rerun()
    elif app["status"] in ("SUBMITTED",):
        st.info("Move the application to **In Review** or **Underwriting** before running the engine.")

    st.divider()

    # ── Decision History ─────────────────────────────────────────────
    decisions = get_underwriting_decisions(app["id"])

    if not decisions:
        st.caption("No underwriting decisions recorded yet.")
        return

    for dec in decisions:
        decision_label = dec["decision"].replace("_", " ").title()
        # Color-code the decision
        if dec["decision"] == "APPROVE":
            st.success(f"**{decision_label}** — {fmt_datetime(dec['decided_at'])}")
        elif dec["decision"] == "DENY":
            st.error(f"**{decision_label}** — {fmt_datetime(dec['decided_at'])}")
        else:
            st.warning(f"**{decision_label}** — {fmt_datetime(dec['decided_at'])}")

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

        st.caption(f"Decided by: {dec['decided_by']}")
        st.divider()


def _execute_underwriting(app: dict, current_user: str):
    """Gather input data, run the engine, save results, update status."""
    borrowers = get_borrowers(app["id"])

    # Collect credit scores from all borrowers
    credit_scores = [b["credit_score"] for b in borrowers]

    # Sum income across all borrowers
    total_income = 0.0
    for b in borrowers:
        jobs = get_employment(b["id"])
        total_income += sum(j["monthly_income"] for j in jobs)

    # Sum existing debts (primary borrower only, per our data model)
    primary = next((b for b in borrowers if b["is_primary"]), None)
    total_debts = 0.0
    if primary:
        debts = get_debts(primary["id"])
        total_debts = sum(d["monthly_payment"] for d in debts)

    # Build engine input and run
    inp = UnderwritingInput(
        property_value=app["property_value"],
        existing_mortgage_balance=app["existing_mortgage_balance"],
        heloc_amount_requested=app["heloc_amount_requested"],
        credit_scores=credit_scores,
        total_monthly_income=total_income,
        total_monthly_debts=total_debts,
    )
    result = run_underwriting(inp)

    # Save the decision to the database
    all_reasons = result.hard_fails + result.warnings
    create_underwriting_decision(
        app["id"],
        decision=result.decision,
        ltv=result.ltv,
        cltv=result.cltv,
        dti=result.dti,
        highest_credit_score=result.highest_credit_score,
        reasons=json.dumps(all_reasons),
        conditions=json.dumps(result.conditions),
        decided_by=current_user,
    )

    # Auto-create condition records for APPROVE_WITH_CONDITIONS
    if result.decision == "APPROVE_WITH_CONDITIONS":
        for cond_text in result.conditions:
            create_condition(
                app["id"],
                condition_type="PRIOR_TO_CLOSING",
                description=cond_text,
                added_by="UW_ENGINE",
            )

    # Map engine decision to application status
    status_map = {
        "APPROVE": "APPROVED",
        "APPROVE_WITH_CONDITIONS": "APPROVED_WITH_CONDITIONS",
        "DENY": "DENIED",
    }
    new_status = status_map.get(result.decision, app["status"])
    old_status = app["status"]

    update_application(app["id"], status=new_status)
    add_audit_entry(
        app["id"], "UNDERWRITING_DECISION",
        f"Engine decision: {result.decision}. Status changed from {old_status} to {new_status}.",
        current_user,
    )

    # Auto-generate the approval or denial letter
    filename = generate_decision_letter(app["id"])
    add_audit_entry(
        app["id"], "DOCUMENT_GENERATED",
        f"Decision letter generated: {filename}",
        current_user,
    )


# ── Tab: Pricing ─────────────────────────────────────────────────────────────

def _match_pricing_tiers(lock: dict) -> tuple[str, str, str]:
    """Match stored adjustment values back to current tier definitions.

    Returns (fico_tier, ltv_tier, amount_tier) labels for display.
    """
    # FICO — match from credit_tiers (has labels)
    fico_tier = ""
    credit_tiers = get_setting("credit_tiers")
    for tier in credit_tiers:
        if abs(tier["rate_adjustment"] - lock["fico_adjustment"]) < 0.001:
            fico_tier = f"{tier['label']} ({tier['min_score']}-{tier['max_score']})"
            break

    # LTV
    ltv_tier = ""
    ltv_adjustments = get_setting("ltv_adjustments")
    for tier in ltv_adjustments:
        if abs(tier["adjustment"] - lock["ltv_adjustment"]) < 0.001:
            ltv_tier = f"CLTV <= {tier['max_ltv']:.0%}"
            break

    # Amount
    amount_tier = ""
    amount_adjustments = get_setting("amount_adjustments")
    for tier in amount_adjustments:
        if abs(tier["adjustment"] - lock["amount_adjustment"]) < 0.001:
            amount_tier = f">= ${tier['min_amount']:,.0f}"
            break

    return fico_tier, ltv_tier, amount_tier


def _tab_pricing(app: dict):
    """Calculate pricing, display rate breakdown, and manage rate locks."""
    current_user = st.session_state.get("current_user", "")
    locks = get_pricing_locks(app["id"])

    # ── Calculate Pricing Button ─────────────────────────────────────
    # Pricing requires a UW decision first so we have the credit score
    # and CLTV. Check if there's at least one decision on file.
    decisions = get_underwriting_decisions(app["id"])
    can_price = bool(decisions) and app["status"] not in ("DRAFT", "SUBMITTED", "DENIED", "WITHDRAWN")

    if can_price:
        if st.button("Calculate Pricing", type="primary"):
            _execute_pricing(app, decisions[0], current_user)
            st.rerun()
    elif not decisions:
        st.info("Run underwriting first — pricing needs the credit score and CLTV from the UW decision.")

    st.divider()

    # ── Pricing History ──────────────────────────────────────────────
    if not locks:
        st.caption("No pricing calculations yet.")
        return

    for lock in locks:
        st.write(f"### Rate: {fmt_rate(lock['final_rate'])}")

        # Look up which tier each adjustment came from so the employee
        # can explain exactly why the borrower got this rate.
        fico_tier, ltv_tier, amount_tier = _match_pricing_tiers(lock)

        # Rate breakdown table — shows every component with tier context.
        col1, col2, col3 = st.columns([2, 1.5, 2])
        col1.write("**Rate Component**")
        col2.write("**Value**")
        col3.write("**Tier Matched**")

        components = [
            ("Prime Rate", f"+{fmt_rate(lock['prime_rate'])}", ""),
            ("Base Margin", f"+{fmt_rate(lock['margin'])}", ""),
            ("FICO Adjustment", f"{lock['fico_adjustment']:+.3f}%", fico_tier),
            ("LTV Adjustment", f"{lock['ltv_adjustment']:+.3f}%", ltv_tier),
            ("Amount Adjustment", f"{lock['amount_adjustment']:+.3f}%", amount_tier),
            ("Autopay Discount",
             f"-{fmt_rate(lock['autopay_discount'])}" if lock['autopay_discount'] else "N/A",
             "Enrolled" if lock['autopay_discount'] else "Not enrolled"),
        ]
        for label, value, tier in components:
            c1, c2, c3 = st.columns([2, 1.5, 2])
            c1.write(label)
            c2.write(value)
            c3.write(tier)

        st.divider()
        col1, col2 = st.columns(2)
        col1.metric("Final Rate", fmt_rate(lock["final_rate"]))
        col2.metric("Est. Monthly Payment (IO)", fmt_currency(lock["monthly_payment"]))

        # ── Rate Lock ────────────────────────────────────────────────
        if lock["rate_locked"]:
            # Show lock status with countdown
            from datetime import datetime
            lock_exp = datetime.fromisoformat(lock["lock_expiration"])
            now_dt = datetime.utcnow()
            days_remaining = (lock_exp - now_dt).days

            if days_remaining > 0:
                st.success(
                    f"Rate locked on {fmt_date(lock['lock_date'])} — "
                    f"**{days_remaining} days remaining** "
                    f"(expires {fmt_date(lock['lock_expiration'])})"
                )
            else:
                st.error(
                    f"Rate lock **expired** on {fmt_date(lock['lock_expiration'])}. "
                    f"Re-calculate pricing and lock a new rate."
                )
        else:
            if st.button("Lock This Rate", key=f"lock_{lock['id']}"):
                _lock_rate(app, lock, current_user)
                st.rerun()

        st.divider()


def _execute_pricing(app: dict, latest_decision: dict, current_user: str):
    """Run the pricing engine using data from the latest UW decision."""
    pv = app["property_value"]
    cltv = latest_decision["cltv"] if latest_decision["cltv"] > 0 else (
        (app["existing_mortgage_balance"] + app["heloc_amount_requested"]) / pv if pv > 0 else 0
    )

    inp = PricingInput(
        highest_credit_score=latest_decision["highest_credit_score"],
        cltv=cltv,
        heloc_amount=app["heloc_amount_requested"],
        autopay_enrolled=bool(app["autopay_enrolled"]),
    )
    result = calculate_pricing(inp)

    create_pricing_lock(
        app["id"],
        prime_rate=result.prime_rate,
        margin=result.margin,
        fico_adjustment=result.fico_adjustment,
        ltv_adjustment=result.ltv_adjustment,
        amount_adjustment=result.amount_adjustment,
        autopay_discount=result.autopay_discount,
        final_rate=result.final_rate,
        monthly_payment=result.monthly_payment,
        rate_locked=False,
        locked_by=current_user,
    )
    add_audit_entry(
        app["id"], "PRICING_CALCULATED",
        f"Rate calculated: {result.final_rate:.3f}% "
        f"(payment: ${result.monthly_payment:,.2f}/mo)",
        current_user,
    )


def _lock_rate(app: dict, lock: dict, current_user: str):
    """Lock the rate with a 60-day expiration."""
    from datetime import datetime, timedelta
    from src.config import RATE_LOCK_DAYS
    from src.database import get_connection

    now_str = now_utc()
    expiration = (datetime.utcnow() + timedelta(days=RATE_LOCK_DAYS)).isoformat()

    # Update the pricing_locks row directly
    conn = get_connection()
    conn.execute(
        "UPDATE pricing_locks SET rate_locked=1, lock_date=?, lock_expiration=?, locked_by=? WHERE id=?",
        (now_str, expiration, current_user, lock["id"]),
    )
    conn.commit()
    conn.close()

    add_audit_entry(
        app["id"], "RATE_LOCKED",
        f"Rate of {lock['final_rate']:.3f}% locked for {RATE_LOCK_DAYS} days (expires {expiration[:10]})",
        current_user,
    )


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
        import os
        from src.documents.generator import OUTPUT_DIR
        for doc in gen_docs:
            col1, col2, col3 = st.columns([3, 2, 1])
            col1.write(doc["doc_type"].replace("_", " ").title())
            col2.caption(fmt_datetime(doc["generated_at"]))
            filepath = os.path.join(OUTPUT_DIR, doc["filename"])
            if os.path.exists(filepath):
                with open(filepath, "rb") as f:
                    col3.download_button(
                        "Download",
                        data=f.read(),
                        file_name=doc["filename"],
                        mime="application/pdf",
                        key=f"emp_dl_{doc['id']}",
                    )
            else:
                col3.caption("File not found")
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
