"""Risk-based pricing engine for HELOC rates.

Pure function — takes application data and returns a pricing breakdown.
The rate starts at Prime + margin, then adjusts based on FICO, LTV, and
line amount tiers. Autopay discount is applied last before clamping.
"""

from dataclasses import dataclass

from src.config import (
    PRIME_RATE, BASE_MARGIN,
    FICO_ADJUSTMENTS, LTV_ADJUSTMENTS, AMOUNT_ADJUSTMENTS,
    AUTOPAY_DISCOUNT, RATE_FLOOR, RATE_CEILING,
)


@dataclass
class PricingInput:
    """All the data the pricing engine needs."""
    highest_credit_score: int
    cltv: float                      # Combined LTV as a decimal (e.g. 0.75)
    heloc_amount: float
    autopay_enrolled: bool


@dataclass
class PricingOutput:
    """Full pricing breakdown so the employee can see every component."""
    prime_rate: float = 0.0
    margin: float = 0.0
    fico_adjustment: float = 0.0
    ltv_adjustment: float = 0.0
    amount_adjustment: float = 0.0
    autopay_discount: float = 0.0
    final_rate: float = 0.0
    monthly_payment: float = 0.0     # Interest-only at full draw


def calculate_pricing(inp: PricingInput) -> PricingOutput:
    """Calculate the HELOC rate and monthly payment.

    Each adjustment tier is checked in order (best tier first), and the
    first match is used. This means the tiers must be sorted from most
    favorable to least favorable in config.py.
    """
    out = PricingOutput()
    out.prime_rate = PRIME_RATE
    out.margin = BASE_MARGIN

    # ── FICO Adjustment ──────────────────────────────────────────────
    # Tiers are sorted best-first (760+, 720+, 680+). We take the first
    # tier where the borrower's score meets the minimum.
    for tier in FICO_ADJUSTMENTS:
        if inp.highest_credit_score >= tier["min_score"]:
            out.fico_adjustment = tier["adjustment"]
            break

    # ── LTV Adjustment ───────────────────────────────────────────────
    # Tiers are sorted by max_ltv ascending. Lower LTV = better rate.
    for tier in LTV_ADJUSTMENTS:
        if inp.cltv <= tier["max_ltv"]:
            out.ltv_adjustment = tier["adjustment"]
            break
    else:
        # If CLTV exceeds all tiers, use the worst (last) tier
        out.ltv_adjustment = LTV_ADJUSTMENTS[-1]["adjustment"]

    # ── Amount Adjustment ────────────────────────────────────────────
    # Tiers are sorted largest-first. Bigger lines get better pricing
    # because the lender earns more interest revenue.
    for tier in AMOUNT_ADJUSTMENTS:
        if inp.heloc_amount >= tier["min_amount"]:
            out.amount_adjustment = tier["adjustment"]
            break

    # ── Autopay Discount ─────────────────────────────────────────────
    if inp.autopay_enrolled:
        out.autopay_discount = AUTOPAY_DISCOUNT

    # ── Final Rate ───────────────────────────────────────────────────
    raw_rate = (
        out.prime_rate
        + out.margin
        + out.fico_adjustment
        + out.ltv_adjustment
        + out.amount_adjustment
        - out.autopay_discount
    )
    out.final_rate = max(RATE_FLOOR, min(RATE_CEILING, raw_rate))

    # ── Monthly Payment (Interest-Only) ──────────────────────────────
    # Standard interest-only calc: (balance * annual_rate) / 12
    # Assumes full draw of the HELOC line.
    out.monthly_payment = (inp.heloc_amount * (out.final_rate / 100)) / 12

    return out
