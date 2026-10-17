"""Round 3: issues found during the Round 2 browser regression."""

from tests.test_app_flows import _texts, _button, _as_employee, _as_borrower, _field


# ── N-03: borrowers see outstanding items whatever the approval status ─────

def test_outstanding_items_shown_on_approved_file(apptest, app_by_number):
    from src.utils.db_helpers import update_application, create_condition
    tony = app_by_number("DEMO-2026-000004")
    update_application(tony["id"], status="APPROVED", assigned_employee="jsmith")
    create_condition(tony["id"], condition_type="PRIOR_TO_CLOSING",
                     description="Provide current mortgage statement",
                     added_by="jsmith", doc_type="MORTGAGE_STMT")
    at = _as_borrower(apptest(), "tony@example.com")
    at.sidebar.radio(key="borrower_nav").set_value("Status").run()
    assert "Provide current mortgage statement" in _texts(at)


# ── N-04: borrower timeline formats the lock expiry ─────────────────────────

def test_rate_lock_item_uses_readable_date():
    from src.utils.timeline import borrower_timeline
    items = borrower_timeline([{
        "action": "RATE_LOCKED", "performed_by": "jsmith", "performed_at": "2026-10-17T13:12:00",
        "details": "Rate of 8.000% locked for 60 days (expires 2026-12-16)",
    }])
    assert items[0]["detail"] == "Your rate of 8.000% is locked until Dec 16, 2026."


# ── N-05: State has no silent default ───────────────────────────────────────

def test_state_starts_blank_and_is_required(apptest):
    at = _as_borrower(apptest(), "state@example.com")
    _button(at, "Begin New Application").click().run()
    state = _field(at.selectbox, "State")
    assert state.value is None
    _field(at.text_input, "Street Address").set_value("1 Main St")
    _field(at.text_input, "City").set_value("El Paso")
    _field(at.text_input, "ZIP Code").set_value("79912")
    _field(at.number_input, "Estimated Property Value ($)").set_value(300000.0)
    _field(at.number_input, "HELOC Amount Requested ($)").set_value(30000.0)
    _button(at, "Save & Continue").click().run()
    assert any("state" in e.value.lower() for e in at.error)


# ── N-06: no "do X first" hints for people who can't act ────────────────────

def test_read_only_officer_sees_no_action_hints(apptest, app_by_number):
    harry = app_by_number("DEMO-2026-000005")  # bwilson's, no UW decision yet
    at = _as_employee(apptest(), "Loan Officer", "Jane Smith")
    at.button(key=f"review_{harry['id']}").click().run()
    text = _texts(at)
    assert "Run underwriting first" not in text
    assert "Move the application" not in text
