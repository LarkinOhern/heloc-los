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


def render():
    st.header("Loan Pipeline")

    apps = get_all_applications()
    if not apps:
        st.info("No applications in the system yet.")
        return

    # ── Status Counts ────────────────────────────────────────────────────
    # Show key statuses as metric cards so employees can see workload.
    # We skip DRAFT (borrower hasn't submitted) and terminal states like
    # FUNDED/WITHDRAWN since those aren't actionable.
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
        cols[i].markdown(
            f'<div style="text-align:center; padding:8px; border-left:4px solid {color};">'
            f'<div style="font-size:24px; font-weight:bold;">{counts[status]}</div>'
            f'<div style="font-size:12px; color:#666;">{label}</div></div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Filters ──────────────────────────────────────────────────────────
    # Let employees filter by status so they can focus on their queue.
    col1, col2 = st.columns(2)
    status_filter = col1.multiselect(
        "Filter by Status",
        [s for s in STATUSES if s != "DRAFT"],
        default=[],
        format_func=lambda x: STATUS_LABELS.get(x, x),
    )
    search = col2.text_input("Search (app number or borrower name)", "")

    # ── Build Table Data ─────────────────────────────────────────────────
    # Enrich each application with the primary borrower name for display.
    rows = []
    for a in apps:
        # Skip drafts — those are the borrower's problem, not the employee's
        if a["status"] == "DRAFT":
            continue
        if status_filter and a["status"] not in status_filter:
            continue

        borrowers = get_borrowers(a["id"])
        primary = next((b for b in borrowers if b["is_primary"]), None)
        borrower_name = f"{primary['first_name']} {primary['last_name']}" if primary else "—"

        # Text search across app number and borrower name
        if search:
            search_lower = search.lower()
            if (search_lower not in a["application_number"].lower()
                    and search_lower not in borrower_name.lower()):
                continue

        rows.append({
            "id": a["id"],
            "App Number": a["application_number"],
            "Borrower": borrower_name,
            "Status": STATUS_LABELS.get(a["status"], a["status"]),
            "HELOC Amount": fmt_currency(a["heloc_amount_requested"]),
            "Property Value": fmt_currency(a["property_value"]),
            "Submitted": fmt_date(a["submitted_at"]),
            "Assigned To": a["assigned_employee"] or "Unassigned",
        })

    if not rows:
        st.info("No applications match the current filters.")
        return

    st.caption(f"Showing {len(rows)} application{'s' if len(rows) != 1 else ''}")

    # ── Render Each Row ──────────────────────────────────────────────────
    # Using columns instead of a dataframe so we can embed a "Review" button
    # on each row that navigates to the review page.
    for row in rows:
        col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 1.5, 1.5, 1.5, 1])
        col1.write(f"**{row['App Number']}**")
        col2.write(row["Borrower"])
        col3.write(row["Status"])
        col4.write(row["HELOC Amount"])
        col5.write(row["Submitted"])
        if col6.button("Review", key=f"review_{row['id']}"):
            st.session_state["review_app_id"] = row["id"]
            # Switch nav to Review page. The key depends on whether user is
            # LO or Admin (different radio keys in app.py).
            if st.session_state.get("role") == "Admin":
                st.session_state["admin_nav"] = "Review Application"
            else:
                st.session_state["lo_nav"] = "Review Application"
            st.rerun()
