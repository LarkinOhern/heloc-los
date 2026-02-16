"""All constants, thresholds, pricing tables, and configuration."""

# ── Lender Info ──────────────────────────────────────────────────────────────
LENDER_NAME = "Acme Home Lending"
LENDER_ADDRESS = "123 Main Street, Suite 100, Springfield, IL 62701"
LENDER_NMLS = "1234567"
LENDER_PHONE = "(555) 123-4567"

# ── Application Number ──────────────────────────────────────────────────────
APP_NUMBER_PREFIX = "HELOC"
APP_NUMBER_YEAR = 2026

# ── Property Types ───────────────────────────────────────────────────────────
PROPERTY_TYPES = [
    "PRIMARY_RESIDENCE",
]

PROPERTY_TYPE_LABELS = {
    "PRIMARY_RESIDENCE": "Primary Residence",
}

# ── Underwriting Thresholds ──────────────────────────────────────────────────
MIN_CREDIT_SCORE = 680
MAX_CLTV = 0.80          # 80%
MAX_DTI = 0.43            # 43%
MIN_PROPERTY_VALUE = 50_000
MIN_HELOC_AMOUNT = 10_000
MAX_HELOC_AMOUNT = 500_000

CREDIT_TIERS = [
    {"label": "Excellent", "min_score": 760, "max_score": 850, "rate_adjustment": -0.50},
    {"label": "Good",      "min_score": 720, "max_score": 759, "rate_adjustment": -0.25},
    {"label": "Fair",      "min_score": 680, "max_score": 719, "rate_adjustment":  0.00},
]

# ── Pricing ──────────────────────────────────────────────────────────────────
PRIME_RATE = 8.50          # Current prime rate %
BASE_MARGIN = 0.00         # Added to prime

# FICO tier adjustments — kept for backward compat but credit_tiers is the
# source of truth. The pricing engine reads from credit_tiers via config manager.
FICO_ADJUSTMENTS = [
    {"min_score": 760, "adjustment": -0.50},
    {"min_score": 720, "adjustment": -0.25},
    {"min_score": 680, "adjustment":  0.00},
]

# LTV tier adjustments
LTV_ADJUSTMENTS = [
    {"max_ltv": 0.60, "adjustment": -0.25},
    {"max_ltv": 0.70, "adjustment":  0.00},
    {"max_ltv": 0.80, "adjustment":  0.25},
]

# HELOC amount tier adjustments
AMOUNT_ADJUSTMENTS = [
    {"min_amount": 250_000, "adjustment": -0.25},
    {"min_amount": 100_000, "adjustment":  0.00},
    {"min_amount":       0, "adjustment":  0.25},
]

AUTOPAY_DISCOUNT = 0.25   # % discount for autopay enrollment
RATE_LOCK_DAYS = 60
RATE_FLOOR = 5.00          # Minimum rate %
RATE_CEILING = 18.00       # Maximum rate %

# ── Workflow ─────────────────────────────────────────────────────────────────
STATUSES = [
    "DRAFT",
    "SUBMITTED",
    "IN_REVIEW",
    "UNDERWRITING",
    "APPROVED",
    "APPROVED_WITH_CONDITIONS",
    "DENIED",
    "CLOSING",
    "FUNDED",
    "WITHDRAWN",
]

# Valid status transitions: from_status -> [allowed to_statuses]
VALID_TRANSITIONS = {
    "DRAFT":                     ["SUBMITTED", "WITHDRAWN"],
    "SUBMITTED":                 ["IN_REVIEW", "WITHDRAWN"],
    "IN_REVIEW":                 ["UNDERWRITING", "WITHDRAWN"],
    "UNDERWRITING":              ["APPROVED", "APPROVED_WITH_CONDITIONS", "DENIED"],
    "APPROVED":                  ["CLOSING", "WITHDRAWN"],
    "APPROVED_WITH_CONDITIONS":  ["CLOSING", "DENIED", "WITHDRAWN"],
    "DENIED":                    [],
    "CLOSING":                   ["FUNDED", "WITHDRAWN"],
    "FUNDED":                    [],
    "WITHDRAWN":                 [],
}

STATUS_COLORS = {
    "DRAFT":                     "#9e9e9e",
    "SUBMITTED":                 "#2196f3",
    "IN_REVIEW":                 "#ff9800",
    "UNDERWRITING":              "#9c27b0",
    "APPROVED":                  "#4caf50",
    "APPROVED_WITH_CONDITIONS":  "#8bc34a",
    "DENIED":                    "#f44336",
    "CLOSING":                   "#00bcd4",
    "FUNDED":                    "#009688",
    "WITHDRAWN":                 "#607d8b",
}

STATUS_LABELS = {
    "DRAFT":                     "Draft",
    "SUBMITTED":                 "Submitted",
    "IN_REVIEW":                 "In Review",
    "UNDERWRITING":              "Underwriting",
    "APPROVED":                  "Approved",
    "APPROVED_WITH_CONDITIONS":  "Approved w/ Conditions",
    "DENIED":                    "Denied",
    "CLOSING":                   "Closing",
    "FUNDED":                    "Funded",
    "WITHDRAWN":                 "Withdrawn",
}

# ── Document Requirements ────────────────────────────────────────────────────
REQUIRED_DOCUMENTS = [
    {"type": "PAYSTUB",          "label": "Recent Pay Stub (30 days)"},
    {"type": "W2",               "label": "W-2 (most recent 2 years)"},
    {"type": "TAX_RETURN",       "label": "Federal Tax Return (most recent 2 years)"},
    {"type": "BANK_STATEMENT",   "label": "Bank Statement (most recent 2 months)"},
    {"type": "MORTGAGE_STMT",    "label": "Current Mortgage Statement"},
    {"type": "HOMEOWNERS_INS",   "label": "Homeowners Insurance Declaration"},
    {"type": "GOVT_ID",          "label": "Government-Issued Photo ID"},
]

GENERATED_DOC_TYPES = [
    "INITIAL_DISCLOSURE",
    "APPROVAL_LETTER",
    "DENIAL_LETTER",
    "CLOSING_DOCUMENTS",
]

# ── Employee List (hardcoded for prototype) ──────────────────────────────────
EMPLOYEES = [
    {"username": "jsmith",   "display_name": "Jane Smith",   "role": "Loan Officer"},
    {"username": "bwilson",  "display_name": "Bob Wilson",   "role": "Loan Officer"},
    {"username": "admin",    "display_name": "Admin User",   "role": "Admin"},
]
