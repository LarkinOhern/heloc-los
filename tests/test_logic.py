"""Pure-logic tests: formatting, engines, workflow rules."""

from datetime import datetime, timedelta

import pytest


# ── F-02: Central time must follow daylight saving ──────────────────────────

def test_fmt_datetime_uses_cdt_in_october():
    from src.utils.formatters import fmt_datetime
    # 11:31 UTC on Oct 17 is 6:31 AM CDT (UTC-5), not 5:31.
    assert fmt_datetime("2026-10-17T11:31:13") == "Oct 17, 2026 06:31 AM CT"


def test_fmt_datetime_uses_cst_in_january():
    from src.utils.formatters import fmt_datetime
    assert fmt_datetime("2026-01-15T12:00:00") == "Jan 15, 2026 06:00 AM CT"


def test_fmt_date_rolls_back_across_midnight():
    from src.utils.formatters import fmt_date
    # 03:00 UTC on Oct 18 is still Oct 17 in Chicago.
    assert fmt_date("2026-10-18T03:00:00") == "Oct 17, 2026"


# ── F-03: a fresh 60-day lock shows 60 days ─────────────────────────────────

def test_days_remaining_counts_partial_days():
    from src.utils.formatters import days_remaining
    now = datetime(2026, 10, 17, 11, 36, 0)
    expires = (now + timedelta(days=60)).isoformat()
    assert days_remaining(expires, now=now + timedelta(seconds=5)) == 60


def test_days_remaining_is_zero_after_expiry():
    from src.utils.formatters import days_remaining
    now = datetime(2026, 12, 17)
    assert days_remaining("2026-12-16T11:36:00", now=now) == 0


# ── Engines: lock in the numbers verified by hand in Round 0 ────────────────

def test_maria_underwriting_matches_round0(db):
    from src.engines.underwriting import UnderwritingInput, run_underwriting
    out = run_underwriting(UnderwritingInput(
        property_value=450_000, existing_mortgage_balance=250_000,
        heloc_amount_requested=75_000, credit_scores=[745],
        total_monthly_income=9_500, total_monthly_debts=1_900,
    ))
    assert out.decision == "APPROVE_WITH_CONDITIONS"
    assert out.ltv == pytest.approx(0.5556, abs=1e-4)
    assert out.cltv == pytest.approx(0.7222, abs=1e-4)
    assert out.dti == pytest.approx(0.2559, abs=1e-4)


def test_tony_denied_under_65_cltv_cap(db):
    from src.config_manager import set_setting
    from src.engines.underwriting import UnderwritingInput, run_underwriting
    set_setting("max_cltv", 0.65)
    out = run_underwriting(UnderwritingInput(
        property_value=1_200_000, existing_mortgage_balance=600_000,
        heloc_amount_requested=200_000, credit_scores=[800],
        total_monthly_income=25_000, total_monthly_debts=2_140,
    ))
    assert out.decision == "DENY"
    assert any("$180,000" in r for r in out.hard_fails)


def test_maria_pricing_matches_round0(db):
    from src.engines.pricing import PricingInput, calculate_pricing
    out = calculate_pricing(PricingInput(
        highest_credit_score=745, cltv=325_000 / 450_000,
        heloc_amount=75_000, autopay_enrolled=True,
    ))
    assert out.final_rate == pytest.approx(8.5)
    assert out.monthly_payment == pytest.approx(531.25)


# ── F-04: amount tier labels read as ranges and never start with ">" ───────

@pytest.mark.parametrize("amount,label", [
    (75_000, "Under $100,000"),
    (150_000, "$100,000 to $249,999"),
    (300_000, "$250,000 and up"),
])
def test_amount_tier_labels(db, amount, label):
    from src.engines.pricing import PricingInput, calculate_pricing
    out = calculate_pricing(PricingInput(
        highest_credit_score=745, cltv=0.7, heloc_amount=amount, autopay_enrolled=False,
    ))
    assert out.amount_tier == label


# ── C-03: closing and funding are blocked by open conditions ────────────────

def _cond(ctype, status="OPEN"):
    return {"id": 1, "condition_type": ctype, "status": status, "description": "x"}


def test_closing_blocked_by_open_prior_to_closing():
    from src.engines.workflow import blocking_conditions
    blockers = blocking_conditions("CLOSING", [_cond("PRIOR_TO_CLOSING")])
    assert len(blockers) == 1


def test_closing_not_blocked_by_prior_to_funding():
    from src.engines.workflow import blocking_conditions
    assert blocking_conditions("CLOSING", [_cond("PRIOR_TO_FUNDING")]) == []


def test_funding_blocked_by_any_open_condition():
    from src.engines.workflow import blocking_conditions
    conds = [_cond("PRIOR_TO_CLOSING"), _cond("PRIOR_TO_FUNDING")]
    assert len(blocking_conditions("FUNDED", conds)) == 2


def test_resolved_conditions_never_block():
    from src.engines.workflow import blocking_conditions
    conds = [_cond("PRIOR_TO_CLOSING", "SATISFIED"), _cond("PRIOR_TO_FUNDING", "WAIVED")]
    assert blocking_conditions("FUNDED", conds) == []


# ── C-01: the borrower timeline hides internal events ──────────────────────

def test_borrower_timeline_hides_internal_events():
    from src.utils.timeline import borrower_timeline
    entries = [
        {"action": "APPLICATION_CREATED", "details": "Draft application created", "performed_by": "m@x.com", "performed_at": "2026-10-17T11:24:00"},
        {"action": "STATUS_CHANGE", "details": "Status changed from DRAFT to SUBMITTED", "performed_by": "m@x.com", "performed_at": "2026-10-17T11:31:00"},
        {"action": "ASSIGNED", "details": "Assigned to jsmith", "performed_by": "jsmith", "performed_at": "2026-10-17T11:35:00"},
        {"action": "UNDERWRITING_DECISION", "details": "Engine decision: APPROVE_WITH_CONDITIONS. Status changed from UNDERWRITING to APPROVED_WITH_CONDITIONS.", "performed_by": "jsmith", "performed_at": "2026-10-17T11:35:00"},
        {"action": "PRICING_CALCULATED", "details": "Rate calculated: 8.500%", "performed_by": "jsmith", "performed_at": "2026-10-17T11:36:00"},
        {"action": "CONDITION_WAIVED", "details": "Condition waived: Review required: Combined LTV of 72.2% is above 70%.", "performed_by": "jsmith", "performed_at": "2026-10-17T11:37:00"},
        {"action": "RATE_LOCKED", "details": "Rate of 8.500% locked for 60 days (expires 2026-12-16)", "performed_by": "jsmith", "performed_at": "2026-10-17T11:36:30"},
    ]
    items = borrower_timeline(entries)
    text = " ".join(f"{i['title']} {i['detail']}" for i in items)
    assert "jsmith" not in text
    assert "Engine" not in text
    assert "waived" not in text.lower()
    assert "Combined LTV" not in text
    titles = [i["title"] for i in items]
    assert "Application submitted" in titles
    assert "Decision: Approved with conditions" in titles
    assert "Rate locked" in titles


def test_borrower_timeline_understands_seed_arrow_format():
    from src.utils.timeline import borrower_timeline
    items = borrower_timeline([{"action": "STATUS_CHANGE", "details": "IN_REVIEW → UNDERWRITING",
                                "performed_by": "", "performed_at": "2026-10-17T11:00:00"}])
    assert items[0]["title"] == "Status: Underwriting"
