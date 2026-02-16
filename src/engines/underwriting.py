"""Rules-based underwriting engine.

Pure function — takes application data, returns a decision with ratios and reasons.
No side effects: the caller is responsible for saving results to the database.

Reads thresholds from the config manager (DB-backed) so admin changes
take effect immediately.
"""

from dataclasses import dataclass, field

from src.config_manager import get_setting


@dataclass
class UnderwritingInput:
    """All the data the engine needs to make a decision."""
    property_value: float
    existing_mortgage_balance: float
    heloc_amount_requested: float
    credit_scores: list[int]           # One per borrower
    total_monthly_income: float        # Across all borrowers
    total_monthly_debts: float         # Existing obligations (excluding HELOC)


@dataclass
class UnderwritingOutput:
    """The engine's decision and supporting data."""
    decision: str = ""                 # APPROVE, APPROVE_WITH_CONDITIONS, DENY
    ltv: float = 0.0
    cltv: float = 0.0
    dti: float = 0.0
    highest_credit_score: int = 0
    hard_fails: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)


def run_underwriting(inp: UnderwritingInput) -> UnderwritingOutput:
    """Evaluate the application against all underwriting rules.

    Rules are checked in order. Hard fails result in DENY. Warnings
    result in APPROVE_WITH_CONDITIONS. Clean pass = APPROVE.
    """
    # Read all thresholds from DB-backed config
    min_credit_score = get_setting("min_credit_score")
    max_cltv = get_setting("max_cltv")
    max_dti = get_setting("max_dti")
    min_property_value = get_setting("min_property_value")
    min_heloc_amount = get_setting("min_heloc_amount")
    max_heloc_amount = get_setting("max_heloc_amount")
    prime_rate = get_setting("prime_rate")
    base_margin = get_setting("base_margin")

    out = UnderwritingOutput()

    # ── Rule 1: Credit Score ─────────────────────────────────────────
    scores = [s for s in inp.credit_scores if s > 0]
    if not scores:
        out.hard_fails.append("No valid credit score provided.")
    else:
        out.highest_credit_score = max(scores)
        if out.highest_credit_score < min_credit_score:
            out.hard_fails.append(
                f"Credit score {out.highest_credit_score} is below the "
                f"minimum of {min_credit_score}."
            )
        elif out.highest_credit_score < 720:
            out.warnings.append(
                f"Credit score {out.highest_credit_score} qualifies but "
                f"is below preferred threshold of 720."
            )

    # ── Rule 2: LTV (existing mortgage only) ─────────────────────────
    if inp.property_value > 0:
        out.ltv = inp.existing_mortgage_balance / inp.property_value
    else:
        out.hard_fails.append("Property value must be greater than zero.")

    # ── Rule 3: CLTV (mortgage + HELOC combined) ────────────────────
    if inp.property_value > 0:
        out.cltv = (inp.existing_mortgage_balance + inp.heloc_amount_requested) / inp.property_value
        if out.cltv > max_cltv:
            out.hard_fails.append(
                f"Combined LTV of {out.cltv:.1%} exceeds maximum of {max_cltv:.0%}. "
                f"Maximum HELOC amount at this property value: "
                f"${inp.property_value * max_cltv - inp.existing_mortgage_balance:,.0f}."
            )
        elif out.cltv > 0.70:
            out.warnings.append(
                f"Combined LTV of {out.cltv:.1%} is above 70%. "
                f"Higher pricing tier may apply."
            )

    # ── Rule 4: DTI ──────────────────────────────────────────────────
    estimated_heloc_rate = (prime_rate + base_margin) / 100
    estimated_heloc_payment = (inp.heloc_amount_requested * estimated_heloc_rate) / 12
    total_debts_with_heloc = inp.total_monthly_debts + estimated_heloc_payment

    if inp.total_monthly_income > 0:
        out.dti = total_debts_with_heloc / inp.total_monthly_income
        if out.dti > max_dti:
            out.hard_fails.append(
                f"Debt-to-income ratio of {out.dti:.1%} exceeds maximum of {max_dti:.0%}. "
                f"Monthly debts: ${total_debts_with_heloc:,.0f} "
                f"(includes ${estimated_heloc_payment:,.0f} estimated HELOC payment) "
                f"vs. income: ${inp.total_monthly_income:,.0f}."
            )
        elif out.dti > 0.38:
            out.warnings.append(
                f"DTI of {out.dti:.1%} is above 38%. Closely monitor borrower capacity."
            )
    else:
        out.hard_fails.append("No monthly income reported.")

    # ── Rule 5: Property value minimum ───────────────────────────────
    if 0 < inp.property_value < min_property_value:
        out.hard_fails.append(
            f"Property value of ${inp.property_value:,.0f} is below "
            f"minimum of ${min_property_value:,.0f}."
        )

    # ── Rule 6: HELOC amount range ───────────────────────────────────
    if inp.heloc_amount_requested < min_heloc_amount:
        out.hard_fails.append(
            f"HELOC amount ${inp.heloc_amount_requested:,.0f} is below "
            f"minimum of ${min_heloc_amount:,.0f}."
        )
    if inp.heloc_amount_requested > max_heloc_amount:
        out.hard_fails.append(
            f"HELOC amount ${inp.heloc_amount_requested:,.0f} exceeds "
            f"maximum of ${max_heloc_amount:,.0f}."
        )

    # ── Decision ─────────────────────────────────────────────────────
    if out.hard_fails:
        out.decision = "DENY"
    elif out.warnings:
        out.decision = "APPROVE_WITH_CONDITIONS"
        out.conditions = [
            f"Review required: {w}" for w in out.warnings
        ]
    else:
        out.decision = "APPROVE"

    return out
