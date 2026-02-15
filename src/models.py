"""Dataclasses for the HELOC LOS domain objects."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Borrower:
    id: Optional[int] = None
    application_id: Optional[int] = None
    is_primary: bool = True
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    ssn_last4: str = ""
    date_of_birth: str = ""
    credit_score: int = 0  # Self-reported
    citizenship: str = "US_CITIZEN"


@dataclass
class Employment:
    id: Optional[int] = None
    borrower_id: Optional[int] = None
    employer_name: str = ""
    position: str = ""
    years_employed: float = 0.0
    monthly_income: float = 0.0
    income_type: str = "SALARY"  # SALARY, HOURLY, SELF_EMPLOYED, RETIREMENT, OTHER


@dataclass
class Asset:
    id: Optional[int] = None
    borrower_id: Optional[int] = None
    account_type: str = ""   # CHECKING, SAVINGS, INVESTMENT, RETIREMENT, OTHER
    institution: str = ""
    balance: float = 0.0


@dataclass
class Debt:
    id: Optional[int] = None
    borrower_id: Optional[int] = None
    debt_type: str = ""      # MORTGAGE, AUTO, STUDENT, CREDIT_CARD, PERSONAL, OTHER
    creditor: str = ""
    monthly_payment: float = 0.0
    balance: float = 0.0


@dataclass
class Application:
    id: Optional[int] = None
    application_number: str = ""
    status: str = "DRAFT"
    # Property info
    property_address: str = ""
    property_city: str = ""
    property_state: str = ""
    property_zip: str = ""
    property_type: str = "PRIMARY_RESIDENCE"
    property_value: float = 0.0
    existing_mortgage_balance: float = 0.0
    # HELOC request
    heloc_amount_requested: float = 0.0
    heloc_purpose: str = ""
    autopay_enrolled: bool = False
    # E-consent
    econsent_given: bool = False
    econsent_date: Optional[str] = None
    # Assignment
    assigned_employee: Optional[str] = None
    # Timestamps
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    submitted_at: Optional[str] = None


@dataclass
class UnderwritingResult:
    id: Optional[int] = None
    application_id: Optional[int] = None
    decision: str = ""       # APPROVE, APPROVE_WITH_CONDITIONS, DENY
    ltv: float = 0.0
    cltv: float = 0.0
    dti: float = 0.0
    highest_credit_score: int = 0
    reasons: str = ""        # JSON list of reason strings
    conditions: str = ""     # JSON list of condition strings
    decided_by: str = ""
    decided_at: Optional[str] = None


@dataclass
class PricingResult:
    id: Optional[int] = None
    application_id: Optional[int] = None
    prime_rate: float = 0.0
    margin: float = 0.0
    fico_adjustment: float = 0.0
    ltv_adjustment: float = 0.0
    amount_adjustment: float = 0.0
    autopay_discount: float = 0.0
    final_rate: float = 0.0
    monthly_payment: float = 0.0    # Interest-only
    rate_locked: bool = False
    lock_date: Optional[str] = None
    lock_expiration: Optional[str] = None
    locked_by: str = ""


@dataclass
class Condition:
    id: Optional[int] = None
    application_id: Optional[int] = None
    condition_type: str = ""     # PRIOR_TO_CLOSING, PRIOR_TO_FUNDING
    description: str = ""
    status: str = "OPEN"         # OPEN, SATISFIED, WAIVED
    added_by: str = ""
    added_at: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None


@dataclass
class Document:
    id: Optional[int] = None
    application_id: Optional[int] = None
    doc_type: str = ""
    filename: str = ""
    uploaded_by: str = ""
    uploaded_at: Optional[str] = None


@dataclass
class GeneratedDocument:
    id: Optional[int] = None
    application_id: Optional[int] = None
    doc_type: str = ""
    filename: str = ""
    generated_at: Optional[str] = None


@dataclass
class AuditEntry:
    id: Optional[int] = None
    application_id: Optional[int] = None
    action: str = ""
    details: str = ""
    performed_by: str = ""
    performed_at: Optional[str] = None
