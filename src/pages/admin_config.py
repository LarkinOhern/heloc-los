"""Admin configuration page — editable UW guidelines and pricing tables.

The Underwriting and Pricing tabs have interactive forms backed by the
settings DB table. Changes take effect immediately for new UW/pricing runs.
Workflow and Lender Info remain read-only (code changes required).
"""

import pandas as pd
import streamlit as st

from src.config import (
    LENDER_NAME, LENDER_ADDRESS, LENDER_NMLS, LENDER_PHONE,
    STATUSES, STATUS_LABELS, VALID_TRANSITIONS, EMPLOYEES,
)
from src.config_manager import get_setting, set_setting, reset_all_settings
from src.utils.db_helpers import get_full_audit_log
from src.utils.formatters import fmt_datetime


def render():
    st.header("Admin Configuration")

    tabs = st.tabs([
        "Underwriting Guidelines",
        "Pricing Configuration",
        "Workflow",
        "Lender Info",
        "Audit Log",
    ])

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

    # Reset all button at the bottom
    st.divider()
    if st.button("Reset All Settings to Defaults", type="secondary"):
        reset_all_settings()
        st.success("All settings reset to defaults.")
        st.rerun()


# ── Underwriting Guidelines ──────────────────────────────────────────────────

def _tab_underwriting():
    st.subheader("Underwriting Guidelines")
    st.caption("Changes take effect on the next underwriting run.")

    # ── Core Thresholds ──────────────────────────────────────────────
    st.write("**Core Thresholds**")
    with st.form("uw_thresholds"):
        col1, col2, col3 = st.columns(3)
        min_credit = col1.number_input(
            "Minimum Credit Score",
            min_value=300, max_value=850, step=10,
            value=int(get_setting("min_credit_score")),
            help="Borrowers below this score are automatically denied.",
        )
        max_cltv = col2.number_input(
            "Maximum CLTV (%)",
            min_value=50.0, max_value=100.0, step=5.0,
            value=float(get_setting("max_cltv") * 100),
            help="Combined loan-to-value ceiling. 80% is standard.",
        )
        max_dti = col3.number_input(
            "Maximum DTI (%)",
            min_value=20.0, max_value=60.0, step=1.0,
            value=float(get_setting("max_dti") * 100),
            help="Debt-to-income ceiling. 43% is the qualified mortgage standard.",
        )

        st.divider()

        col1, col2, col3 = st.columns(3)
        min_prop = col1.number_input(
            "Min Property Value ($)",
            min_value=0, step=10000,
            value=int(get_setting("min_property_value")),
        )
        min_heloc = col2.number_input(
            "Min HELOC Amount ($)",
            min_value=0, step=5000,
            value=int(get_setting("min_heloc_amount")),
        )
        max_heloc = col3.number_input(
            "Max HELOC Amount ($)",
            min_value=0, step=50000,
            value=int(get_setting("max_heloc_amount")),
        )

        save_thresholds = st.form_submit_button("Save Thresholds", type="primary")

    if save_thresholds:
        set_setting("min_credit_score", int(min_credit))
        set_setting("max_cltv", max_cltv / 100)
        set_setting("max_dti", max_dti / 100)
        set_setting("min_property_value", int(min_prop))
        set_setting("min_heloc_amount", int(min_heloc))
        set_setting("max_heloc_amount", int(max_heloc))
        st.success("Underwriting thresholds saved.")
        st.rerun()

    # ── Credit Tiers ─────────────────────────────────────────────────
    st.divider()
    st.write("**Credit Tiers**")
    st.caption("Define how credit score ranges are labeled. "
               "These are informational — the min score threshold above controls eligibility.")

    credit_tiers = get_setting("credit_tiers")
    with st.form("credit_tiers_form"):
        updated_tiers = []
        for i, tier in enumerate(credit_tiers):
            col1, col2, col3 = st.columns(3)
            label = col1.text_input(f"Tier {i+1} Label", value=tier["label"], key=f"ct_label_{i}")
            min_s = col2.number_input(f"Min Score", value=tier["min_score"], key=f"ct_min_{i}",
                                       min_value=300, max_value=850)
            max_s = col3.number_input(f"Max Score", value=tier["max_score"], key=f"ct_max_{i}",
                                       min_value=300, max_value=850)
            updated_tiers.append({"label": label, "min_score": int(min_s), "max_score": int(max_s)})

        save_tiers = st.form_submit_button("Save Credit Tiers")

    if save_tiers:
        set_setting("credit_tiers", updated_tiers)
        st.success("Credit tiers saved.")
        st.rerun()


# ── Pricing Configuration ────────────────────────────────────────────────────

def _tab_pricing():
    st.subheader("Pricing Configuration")
    st.caption("Changes take effect on the next pricing calculation.")

    # ── Base Rates ───────────────────────────────────────────────────
    st.write("**Base Rate Components**")
    with st.form("pricing_base"):
        col1, col2 = st.columns(2)
        prime = col1.number_input(
            "Prime Rate (%)",
            min_value=0.0, max_value=25.0, step=0.25,
            value=float(get_setting("prime_rate")),
            help="Current WSJ Prime Rate. Updated periodically.",
        )
        margin = col2.number_input(
            "Base Margin (%)",
            min_value=-5.0, max_value=10.0, step=0.25,
            value=float(get_setting("base_margin")),
            help="Added to Prime before any adjustments.",
        )

        st.divider()

        col1, col2, col3 = st.columns(3)
        autopay = col1.number_input(
            "Autopay Discount (%)",
            min_value=0.0, max_value=2.0, step=0.05,
            value=float(get_setting("autopay_discount")),
        )
        floor = col2.number_input(
            "Rate Floor (%)",
            min_value=0.0, max_value=25.0, step=0.25,
            value=float(get_setting("rate_floor")),
            help="Minimum rate regardless of adjustments.",
        )
        ceiling = col3.number_input(
            "Rate Ceiling (%)",
            min_value=0.0, max_value=30.0, step=0.25,
            value=float(get_setting("rate_ceiling")),
            help="Maximum rate regardless of adjustments.",
        )

        lock_days = st.number_input(
            "Rate Lock Duration (days)",
            min_value=7, max_value=180, step=1,
            value=int(get_setting("rate_lock_days")),
        )

        save_base = st.form_submit_button("Save Base Rates", type="primary")

    if save_base:
        set_setting("prime_rate", float(prime))
        set_setting("base_margin", float(margin))
        set_setting("autopay_discount", float(autopay))
        set_setting("rate_floor", float(floor))
        set_setting("rate_ceiling", float(ceiling))
        set_setting("rate_lock_days", int(lock_days))
        st.success("Base rate settings saved.")
        st.rerun()

    # ── FICO Adjustments ─────────────────────────────────────────────
    st.divider()
    st.write("**FICO Score Adjustments**")
    st.caption("Tiers are checked top-to-bottom. First match wins. "
               "Better scores should have the best (most negative) adjustments at the top.")

    fico_adj = get_setting("fico_adjustments")
    with st.form("fico_adj_form"):
        updated_fico = []
        for i, tier in enumerate(fico_adj):
            col1, col2 = st.columns(2)
            min_score = col1.number_input(
                f"Min Score (Tier {i+1})", value=int(tier["min_score"]),
                min_value=300, max_value=850, key=f"fico_min_{i}",
            )
            adj = col2.number_input(
                f"Rate Adjustment (%)", value=float(tier["adjustment"]),
                min_value=-3.0, max_value=3.0, step=0.05, format="%.2f",
                key=f"fico_adj_{i}",
            )
            updated_fico.append({"min_score": int(min_score), "adjustment": float(adj)})

        save_fico = st.form_submit_button("Save FICO Adjustments")

    if save_fico:
        set_setting("fico_adjustments", updated_fico)
        st.success("FICO adjustments saved.")
        st.rerun()

    # ── LTV Adjustments ──────────────────────────────────────────────
    st.divider()
    st.write("**LTV Adjustments**")
    st.caption("Tiers are checked top-to-bottom. Lower CLTV = better rate.")

    ltv_adj = get_setting("ltv_adjustments")
    with st.form("ltv_adj_form"):
        updated_ltv = []
        for i, tier in enumerate(ltv_adj):
            col1, col2 = st.columns(2)
            max_ltv = col1.number_input(
                f"Max CLTV (Tier {i+1})", value=float(tier["max_ltv"]),
                min_value=0.0, max_value=1.0, step=0.05, format="%.2f",
                key=f"ltv_max_{i}",
            )
            adj = col2.number_input(
                f"Rate Adjustment (%)", value=float(tier["adjustment"]),
                min_value=-3.0, max_value=3.0, step=0.05, format="%.2f",
                key=f"ltv_adj_{i}",
            )
            updated_ltv.append({"max_ltv": float(max_ltv), "adjustment": float(adj)})

        save_ltv = st.form_submit_button("Save LTV Adjustments")

    if save_ltv:
        set_setting("ltv_adjustments", updated_ltv)
        st.success("LTV adjustments saved.")
        st.rerun()

    # ── Amount Adjustments ───────────────────────────────────────────
    st.divider()
    st.write("**Line Amount Adjustments**")
    st.caption("Tiers are checked top-to-bottom. Larger lines get better pricing.")

    amt_adj = get_setting("amount_adjustments")
    with st.form("amt_adj_form"):
        updated_amt = []
        for i, tier in enumerate(amt_adj):
            col1, col2 = st.columns(2)
            min_amt = col1.number_input(
                f"Min Amount (Tier {i+1})", value=int(tier["min_amount"]),
                min_value=0, step=10000, key=f"amt_min_{i}",
            )
            adj = col2.number_input(
                f"Rate Adjustment (%)", value=float(tier["adjustment"]),
                min_value=-3.0, max_value=3.0, step=0.05, format="%.2f",
                key=f"amt_adj_{i}",
            )
            updated_amt.append({"min_amount": int(min_amt), "adjustment": float(adj)})

        save_amt = st.form_submit_button("Save Amount Adjustments")

    if save_amt:
        set_setting("amount_adjustments", updated_amt)
        st.success("Amount adjustments saved.")
        st.rerun()


# ── Workflow (read-only) ─────────────────────────────────────────────────────

def _tab_workflow():
    st.subheader("Workflow Configuration")
    st.caption("Workflow changes require code updates. Shown here for reference.")

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


# ── Lender Info (read-only) ──────────────────────────────────────────────────

def _tab_lender():
    st.subheader("Lender Information")
    st.caption("Lender info changes require code updates. Used in generated documents.")
    st.write(f"**Name:** {LENDER_NAME}")
    st.write(f"**Address:** {LENDER_ADDRESS}")
    st.write(f"**NMLS:** {LENDER_NMLS}")
    st.write(f"**Phone:** {LENDER_PHONE}")


# ── Audit Log ────────────────────────────────────────────────────────────────

def _tab_audit():
    st.subheader("System Audit Log")
    entries = get_full_audit_log()

    if not entries:
        st.info("No audit entries yet.")
        return

    st.caption(f"{len(entries)} total entries")

    actions = sorted(set(e["action"] for e in entries))
    action_filter = st.multiselect("Filter by Action", actions)

    filtered = entries
    if action_filter:
        filtered = [e for e in entries if e["action"] in action_filter]

    rows = []
    for e in filtered[:200]:
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
