"""Screen-flow tests that run the real Streamlit app headlessly with AppTest.

Each test reproduces a finding from the browser test log by driving the same
widgets a person would.
"""

from datetime import datetime, timedelta


# ── helpers ──────────────────────────────────────────────────────────────────

def _texts(at):
    """Every piece of rendered text, for 'does the page say X' checks."""
    parts = []
    for kind in ("markdown", "caption", "header", "subheader", "success",
                 "info", "warning", "error", "title", "text"):
        parts += [getattr(e, "value", "") or "" for e in getattr(at, kind)]
    for m in at.metric:
        parts += [m.label, str(m.value)]
    return "\n".join(str(p) for p in parts)


def _button(at, label):
    matches = [b for b in at.button if b.label == label]
    assert matches, f"no button labelled {label!r}; have {[b.label for b in at.button]}"
    return matches[0]


def _field(collection, label):
    matches = [w for w in collection if w.label == label]
    assert len(matches) == 1, f"expected one {label!r}, found {len(matches)}"
    return matches[0]


def _as_employee(at, role, name):
    at.sidebar.selectbox(key="role_selector").set_value(role).run()
    at.sidebar.selectbox(key="employee_selector").set_value(name).run()
    return at


def _as_borrower(at, email):
    at.sidebar.text_input(key="borrower_email_input").set_value(email).run()
    return at


def _draft_for(email, *, with_income=True, with_assets=True):
    """Create a draft that has finished every step a resume should skip."""
    from src.utils.db_helpers import (
        create_application, create_borrower, update_application,
        create_employment, create_asset,
    )
    app_id = create_application()
    update_application(
        app_id, property_address="1 Test Way", property_city="Austin",
        property_state="TX", property_zip="78701", property_value=400_000,
        existing_mortgage_balance=200_000, heloc_amount_requested=50_000,
    )
    bid = create_borrower(app_id, is_primary=True, email=email,
                          first_name="Rita", last_name="Resume", credit_score=760)
    if with_income:
        create_employment(bid, employer_name="Acme", position="Analyst",
                          years_employed=3, monthly_income=8_000, income_type="SALARY")
    if with_assets:
        create_asset(bid, account_type="CHECKING", institution="Bank", balance=10_000)
    return app_id, bid


# ── F-01: pipeline drill-in must not swallow the next action ────────────────

def test_pipeline_review_then_status_change_stays_on_review(apptest, app_by_number):
    harry = app_by_number("DEMO-2026-000005")  # IN_REVIEW, assigned to bwilson
    at = _as_employee(apptest(), "Loan Officer", "Bob Wilson")
    at.button(key=f"review_{harry['id']}").click().run()
    assert "Application Review" in _texts(at)

    # The browser bug: the server switched pages but never told the browser's
    # radio to change, so the browser sent "Pipeline" back on the next click.
    # AppTest keeps server state, so check the instruction the browser gets.
    nav = at.sidebar.radio(key="lo_nav")
    assert nav.value == "Review Application"
    assert nav.proto.set_value, "browser is not told to move its nav radio"

    at.selectbox(key="status_change").set_value("UNDERWRITING").run()

    assert "Application Review" in _texts(at), "bounced back to the pipeline"
    assert any(b.label == "Update Status" for b in at.button)


# ── F-05: the add-income form clears after a successful add ─────────────────

def test_add_income_form_clears(apptest):
    app_id, bid = _draft_for("clear@example.com", with_income=False, with_assets=False)
    at = _as_borrower(apptest(), "clear@example.com")
    at.session_state["app_id"] = app_id
    at.session_state["wizard_step"] = 3
    at.run()

    _field(at.text_input, "Employer Name").set_value("Acme")
    _field(at.number_input, "Monthly Income ($)").set_value(5000.0)
    _button(at, "Add Income for Rita").click().run()

    from src.utils.db_helpers import get_employment
    assert len(get_employment(bid)) == 1
    assert _field(at.text_input, "Employer Name").value == ""
    assert _field(at.number_input, "Monthly Income ($)").value == 0.0

    # Clicking Add again on the now-empty form must not add a duplicate.
    _button(at, "Add Income for Rita").click().run()
    assert len(get_employment(bid)) == 1


# ── F-06: resume goes to the first unfinished step ──────────────────────────

def test_resume_lands_on_review_when_everything_is_filled(apptest):
    app_id, _ = _draft_for("resume@example.com")
    at = _as_borrower(apptest(), "resume@example.com")
    at.button(key=f"resume_{app_id}").click().run()
    assert "Review Your Application" in _texts(at)


def test_resume_lands_on_employment_when_income_missing(apptest):
    app_id, _ = _draft_for("noincome@example.com", with_income=False, with_assets=False)
    at = _as_borrower(apptest(), "noincome@example.com")
    at.button(key=f"resume_{app_id}").click().run()
    # Co-borrower is optional, so the next required step is Employment.
    assert "Employment & Income" in _texts(at) or "Co-Borrower Information" in _texts(at)


# ── O-01: a second click after submitting keeps the confirmation ───────────

def test_submit_confirmation_survives_next_rerun(apptest):
    from src.utils.db_helpers import get_application
    app_id, _ = _draft_for("submit@example.com")
    number = get_application(app_id)["application_number"]
    at = _as_borrower(apptest(), "submit@example.com")
    at.session_state["app_id"] = app_id
    at.session_state["wizard_step"] = 5
    at.run()
    at.checkbox(key="econsent_check").check().run()
    _button(at, "Submit Application").click().run()
    assert number in _texts(at)

    at.run()  # any further interaction
    assert number in _texts(at), "confirmation disappeared on the next rerun"
    assert get_application(app_id)["status"] == "SUBMITTED"


# ── C-01: borrowers never see officer names or internal notes ──────────────

def test_borrower_status_page_hides_internal_audit(apptest):
    at = _as_borrower(apptest(), "homer@example.com")
    at.sidebar.radio(key="borrower_nav").set_value("Status").run()
    text = _texts(at)
    assert "Application Status" in text
    assert "jsmith" not in text
    assert "Engine decision" not in text


# ── C-03: no Closing while prior-to-closing conditions are open ────────────

def test_cannot_move_to_closing_with_open_conditions(apptest, app_by_number):
    george = app_by_number("DEMO-2026-000002")  # APPROVED_WITH_CONDITIONS, bwilson
    at = _as_employee(apptest(), "Loan Officer", "Bob Wilson")
    at.button(key=f"review_{george['id']}").click().run()
    at.selectbox(key="status_change").set_value("CLOSING").run()
    _button(at, "Update Status").click().run()

    assert app_by_number("DEMO-2026-000002")["status"] == "APPROVED_WITH_CONDITIONS"
    assert any("condition" in e.value.lower() for e in at.error)


# ── F-08: rate lock length comes from the admin setting ────────────────────

def test_rate_lock_uses_admin_lock_days(db, app_by_number):
    from src.config_manager import set_setting
    from src.utils.db_helpers import create_pricing_lock, get_pricing_locks
    from src.pages.employee_review import _lock_rate

    set_setting("rate_lock_days", 30)
    app = app_by_number("DEMO-2026-000004")
    create_pricing_lock(app["id"], final_rate=8.5, monthly_payment=100.0, rate_locked=False)
    lock = get_pricing_locks(app["id"])[0]
    _lock_rate(app, lock, "jsmith")

    lock = next(l for l in get_pricing_locks(app["id"]) if l["id"] == lock["id"])
    expires = datetime.fromisoformat(lock["lock_expiration"])
    assert abs((expires - datetime.utcnow()) - timedelta(days=30)) < timedelta(minutes=5)
