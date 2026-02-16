"""Seed data script — populates the database with sample applications.

Called on app startup if the database is empty. Creates applications at
various stages of the workflow so the prototype has realistic data to
demonstrate all features immediately.
"""

import json
from src.database import get_connection, init_db
from src.config_manager import seed_settings
from src.utils.db_helpers import (
    create_application, create_borrower, create_employment,
    create_asset, create_debt, create_underwriting_decision,
    create_pricing_lock, create_condition, create_document,
    update_application, add_audit_entry,
)
from src.utils.formatters import now_utc
from src.engines.underwriting import UnderwritingInput, run_underwriting
from src.engines.pricing import PricingInput, calculate_pricing
from src.documents.generator import (
    generate_initial_disclosure, generate_decision_letter,
    generate_closing_documents,
)


# Seed apps use DEMO- prefix so they never collide with real user apps.
SEED_APP_NUMBERS = [
    "DEMO-2026-000001",
    "DEMO-2026-000002",
    "DEMO-2026-000003",
    "DEMO-2026-000004",
    "DEMO-2026-000005",
]


def _seed_apps_exist() -> bool:
    """Check if the seed applications are already in the database."""
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM applications WHERE application_number = ?",
        (SEED_APP_NUMBERS[0],),
    ).fetchone()
    conn.close()
    return row["cnt"] > 0


def seed_database():
    """Create sample data across all workflow stages."""
    init_db()
    seed_settings()  # Populate config defaults into DB
    if _seed_apps_exist():
        return

    # ── App 1: Fully funded (complete happy path) ────────────────────
    app1 = _create_app(
        address="742 Evergreen Terrace", city="Springfield", state="IL", zip="62704",
        value=450000, mortgage=180000, heloc=60000, purpose="Kitchen renovation",
        autopay=True,
        borrower=("Homer", "Simpson", "homer@example.com", "555-0001", "1234", 745),
        coborrower=("Marge", "Simpson", "marge@example.com", "555-0002", "5678", 780),
        employer="Springfield Nuclear", position="Safety Inspector", income=9500,
        co_employer="Springfield Elementary", co_position="Substitute Teacher", co_income=3200,
        app_number=SEED_APP_NUMBERS[0],
        assets=[("CHECKING", "First Bank", 45000), ("SAVINGS", "First Bank", 28000),
                ("RETIREMENT", "Fidelity", 125000)],
        debts=[("MORTGAGE", "Home Federal", 1350, 180000), ("AUTO", "Toyota Financial", 450, 18000)],
    )
    # Walk through full workflow
    update_application(app1["app_id"], status="SUBMITTED", submitted_at=now_utc(),
                       econsent_given=1, econsent_date=now_utc(), assigned_employee="jsmith")
    add_audit_entry(app1["app_id"], "STATUS_CHANGE", "DRAFT -> SUBMITTED", "homer@example.com")
    generate_initial_disclosure(app1["app_id"])
    add_audit_entry(app1["app_id"], "DOCUMENT_GENERATED", "Initial Disclosure generated", "system")

    update_application(app1["app_id"], status="IN_REVIEW")
    add_audit_entry(app1["app_id"], "STATUS_CHANGE", "SUBMITTED -> IN_REVIEW", "jsmith")
    add_audit_entry(app1["app_id"], "ASSIGNED", "Assigned to jsmith", "jsmith")

    update_application(app1["app_id"], status="UNDERWRITING")
    add_audit_entry(app1["app_id"], "STATUS_CHANGE", "IN_REVIEW -> UNDERWRITING", "jsmith")

    _run_uw_and_pricing(app1, "jsmith")

    update_application(app1["app_id"], status="CLOSING")
    add_audit_entry(app1["app_id"], "STATUS_CHANGE", "APPROVED -> CLOSING", "jsmith")
    generate_closing_documents(app1["app_id"])
    add_audit_entry(app1["app_id"], "DOCUMENT_GENERATED", "Closing documents generated", "jsmith")

    update_application(app1["app_id"], status="FUNDED")
    add_audit_entry(app1["app_id"], "STATUS_CHANGE", "CLOSING -> FUNDED", "jsmith")

    # ── App 2: Approved with conditions (waiting for borrower) ───────
    app2 = _create_app(
        address="1600 Pennsylvania Ave", city="Washington", state="DC", zip="20500",
        value=800000, mortgage=400000, heloc=150000, purpose="Home office addition",
        autopay=False,
        borrower=("George", "Washington", "george@example.com", "555-0003", "1776", 710),
        employer="Federal Government", position="Executive", income=15000,
        assets=[("CHECKING", "Treasury Direct", 200000), ("INVESTMENT", "Vanguard", 500000)],
        debts=[("MORTGAGE", "Fannie Mae", 2800, 400000), ("PERSONAL", "SBA", 500, 15000)],
        app_number=SEED_APP_NUMBERS[1],
    )
    update_application(app2["app_id"], status="SUBMITTED", submitted_at=now_utc(),
                       econsent_given=1, econsent_date=now_utc(), assigned_employee="bwilson")
    add_audit_entry(app2["app_id"], "STATUS_CHANGE", "DRAFT -> SUBMITTED", "george@example.com")
    generate_initial_disclosure(app2["app_id"])

    update_application(app2["app_id"], status="IN_REVIEW")
    add_audit_entry(app2["app_id"], "STATUS_CHANGE", "SUBMITTED -> IN_REVIEW", "bwilson")

    update_application(app2["app_id"], status="UNDERWRITING")
    add_audit_entry(app2["app_id"], "STATUS_CHANGE", "IN_REVIEW -> UNDERWRITING", "bwilson")

    _run_uw_and_pricing(app2, "bwilson")

    # Add extra manual conditions
    create_condition(app2["app_id"], condition_type="PRIOR_TO_CLOSING",
                     description="Provide updated property appraisal", added_by="bwilson")
    create_condition(app2["app_id"], condition_type="PRIOR_TO_FUNDING",
                     description="Verify flood insurance coverage", added_by="bwilson")

    # ── App 3: Denied (CLTV too high) ────────────────────────────────
    app3 = _create_app(
        address="221B Baker Street", city="London", state="NY", zip="10001",
        value=350000, mortgage=260000, heloc=100000, purpose="Debt consolidation",
        autopay=True,
        borrower=("Sherlock", "Holmes", "sherlock@example.com", "555-0004", "2210", 720),
        employer="Self Employed", position="Consulting Detective", income=7000,
        assets=[("CHECKING", "Barclays", 15000)],
        debts=[("MORTGAGE", "HSBC", 2100, 260000), ("CREDIT_CARD", "Amex", 800, 25000)],
        app_number=SEED_APP_NUMBERS[2],
    )
    update_application(app3["app_id"], status="SUBMITTED", submitted_at=now_utc(),
                       econsent_given=1, econsent_date=now_utc(), assigned_employee="jsmith")
    add_audit_entry(app3["app_id"], "STATUS_CHANGE", "DRAFT -> SUBMITTED", "sherlock@example.com")
    generate_initial_disclosure(app3["app_id"])

    update_application(app3["app_id"], status="IN_REVIEW")
    add_audit_entry(app3["app_id"], "STATUS_CHANGE", "SUBMITTED -> IN_REVIEW", "jsmith")

    update_application(app3["app_id"], status="UNDERWRITING")
    add_audit_entry(app3["app_id"], "STATUS_CHANGE", "IN_REVIEW -> UNDERWRITING", "jsmith")

    _run_uw_only(app3, "jsmith")

    # ── App 4: Just submitted (unassigned, waiting for pickup) ───────
    app4 = _create_app(
        address="350 Fifth Avenue", city="New York", state="NY", zip="10118",
        value=1200000, mortgage=600000, heloc=200000, purpose="Investment property down payment",
        autopay=True,
        borrower=("Tony", "Stark", "tony@example.com", "555-0005", "3000", 800),
        employer="Stark Industries", position="CEO", income=50000,
        assets=[("CHECKING", "Goldman Sachs", 2000000), ("INVESTMENT", "Schwab", 5000000)],
        debts=[("MORTGAGE", "JPMorgan", 4500, 600000), ("AUTO", "Mercedes Financial", 1200, 85000)],
        app_number=SEED_APP_NUMBERS[3],
    )
    update_application(app4["app_id"], status="SUBMITTED", submitted_at=now_utc(),
                       econsent_given=1, econsent_date=now_utc())
    add_audit_entry(app4["app_id"], "STATUS_CHANGE", "DRAFT -> SUBMITTED", "tony@example.com")
    generate_initial_disclosure(app4["app_id"])

    # ── App 5: In review (assigned, being worked) ────────────────────
    app5 = _create_app(
        address="12 Grimmauld Place", city="Salem", state="MA", zip="01970",
        value=550000, mortgage=220000, heloc=80000, purpose="Home repairs and updates",
        autopay=False,
        borrower=("Harry", "Potter", "harry@example.com", "555-0006", "9394", 735),
        coborrower=("Ginny", "Potter", "ginny@example.com", "555-0007", "9395", 750),
        employer="Ministry of Magic", position="Auror", income=8500,
        co_employer="Daily Prophet", co_position="Sports Editor", co_income=4500,
        assets=[("SAVINGS", "Gringotts", 350000), ("CHECKING", "Gringotts", 45000)],
        debts=[("MORTGAGE", "Diagon Alley Lending", 1650, 220000), ("STUDENT", "Hogwarts", 350, 12000)],
        app_number=SEED_APP_NUMBERS[4],
    )
    update_application(app5["app_id"], status="SUBMITTED", submitted_at=now_utc(),
                       econsent_given=1, econsent_date=now_utc(), assigned_employee="bwilson")
    add_audit_entry(app5["app_id"], "STATUS_CHANGE", "DRAFT -> SUBMITTED", "harry@example.com")
    generate_initial_disclosure(app5["app_id"])

    update_application(app5["app_id"], status="IN_REVIEW")
    add_audit_entry(app5["app_id"], "STATUS_CHANGE", "SUBMITTED -> IN_REVIEW", "bwilson")
    add_audit_entry(app5["app_id"], "ASSIGNED", "Assigned to bwilson", "bwilson")

    # Upload some docs for this one
    create_document(app5["app_id"], doc_type="PAYSTUB", filename="potter_paystub_jan2026.pdf",
                    uploaded_by="harry@example.com")
    create_document(app5["app_id"], doc_type="GOVT_ID", filename="potter_drivers_license.pdf",
                    uploaded_by="harry@example.com")


def _create_app(address, city, state, zip, value, mortgage, heloc, purpose, autopay,
                borrower, employer, position, income,
                coborrower=None, co_employer=None, co_position=None, co_income=None,
                assets=None, debts=None, app_number=None):
    """Helper to create an application with borrower, employment, assets, debts."""
    kwargs = dict(
        property_address=address, property_city=city, property_state=state,
        property_zip=zip, property_value=value, existing_mortgage_balance=mortgage,
        heloc_amount_requested=heloc, heloc_purpose=purpose, autopay_enrolled=int(autopay),
    )
    if app_number:
        kwargs["application_number"] = app_number
    app_id = create_application(**kwargs)

    first, last, email, phone, ssn4, score = borrower
    bid = create_borrower(app_id, is_primary=True, first_name=first, last_name=last,
                          email=email, phone=phone, ssn_last4=ssn4, credit_score=score)
    create_employment(bid, employer_name=employer, position=position, monthly_income=income,
                      years_employed=5.0)

    if coborrower:
        co_first, co_last, co_email, co_phone, co_ssn4, co_score = coborrower
        co_bid = create_borrower(app_id, is_primary=False, first_name=co_first, last_name=co_last,
                                 email=co_email, phone=co_phone, ssn_last4=co_ssn4, credit_score=co_score)
        if co_employer:
            create_employment(co_bid, employer_name=co_employer, position=co_position,
                              monthly_income=co_income, years_employed=3.0)

    if assets:
        for acct_type, institution, balance in assets:
            create_asset(bid, account_type=acct_type, institution=institution, balance=balance)

    if debts:
        for debt_type, creditor, payment, balance in debts:
            create_debt(bid, debt_type=debt_type, creditor=creditor,
                        monthly_payment=payment, balance=balance)

    add_audit_entry(app_id, "APPLICATION_CREATED", "Draft application created", email)

    return {"app_id": app_id, "primary_bid": bid, "value": value, "mortgage": mortgage,
            "heloc": heloc, "scores": [borrower[5]] + ([coborrower[5]] if coborrower else []),
            "total_income": income + (co_income or 0),
            "total_debts": sum(d[2] for d in debts) if debts else 0}


def _run_uw_and_pricing(app_data, employee):
    """Run underwriting and pricing for an application."""
    inp = UnderwritingInput(
        property_value=app_data["value"],
        existing_mortgage_balance=app_data["mortgage"],
        heloc_amount_requested=app_data["heloc"],
        credit_scores=app_data["scores"],
        total_monthly_income=app_data["total_income"],
        total_monthly_debts=app_data["total_debts"],
    )
    result = run_underwriting(inp)

    create_underwriting_decision(
        app_data["app_id"], decision=result.decision, ltv=result.ltv,
        cltv=result.cltv, dti=result.dti, highest_credit_score=result.highest_credit_score,
        reasons=json.dumps(result.hard_fails + result.warnings),
        conditions=json.dumps(result.conditions), decided_by=employee,
    )

    # Auto-create conditions
    if result.conditions:
        for c in result.conditions:
            create_condition(app_data["app_id"], condition_type="PRIOR_TO_CLOSING",
                             description=c, added_by="UW_ENGINE")

    status_map = {"APPROVE": "APPROVED", "APPROVE_WITH_CONDITIONS": "APPROVED_WITH_CONDITIONS",
                  "DENY": "DENIED"}
    new_status = status_map[result.decision]
    update_application(app_data["app_id"], status=new_status)
    add_audit_entry(app_data["app_id"], "UNDERWRITING_DECISION",
                    f"Engine decision: {result.decision}", employee)

    generate_decision_letter(app_data["app_id"])
    add_audit_entry(app_data["app_id"], "DOCUMENT_GENERATED", "Decision letter generated", employee)

    # Pricing
    pricing_inp = PricingInput(
        highest_credit_score=result.highest_credit_score,
        cltv=result.cltv,
        heloc_amount=app_data["heloc"],
        autopay_enrolled=True,
    )
    pricing = calculate_pricing(pricing_inp)
    from datetime import datetime, timedelta
    create_pricing_lock(
        app_data["app_id"], prime_rate=pricing.prime_rate, margin=pricing.margin,
        fico_adjustment=pricing.fico_adjustment, ltv_adjustment=pricing.ltv_adjustment,
        amount_adjustment=pricing.amount_adjustment, autopay_discount=pricing.autopay_discount,
        final_rate=pricing.final_rate, monthly_payment=pricing.monthly_payment,
        rate_locked=True, lock_date=now_utc(),
        lock_expiration=(datetime.utcnow() + timedelta(days=60)).isoformat(),
        locked_by=employee,
    )
    add_audit_entry(app_data["app_id"], "PRICING_CALCULATED",
                    f"Rate: {pricing.final_rate:.3f}%", employee)
    add_audit_entry(app_data["app_id"], "RATE_LOCKED",
                    f"Rate locked for 60 days", employee)


def _run_uw_only(app_data, employee):
    """Run underwriting only (for denied apps — no pricing needed)."""
    inp = UnderwritingInput(
        property_value=app_data["value"],
        existing_mortgage_balance=app_data["mortgage"],
        heloc_amount_requested=app_data["heloc"],
        credit_scores=app_data["scores"],
        total_monthly_income=app_data["total_income"],
        total_monthly_debts=app_data["total_debts"],
    )
    result = run_underwriting(inp)

    create_underwriting_decision(
        app_data["app_id"], decision=result.decision, ltv=result.ltv,
        cltv=result.cltv, dti=result.dti, highest_credit_score=result.highest_credit_score,
        reasons=json.dumps(result.hard_fails + result.warnings),
        conditions=json.dumps(result.conditions), decided_by=employee,
    )

    status_map = {"APPROVE": "APPROVED", "APPROVE_WITH_CONDITIONS": "APPROVED_WITH_CONDITIONS",
                  "DENY": "DENIED"}
    new_status = status_map[result.decision]
    update_application(app_data["app_id"], status=new_status)
    add_audit_entry(app_data["app_id"], "UNDERWRITING_DECISION",
                    f"Engine decision: {result.decision}", employee)

    generate_decision_letter(app_data["app_id"])
    add_audit_entry(app_data["app_id"], "DOCUMENT_GENERATED", "Decision letter generated", employee)
