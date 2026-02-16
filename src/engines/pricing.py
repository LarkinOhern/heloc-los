"""Risk-based pricing engine for HELOC rates.

Pure function — takes application data and returns a pricing breakdown.
Reads rate tables from the config manager (DB-backed) so admin changes
take effect immediately.
"""

from dataclasses import dataclass

from src.config_manager import get_setting


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
    fico_tier: str = ""              # e.g. "Excellent (760-850)"
    ltv_adjustment: float = 0.0
    ltv_tier: str = ""               # e.g. "CLTV <= 60%"
    amount_adjustment: float = 0.0
    amount_tier: str = ""            # e.g. ">= $250,000"
    autopay_discount: float = 0.0
    final_rate: float = 0.0
    monthly_payment: float = 0.0     # Interest-only at full draw


def calculate_pricing(inp: PricingInput) -> PricingOutput:
    """Calculate the HELOC rate and monthly payment.

    Each adjustment tier is checked in order (best tier first), and the
    first match is used.
    """
    # Read all pricing config from DB
    prime_rate = get_setting("prime_rate")
    base_margin = get_setting("base_margin")
    fico_adjustments = get_setting("fico_adjustments")
    ltv_adjustments = get_setting("ltv_adjustments")
    amount_adjustments = get_setting("amount_adjustments")
    autopay_discount = get_setting("autopay_discount")
    rate_floor = get_setting("rate_floor")
    rate_ceiling = get_setting("rate_ceiling")

    out = PricingOutput()
    out.prime_rate = prime_rate
    out.margin = base_margin

    # ── FICO Adjustment ──────────────────────────────────────────────
    # credit_tiers has labels; fico_adjustments is derived from them.
    credit_tiers = get_setting("credit_tiers")
    for tier in credit_tiers:
        if inp.highest_credit_score >= tier["min_score"]:
            out.fico_adjustment = tier["rate_adjustment"]
            out.fico_tier = f"{tier['label']} ({tier['min_score']}-{tier['max_score']})"
            break

    # ── LTV Adjustment ───────────────────────────────────────────────
    for tier in ltv_adjustments:
        if inp.cltv <= tier["max_ltv"]:
            out.ltv_adjustment = tier["adjustment"]
            out.ltv_tier = f"CLTV <= {tier['max_ltv']:.0%}"
            break
    else:
        out.ltv_adjustment = ltv_adjustments[-1]["adjustment"]
        out.ltv_tier = f"CLTV <= {ltv_adjustments[-1]['max_ltv']:.0%}"

    # ── Amount Adjustment ────────────────────────────────────────────
    for tier in amount_adjustments:
        if inp.heloc_amount >= tier["min_amount"]:
            out.amount_adjustment = tier["adjustment"]
            out.amount_tier = f">= ${tier['min_amount']:,.0f}"
            break

    # ── Autopay Discount ─────────────────────────────────────────────
    if inp.autopay_enrolled:
        out.autopay_discount = autopay_discount

    # ── Final Rate ───────────────────────────────────────────────────
    raw_rate = (
        out.prime_rate
        + out.margin
        + out.fico_adjustment
        + out.ltv_adjustment
        + out.amount_adjustment
        - out.autopay_discount
    )
    out.final_rate = max(rate_floor, min(rate_ceiling, raw_rate))

    # ── Monthly Payment (Interest-Only) ──────────────────────────────
    out.monthly_payment = (inp.heloc_amount * (out.final_rate / 100)) / 12

    return out
