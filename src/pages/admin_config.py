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
from src.utils.db_helpers import get_full_audit_log, get_system_audit_log, add_system_audit_entry
from src.utils.formatters import fmt_datetime


def _current_user():
    return st.session_state.get("employee_display_name", "Admin")


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
        add_system_audit_entry("CONFIG_RESET", "All settings reset to defaults", _current_user())
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
        add_system_audit_entry(
            "CONFIG_CHANGE",
            f"UW thresholds updated: FICO>={int(min_credit)}, CLTV<={max_cltv:.0f}%, "
            f"DTI<={max_dti:.0f}%, PropVal>=${int(min_prop):,}, "
            f"HELOC ${int(min_heloc):,}-${int(max_heloc):,}",
            _current_user(),
        )
        st.success("Underwriting thresholds saved.")
        st.rerun()

    # ── Credit Score Tiers (unified: labels + pricing adjustments) ──
    st.divider()
    st.write("**Credit Score Tiers & Rate Adjustments**")
    st.caption(
        "Each tier defines a score range, a label, and a rate adjustment that "
        "gets applied during pricing. For example, 'Excellent' borrowers (760+) "
        "get a -0.50% rate discount. These tiers drive both underwriting classification "
        "and pricing calculations."
    )

    credit_tiers = get_setting("credit_tiers")
    with st.form("credit_tiers_form"):
        # Header row
        hcol1, hcol2, hcol3, hcol4 = st.columns([2, 1.5, 1.5, 1.5])
        hcol1.write("**Tier Label**")
        hcol2.write("**Min Score**")
        hcol3.write("**Max Score**")
        hcol4.write("**Rate Adjustment (%)**")

        updated_tiers = []
        for i, tier in enumerate(credit_tiers):
            col1, col2, col3, col4 = st.columns([2, 1.5, 1.5, 1.5])
            label = col1.text_input(
                f"Label {i+1}", value=tier["label"], key=f"ct_label_{i}",
                label_visibility="collapsed",
            )
            min_s = col2.number_input(
                f"Min {i+1}", value=int(tier["min_score"]), key=f"ct_min_{i}",
                min_value=300, max_value=850, label_visibility="collapsed",
            )
            max_s = col3.number_input(
                f"Max {i+1}", value=int(tier["max_score"]), key=f"ct_max_{i}",
                min_value=300, max_value=850, label_visibility="collapsed",
            )
            adj = col4.number_input(
                f"Adj {i+1}", value=float(tier.get("rate_adjustment", 0.0)),
                key=f"ct_adj_{i}", min_value=-3.0, max_value=3.0, step=0.05,
                format="%.2f", label_visibility="collapsed",
            )
            updated_tiers.append({
                "label": label,
                "min_score": int(min_s),
                "max_score": int(max_s),
                "rate_adjustment": float(adj),
            })

        save_tiers = st.form_submit_button("Save Credit Tiers & Adjustments", type="primary")

    if save_tiers:
        set_setting("credit_tiers", updated_tiers)
        tier_summary = ", ".join(
            f"{t['label']} ({t['min_score']}-{t['max_score']}): {t['rate_adjustment']:+.2f}%"
            for t in updated_tiers
        )
        add_system_audit_entry("CONFIG_CHANGE", f"Credit tiers updated: {tier_summary}", _current_user())
        st.success("Credit tiers and rate adjustments saved. "
                   "Changes will apply to the next pricing calculation.")
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
        add_system_audit_entry(
            "CONFIG_CHANGE",
            f"Base rates updated: Prime={prime:.2f}%, Margin={margin:.2f}%, "
            f"Autopay disc={autopay:.2f}%, Floor={floor:.2f}%, "
            f"Ceiling={ceiling:.2f}%, Lock={int(lock_days)}d",
            _current_user(),
        )
        st.success("Base rate settings saved.")
        st.rerun()

    # ── FICO / Credit Score Adjustments ──────────────────────────────
    st.divider()
    st.info("**FICO / Credit Score Adjustments** are managed in the "
            "**Underwriting Guidelines** tab under *Credit Score Tiers & "
            "Rate Adjustments*. Changes there automatically feed into pricing.")

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
        ltv_summary = ", ".join(
            f"<={t['max_ltv']:.0%}: {t['adjustment']:+.2f}%" for t in updated_ltv
        )
        add_system_audit_entry("CONFIG_CHANGE", f"LTV adjustments updated: {ltv_summary}", _current_user())
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
        amt_summary = ", ".join(
            f">=${t['min_amount']:,}: {t['adjustment']:+.2f}%" for t in updated_amt
        )
        add_system_audit_entry("CONFIG_CHANGE", f"Amount adjustments updated: {amt_summary}", _current_user())
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

    # Merge application-level and system-level audit entries into one view.
    app_entries = get_full_audit_log()
    sys_entries = get_system_audit_log()

    # Normalize system entries to match the app entry format
    for e in sys_entries:
        e["application_number"] = "SYSTEM"

    all_entries = app_entries + sys_entries
    all_entries.sort(key=lambda e: e.get("performed_at", ""), reverse=True)

    if not all_entries:
        st.info("No audit entries yet.")
        return

    st.caption(f"{len(all_entries)} total entries")

    actions = sorted(set(e["action"] for e in all_entries))
    action_filter = st.multiselect("Filter by Action", actions)

    filtered = all_entries
    if action_filter:
        filtered = [e for e in all_entries if e["action"] in action_filter]

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
