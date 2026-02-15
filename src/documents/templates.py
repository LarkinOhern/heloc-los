"""Document content templates — text and structure for each generated PDF.

Each template function returns a list of sections, where each section is a
dict with 'heading' and 'lines' (list of strings). The generator renders
these into a formatted PDF.
"""

from src.config import LENDER_NAME, LENDER_ADDRESS, LENDER_NMLS, LENDER_PHONE
from src.utils.formatters import fmt_currency, fmt_date, fmt_rate, fmt_percent


def initial_disclosure(app: dict, borrower: dict) -> list[dict]:
    """Truth-in-Lending style initial disclosure generated on submission."""
    return [
        {
            "heading": "IMPORTANT DISCLOSURE — PLEASE READ CAREFULLY",
            "lines": [
                f"Application Number: {app['application_number']}",
                f"Date: {fmt_date(app['submitted_at'])}",
                f"Borrower: {borrower['first_name']} {borrower['last_name']}",
            ],
        },
        {
            "heading": "LOAN SUMMARY",
            "lines": [
                f"Product Type: Home Equity Line of Credit (HELOC)",
                f"Credit Line Amount Requested: {fmt_currency(app['heloc_amount_requested'])}",
                f"Property Address: {app['property_address']}, {app['property_city']}, "
                f"{app['property_state']} {app['property_zip']}",
                f"Property Value (Estimated): {fmt_currency(app['property_value'])}",
                f"Existing Mortgage Balance: {fmt_currency(app['existing_mortgage_balance'])}",
            ],
        },
        {
            "heading": "RATE INFORMATION",
            "lines": [
                "Your HELOC features a VARIABLE interest rate tied to the Prime Rate.",
                "The rate is determined by Prime + Margin, adjusted for credit profile,",
                "loan-to-value ratio, and line amount. The exact rate will be provided",
                "upon underwriting approval.",
                "",
                f"Autopay Enrollment: {'Yes (0.25% discount applied)' if app['autopay_enrolled'] else 'No'}",
            ],
        },
        {
            "heading": "KEY TERMS",
            "lines": [
                "Draw Period: 10 years from closing date.",
                "Repayment Period: 20 years following the draw period.",
                "During the draw period, minimum payments are interest-only.",
                "During the repayment period, payments include principal and interest.",
                "You may pay more than the minimum at any time without penalty.",
            ],
        },
        {
            "heading": "DISCLOSURES",
            "lines": [
                "This is an application disclosure, not a commitment to lend.",
                "Final terms are subject to underwriting approval.",
                "Your property serves as collateral for this line of credit.",
                "Failure to repay may result in foreclosure on your property.",
                "",
                f"E-Consent: {'Provided' if app['econsent_given'] else 'Not provided'} "
                f"on {fmt_date(app['econsent_date'])}",
            ],
        },
    ]


def approval_letter(app: dict, borrower: dict, decision: dict, pricing: dict | None) -> list[dict]:
    """Approval letter generated after a positive UW decision."""
    sections = [
        {
            "heading": "APPROVAL NOTIFICATION",
            "lines": [
                f"Date: {fmt_date(decision['decided_at'])}",
                f"Application Number: {app['application_number']}",
                f"Borrower: {borrower['first_name']} {borrower['last_name']}",
                "",
                "Congratulations! Your Home Equity Line of Credit application",
                "has been approved subject to the terms outlined below.",
            ],
        },
        {
            "heading": "APPROVED TERMS",
            "lines": [
                f"Credit Line Amount: {fmt_currency(app['heloc_amount_requested'])}",
                f"Property: {app['property_address']}, {app['property_city']}, "
                f"{app['property_state']} {app['property_zip']}",
                f"Combined Loan-to-Value: {fmt_percent(decision['cltv'])}",
                f"Debt-to-Income Ratio: {fmt_percent(decision['dti'])}",
            ],
        },
    ]

    if pricing:
        sections.append({
            "heading": "RATE AND PAYMENT",
            "lines": [
                f"Interest Rate: {fmt_rate(pricing['final_rate'])}",
                f"Estimated Monthly Payment (Interest-Only): {fmt_currency(pricing['monthly_payment'])}",
                f"Rate Lock: {'Yes' if pricing['rate_locked'] else 'No'}",
                f"{'Lock Expiration: ' + fmt_date(pricing['lock_expiration']) if pricing['rate_locked'] else ''}",
            ],
        })

    import json
    conditions = json.loads(decision.get("conditions", "[]"))
    if conditions:
        sections.append({
            "heading": "CONDITIONS",
            "lines": [
                "The following conditions must be satisfied prior to closing:",
                "",
            ] + [f"  - {c}" for c in conditions],
        })

    sections.append({
        "heading": "NEXT STEPS",
        "lines": [
            "1. Review and satisfy any outstanding conditions listed above.",
            "2. Upload required documentation through the borrower portal.",
            "3. Your loan officer will contact you to schedule closing.",
            "",
            f"For questions, contact us at {LENDER_PHONE}.",
        ],
    })

    return sections


def denial_letter(app: dict, borrower: dict, decision: dict) -> list[dict]:
    """Adverse action notice generated after a DENY decision."""
    import json
    reasons = json.loads(decision.get("reasons", "[]"))

    return [
        {
            "heading": "NOTICE OF ADVERSE ACTION",
            "lines": [
                f"Date: {fmt_date(decision['decided_at'])}",
                f"Application Number: {app['application_number']}",
                f"Borrower: {borrower['first_name']} {borrower['last_name']}",
                "",
                "After careful review of your application for a Home Equity",
                "Line of Credit, we are unable to approve your request at this time.",
            ],
        },
        {
            "heading": "REASON(S) FOR DENIAL",
            "lines": [f"  - {r}" for r in reasons] if reasons else [
                "  - Application did not meet underwriting requirements."
            ],
        },
        {
            "heading": "YOUR RIGHTS",
            "lines": [
                "Under the Equal Credit Opportunity Act, you have the right to",
                "know why your application was denied. The reasons are listed above.",
                "",
                "You have the right to obtain a free copy of your credit report",
                "within 60 days from each credit reporting agency.",
                "",
                "If you believe this decision was made in error, you may contact",
                f"us at {LENDER_PHONE} to discuss your application.",
            ],
        },
    ]


def closing_documents(app: dict, borrower: dict, pricing: dict | None) -> list[dict]:
    """Closing document package generated when status moves to CLOSING."""
    sections = [
        {
            "heading": "CLOSING DISCLOSURE",
            "lines": [
                f"Application Number: {app['application_number']}",
                f"Borrower: {borrower['first_name']} {borrower['last_name']}",
                f"Property: {app['property_address']}, {app['property_city']}, "
                f"{app['property_state']} {app['property_zip']}",
            ],
        },
        {
            "heading": "FINAL LOAN TERMS",
            "lines": [
                f"Product: Home Equity Line of Credit (HELOC)",
                f"Credit Line Amount: {fmt_currency(app['heloc_amount_requested'])}",
                f"Draw Period: 10 years",
                f"Repayment Period: 20 years",
            ],
        },
    ]

    if pricing:
        sections.append({
            "heading": "RATE AND PAYMENT SUMMARY",
            "lines": [
                f"Interest Rate: {fmt_rate(pricing['final_rate'])} (variable)",
                f"Estimated Monthly Payment: {fmt_currency(pricing['monthly_payment'])}",
                f"Payment Type: Interest-only during draw period",
                "",
                "Note: Your rate is variable and will adjust with the Prime Rate.",
                "Your actual payment may differ based on draws and rate changes.",
            ],
        })

    sections.append({
        "heading": "BORROWER ACKNOWLEDGMENT",
        "lines": [
            "By proceeding to closing, you acknowledge that:",
            "  - You have received and reviewed all required disclosures.",
            "  - Your property serves as collateral for this line of credit.",
            "  - You understand the terms and conditions of this HELOC.",
            "",
            f"Lender: {LENDER_NAME}",
            f"Address: {LENDER_ADDRESS}",
            f"NMLS: {LENDER_NMLS}",
        ],
    })

    return sections
