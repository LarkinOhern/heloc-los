"""Pipeline / queue view for loan officers and admins.

Shows status counts as metrics across the top, then a filterable table of all
applications. Clicking "Review" on a row stores the app ID in session state so
the Review page can pick it up.
"""

import pandas as pd
import streamlit as st

from src.config import STATUSES, STATUS_LABELS, STATUS_COLORS
from src.utils.db_helpers import get_all_applications, get_borrowers
from src.utils.formatters import fmt_currency, fmt_date
from src.utils.styles import pipeline_card, status_badge


def render():
    st.header("Loan Pipeline")

    apps = get_all_applications()
    if not apps:
        st.info("No applications in the system yet.")
        return

    # ── Status Counts ────────────────────────────────────────────────────
    actionable = ["SUBMITTED", "IN_REVIEW", "UNDERWRITING",
                  "APPROVED", "APPROVED_WITH_CONDITIONS", "CLOSING"]
    counts = {s: 0 for s in actionable}
    for a in apps:
        if a["status"] in counts:
            counts[a["status"]] += 1

    cols = st.columns(len(actionable))
    for i, status in enumerate(actionable):
        label = STATUS_LABELS.get(status, status)
        color = STATUS_COLORS.get(status, "#9e9e9e")
        cols[i].markdown(pipeline_card(counts[status], label, color),
                         unsafe_allow_html=True)

    st.divider()

    # ── Filters ──────────────────────────────────────────────────────────
    col1, col2 = st.columns(2)
    status_filter = col1.multiselect(
        "Filter by Status",
        [s for s in STATUSES if s != "DRAFT"],
        default=[],
        format_func=lambda x: STATUS_LABELS.get(x, x),
    )
    search = col2.text_input("Search (app number or borrower name)", "")

    # ── Build Table Data ─────────────────────────────────────────────────
    rows = []
    for a in apps:
        if a["status"] == "DRAFT":
            continue
        if status_filter and a["status"] not in status_filter:
            continue

        borrowers = get_borrowers(a["id"])
        primary = next((b for b in borrowers if b["is_primary"]), None)
        borrower_name = f"{primary['first_name']} {primary['last_name']}" if primary else "--"

        if search:
            search_lower = search.lower()
            if (search_lower not in a["application_number"].lower()
                    and search_lower not in borrower_name.lower()):
                continue

        rows.append({
            "id": a["id"],
            "app_number": a["application_number"],
            "borrower": borrower_name,
            "status": a["status"],
            "heloc_amount": fmt_currency(a["heloc_amount_requested"]),
            "submitted": fmt_date(a["submitted_at"]),
            "assigned": a["assigned_employee"] or "Unassigned",
        })

    if not rows:
        st.info("No applications match the current filters.")
        return

    st.caption(f"Showing {len(rows)} application{'s' if len(rows) != 1 else ''}")

    # ── Table Header ─────────────────────────────────────────────────────
    hcols = st.columns([2, 2, 1.5, 1.5, 1.5, 1.2, 0.8])
    hcols[0].markdown("**App Number**")
    hcols[1].markdown("**Borrower**")
    hcols[2].markdown("**Status**")
    hcols[3].markdown("**HELOC Amount**")
    hcols[4].markdown("**Submitted**")
    hcols[5].markdown("**Assigned**")
    hcols[6].markdown("**Action**")

    # ── Render Each Row ──────────────────────────────────────────────────
    for row in rows:
        col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 2, 1.5, 1.5, 1.5, 1.2, 0.8])
        col1.write(f"**{row['app_number']}**")
        col2.write(row["borrower"])
        col3.markdown(status_badge(row["status"]), unsafe_allow_html=True)
        col4.write(row["heloc_amount"])
        col5.write(row["submitted"])
        col6.write(row["assigned"])
        if col7.button("Review", key=f"review_{row['id']}"):
            st.session_state["review_app_id"] = row["id"]
            st.session_state["_pending_nav"] = "Review Application"
            st.session_state.pop("lo_nav", None)
            st.session_state.pop("admin_nav", None)
            st.rerun()
