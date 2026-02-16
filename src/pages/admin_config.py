"""Admin configuration page — read-only display of all config values and audit log.

This page serves two purposes:
1. Let the team see exactly what rules and thresholds are configured (useful
   for comparing against vendor configurations during the RFP process)
2. Provide a system-wide audit log view across all applications
"""

import pandas as pd
import streamlit as st

from src.config import (
    LENDER_NAME, LENDER_ADDRESS, LENDER_NMLS, LENDER_PHONE,
    MIN_CREDIT_SCORE, MAX_CLTV, MAX_DTI,
    MIN_PROPERTY_VALUE, MIN_HELOC_AMOUNT, MAX_HELOC_AMOUNT,
    PRIME_RATE, BASE_MARGIN, AUTOPAY_DISCOUNT, RATE_LOCK_DAYS,
    RATE_FLOOR, RATE_CEILING,
    FICO_ADJUSTMENTS, LTV_ADJUSTMENTS, AMOUNT_ADJUSTMENTS,
    CREDIT_TIERS, STATUSES, STATUS_LABELS, VALID_TRANSITIONS,
    REQUIRED_DOCUMENTS, EMPLOYEES,
)
from src.utils.db_helpers import get_full_audit_log
from src.utils.formatters import fmt_datetime


def render():
    st.header("Admin Configuration")
    st.caption("Read-only view of system configuration. Changes require code updates.")

    tabs = st.tabs(["Underwriting", "Pricing", "Workflow", "Lender Info", "Audit Log"])

    with tabs[0]:
        _tab_underwriting()
    with tabs[1]:
        _tab_pricing()
    with tabs[2]:
        _tab_workflow()
    with tabs[3]:
        _tab_lender()
    with tabs[4]:
        _tab_audit()


def _tab_underwriting():
    st.subheader("Underwriting Rules")

    col1, col2, col3 = st.columns(3)
    col1.metric("Min Credit Score", MIN_CREDIT_SCORE)
    col2.metric("Max CLTV", f"{MAX_CLTV:.0%}")
    col3.metric("Max DTI", f"{MAX_DTI:.0%}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Min Property Value", f"${MIN_PROPERTY_VALUE:,}")
    col2.metric("Min HELOC Amount", f"${MIN_HELOC_AMOUNT:,}")
    col3.metric("Max HELOC Amount", f"${MAX_HELOC_AMOUNT:,}")

    st.divider()
    st.write("**Credit Tiers**")
    for tier in CREDIT_TIERS:
        st.write(f"- {tier['label']}: {tier['min_score']} - {tier['max_score']}")

    st.divider()
    st.write("**Required Documents**")
    for doc in REQUIRED_DOCUMENTS:
        st.write(f"- {doc['label']} (`{doc['type']}`)")


def _tab_pricing():
    st.subheader("Pricing Configuration")

    col1, col2, col3 = st.columns(3)
    col1.metric("Prime Rate", f"{PRIME_RATE:.2f}%")
    col2.metric("Base Margin", f"{BASE_MARGIN:.2f}%")
    col3.metric("Autopay Discount", f"{AUTOPAY_DISCOUNT:.2f}%")

    col1, col2, col3 = st.columns(3)
    col1.metric("Rate Floor", f"{RATE_FLOOR:.2f}%")
    col2.metric("Rate Ceiling", f"{RATE_CEILING:.2f}%")
    col3.metric("Rate Lock Days", RATE_LOCK_DAYS)

    st.divider()
    st.write("**FICO Adjustments**")
    for tier in FICO_ADJUSTMENTS:
        st.write(f"- Score >= {tier['min_score']}: {tier['adjustment']:+.2f}%")

    st.write("**LTV Adjustments**")
    for tier in LTV_ADJUSTMENTS:
        st.write(f"- CLTV <= {tier['max_ltv']:.0%}: {tier['adjustment']:+.2f}%")

    st.write("**Amount Adjustments**")
    for tier in AMOUNT_ADJUSTMENTS:
        st.write(f"- Amount >= ${tier['min_amount']:,}: {tier['adjustment']:+.2f}%")


def _tab_workflow():
    st.subheader("Workflow Configuration")

    st.write("**Statuses**")
    for s in STATUSES:
        st.write(f"- {STATUS_LABELS.get(s, s)} (`{s}`)")

    st.divider()
    st.write("**Valid Transitions**")
    for from_status, targets in VALID_TRANSITIONS.items():
        if targets:
            target_labels = ", ".join(STATUS_LABELS.get(t, t) for t in targets)
            st.write(f"- **{STATUS_LABELS.get(from_status, from_status)}** -> {target_labels}")
        else:
            st.write(f"- **{STATUS_LABELS.get(from_status, from_status)}** -> (terminal)")

    st.divider()
    st.write("**Employees**")
    for emp in EMPLOYEES:
        st.write(f"- {emp['display_name']} (`{emp['username']}`) - {emp['role']}")


def _tab_lender():
    st.subheader("Lender Information")
    st.write(f"**Name:** {LENDER_NAME}")
    st.write(f"**Address:** {LENDER_ADDRESS}")
    st.write(f"**NMLS:** {LENDER_NMLS}")
    st.write(f"**Phone:** {LENDER_PHONE}")


def _tab_audit():
    st.subheader("System Audit Log")
    entries = get_full_audit_log()

    if not entries:
        st.info("No audit entries yet.")
        return

    st.caption(f"{len(entries)} total entries")

    # Filter
    actions = sorted(set(e["action"] for e in entries))
    action_filter = st.multiselect("Filter by Action", actions)

    filtered = entries
    if action_filter:
        filtered = [e for e in entries if e["action"] in action_filter]

    # Display as a dataframe for easy scanning
    rows = []
    for e in filtered[:200]:  # Limit to 200 for performance
        rows.append({
            "Time": fmt_datetime(e["performed_at"]),
            "Application": e.get("application_number", ""),
            "Action": e["action"].replace("_", " ").title(),
            "Details": e["details"],
            "By": e["performed_by"],
        })

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("No entries match the filter.")
