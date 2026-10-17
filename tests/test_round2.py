"""Round 2: controls, conditions, attribution and display findings."""

import pytest

from tests.test_app_flows import (
    _texts, _button, _as_employee, _as_borrower, _draft_for, _field,
)


# ── N-01: dollar amounts must not become LaTeX ──────────────────────────────

def test_md_escape_dollars():
    from src.utils.formatters import md_escape
    assert md_escape("Monthly debts: $2,000 vs. income: $5,000") == \
        "Monthly debts: \\$2,000 vs. income: \\$5,000"


def test_pricing_tier_label_is_escaped_on_screen(apptest, app_by_number):
    george = app_by_number("DEMO-2026-000002")  # $150K line, bwilson
    at = _as_employee(apptest(), "Loan Officer", "Bob Wilson")
    at.button(key=f"review_{george['id']}").click().run()
    assert "\\$100,000 to \\$249,999" in _texts(at)


# ── C-02: officers can only work files assigned to them ─────────────────────

def test_officer_cannot_change_someone_elses_file(apptest, app_by_number):
    harry = app_by_number("DEMO-2026-000005")  # bwilson's file
    at = _as_employee(apptest(), "Loan Officer", "Jane Smith")
    at.button(key=f"review_{harry['id']}").click().run()
    assert not [s for s in at.selectbox if s.key == "status_change"]
    assert not [b for b in at.button if b.label == "Run Underwriting Engine"]
    assert "bwilson" in _texts(at)


def test_unassigned_file_must_be_claimed_first(apptest, app_by_number):
    tony = app_by_number("DEMO-2026-000004")  # unassigned
    at = _as_employee(apptest(), "Loan Officer", "Jane Smith")
    at.button(key=f"review_{tony['id']}").click().run()
    assert not [s for s in at.selectbox if s.key == "status_change"]
    _button(at, "Assign to Me").click().run()
    assert [s for s in at.selectbox if s.key == "status_change"]


def test_admin_can_work_any_file_and_reassign(apptest, app_by_number):
    harry = app_by_number("DEMO-2026-000005")
    at = _as_employee(apptest(), "Admin", "Admin User")
    at.button(key=f"review_{harry['id']}").click().run()
    assert [s for s in at.selectbox if s.key == "status_change"]
    at.selectbox(key="reassign_to").set_value("jsmith").run()
    _button(at, "Reassign").click().run()
    assert app_by_number("DEMO-2026-000005")["assigned_employee"] == "jsmith"


def test_conditions_page_is_read_only_for_non_owner(apptest, app_by_number):
    george = app_by_number("DEMO-2026-000002")  # bwilson
    at = _as_employee(apptest(), "Loan Officer", "Jane Smith")
    at.session_state["review_app_id"] = george["id"]
    at.sidebar.radio(key="lo_nav").set_value("Conditions").run()
    assert not [b for b in at.button if b.label in ("Satisfy", "Waive")]


# ── C-04: waiving needs a written reason, which is kept ─────────────────────

def _open_conditions_as_bob(apptest, app):
    at = _as_employee(apptest(), "Loan Officer", "Bob Wilson")
    at.session_state["review_app_id"] = app["id"]
    at.sidebar.radio(key="lo_nav").set_value("Conditions").run()
    return at


def test_waive_requires_reason(apptest, app_by_number):
    from src.utils.db_helpers import get_conditions
    george = app_by_number("DEMO-2026-000002")
    cond = next(c for c in get_conditions(george["id"])
                if c["description"] == "Verify flood insurance coverage")
    at = _open_conditions_as_bob(apptest, george)
    at.button(key=f"waive_{cond['id']}").click().run()
    _button(at, "Confirm waiver").click().run()  # empty reason
    assert any("reason" in e.value.lower() for e in at.error)
    assert next(c for c in get_conditions(george["id"]) if c["id"] == cond["id"])["status"] == "OPEN"

    at.text_input(key=f"waive_reason_{cond['id']}").set_value(
        "Property is outside any FEMA flood zone per county map.")
    _button(at, "Confirm waiver").click().run()
    after = next(c for c in get_conditions(george["id"]) if c["id"] == cond["id"])
    assert after["status"] == "WAIVED"
    assert "FEMA" in after["resolution_note"]


# ── C-05 / C-07: engine output is internal and credited to the engine ──────

def test_engine_conditions_are_internal_review_items(db, app_by_number):
    from src.pages.employee_review import _execute_underwriting
    from src.utils.db_helpers import (
        get_conditions, get_underwriting_decisions, update_application,
        get_application, get_borrowers, update_borrower,
    )
    tony = app_by_number("DEMO-2026-000004")
    # 715 FICO triggers the "below preferred 720" warning -> conditions.
    primary = next(b for b in get_borrowers(tony["id"]) if b["is_primary"])
    update_borrower(primary["id"], credit_score=715)
    update_application(tony["id"], status="UNDERWRITING", assigned_employee="jsmith")
    _execute_underwriting(get_application(tony["id"]), "jsmith")

    conds = get_conditions(tony["id"])
    assert conds and all(c["condition_type"] == "INTERNAL_REVIEW" for c in conds)
    assert all(c["description"].startswith("Underwriter review:") for c in conds)
    assert get_underwriting_decisions(tony["id"])[0]["decided_by"] == "UW_ENGINE:jsmith"


def test_internal_review_items_hidden_from_borrower(apptest, app_by_number):
    from src.utils.db_helpers import create_condition
    george = app_by_number("DEMO-2026-000002")
    create_condition(george["id"], condition_type="INTERNAL_REVIEW",
                     description="Underwriter review: secret note", added_by="UW_ENGINE")
    at = _as_borrower(apptest(), "george@example.com")
    at.sidebar.radio(key="borrower_nav").set_value("Status").run()
    text = _texts(at)
    assert "Provide updated property appraisal" in text
    assert "secret note" not in text


# ── C-06: a condition can request a document and shows when it arrives ────

def test_condition_shows_requested_document_received(apptest, app_by_number):
    from src.utils.db_helpers import create_condition, create_document
    george = app_by_number("DEMO-2026-000002")
    create_condition(george["id"], condition_type="PRIOR_TO_CLOSING",
                     description="Provide homeowners insurance declaration",
                     added_by="bwilson", doc_type="HOMEOWNERS_INS")
    at = _open_conditions_as_bob(apptest, george)
    assert "Waiting for borrower" in _texts(at)

    create_document(george["id"], doc_type="HOMEOWNERS_INS",
                    filename="dec_page.pdf", uploaded_by="george@example.com")
    at.run()
    assert "dec_page.pdf" in _texts(at)


def test_borrower_sees_which_document_is_requested(apptest, app_by_number):
    from src.utils.db_helpers import create_condition
    george = app_by_number("DEMO-2026-000002")
    create_condition(george["id"], condition_type="PRIOR_TO_CLOSING",
                     description="Provide homeowners insurance declaration",
                     added_by="bwilson", doc_type="HOMEOWNERS_INS")
    at = _as_borrower(apptest(), "george@example.com")
    at.sidebar.radio(key="borrower_nav").set_value("Documents").run()
    assert "Requested" in _texts(at)


# ── F-07: config change log shows before and after ─────────────────────────

def test_describe_changes_lists_only_changed_values():
    from src.utils.formatters import describe_changes
    text = describe_changes({
        "Max CLTV": ("80%", "65%"),
        "Max DTI": ("43%", "43%"),
    })
    assert text == "Max CLTV: 80% → 65%"


def test_describe_changes_empty_when_nothing_changed():
    from src.utils.formatters import describe_changes
    assert describe_changes({"Max DTI": ("43%", "43%")}) == ""


# ── F-09: pricing keeps the tier labels it actually used ───────────────────

def test_pricing_lock_stores_tier_labels(db, app_by_number):
    from src.pages.employee_review import _execute_pricing
    from src.utils.db_helpers import get_pricing_locks, get_underwriting_decisions, get_application
    george = get_application(app_by_number("DEMO-2026-000002")["id"])
    _execute_pricing(george, get_underwriting_decisions(george["id"])[0], "bwilson")
    lock = get_pricing_locks(george["id"])[0]
    assert lock["amount_tier"] == "$100,000 to $249,999"
    assert lock["fico_tier"] and lock["ltv_tier"]


# ── O-03: credit score starts blank and is required ────────────────────────

def test_credit_score_starts_blank_and_is_required(apptest):
    from src.utils.db_helpers import (
        create_application, create_borrower, update_application,
    )
    app_id = create_application()
    update_application(app_id, property_address="2 Blank St", property_city="Waco",
                       property_state="TX", property_zip="76701", property_value=300_000,
                       heloc_amount_requested=40_000)
    create_borrower(app_id, is_primary=True, email="blank@example.com")
    at = _as_borrower(apptest(), "blank@example.com")
    at.session_state["app_id"] = app_id
    at.session_state["wizard_step"] = 1
    at.run()
    score = _field(at.number_input, "Self-Reported Credit Score")
    assert score.value is None
    _field(at.text_input, "First Name").set_value("Bea")
    _field(at.text_input, "Last Name").set_value("Blank")
    _button(at, "Save & Continue").click().run()
    assert any("credit score" in e.value.lower() for e in at.error)


# ── O-04: mismatched mortgage balances are flagged on review ───────────────

def test_review_flags_mortgage_mismatch(apptest):
    from src.utils.db_helpers import create_debt
    app_id, bid = _draft_for("mismatch@example.com")  # property step says $200,000
    create_debt(bid, debt_type="MORTGAGE", creditor="Lender", monthly_payment=1500, balance=260_000)
    at = _as_borrower(apptest(), "mismatch@example.com")
    at.session_state["app_id"] = app_id
    at.session_state["wizard_step"] = 5
    at.run()
    assert any("mortgage" in w.value.lower() for w in at.warning)


# ── N-02 / F-07: admin saves confirm on screen and log before → after ──────

def test_admin_save_confirms_and_logs_before_after(apptest):
    from src.utils.db_helpers import get_system_audit_log
    at = _as_employee(apptest(), "Admin", "Admin User")
    at.sidebar.radio(key="admin_nav").set_value("Admin Config").run()
    _field(at.number_input, "Maximum CLTV (%)").set_value(65.0)
    _button(at, "Save Thresholds").click().run()

    assert any("thresholds saved" in s.value.lower() for s in at.success)
    latest = get_system_audit_log()[0]["details"]
    assert latest == "UW thresholds: Max CLTV: 80% → 65%"
