"""CRUD functions for all database tables."""

import json
from typing import Optional

from src.database import get_connection
from src.config import APP_NUMBER_PREFIX, APP_NUMBER_YEAR
from src.utils.formatters import now_utc


# ── Application Number Generation ────────────────────────────────────────────

def generate_application_number() -> str:
    """Generate next application number like HELOC-2026-000001."""
    conn = get_connection()
    row = conn.execute(
        "SELECT MAX(id) as max_id FROM applications"
    ).fetchone()
    conn.close()
    next_id = (row["max_id"] or 0) + 1
    return f"{APP_NUMBER_PREFIX}-{APP_NUMBER_YEAR}-{next_id:06d}"


# ── Applications ─────────────────────────────────────────────────────────────

def create_application(**kwargs) -> int:
    """Create a new application and return its id."""
    now = now_utc()
    app_number = generate_application_number()
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO applications
           (application_number, status, property_address, property_city,
            property_state, property_zip, property_type, property_value,
            existing_mortgage_balance, heloc_amount_requested, heloc_purpose,
            autopay_enrolled, econsent_given, econsent_date,
            assigned_employee, created_at, updated_at, submitted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            app_number,
            kwargs.get("status", "DRAFT"),
            kwargs.get("property_address", ""),
            kwargs.get("property_city", ""),
            kwargs.get("property_state", ""),
            kwargs.get("property_zip", ""),
            kwargs.get("property_type", "PRIMARY_RESIDENCE"),
            kwargs.get("property_value", 0),
            kwargs.get("existing_mortgage_balance", 0),
            kwargs.get("heloc_amount_requested", 0),
            kwargs.get("heloc_purpose", ""),
            int(kwargs.get("autopay_enrolled", False)),
            int(kwargs.get("econsent_given", False)),
            kwargs.get("econsent_date"),
            kwargs.get("assigned_employee"),
            now,
            now,
            kwargs.get("submitted_at"),
        ),
    )
    app_id = cur.lastrowid
    conn.commit()
    conn.close()
    return app_id


def get_application(app_id: int) -> Optional[dict]:
    """Get a single application by id."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_application_by_number(app_number: str) -> Optional[dict]:
    """Get a single application by application_number."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM applications WHERE application_number = ?", (app_number,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_applications_by_email(email: str) -> list[dict]:
    """Get all applications where the primary borrower has the given email."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.* FROM applications a
           JOIN borrowers b ON b.application_id = a.id
           WHERE b.email = ? AND b.is_primary = 1
           ORDER BY a.created_at DESC""",
        (email,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_applications() -> list[dict]:
    """Get all applications ordered by most recent first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM applications ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_application(app_id: int, **kwargs):
    """Update an application's fields."""
    kwargs["updated_at"] = now_utc()
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [app_id]
    conn = get_connection()
    conn.execute(f"UPDATE applications SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


# ── Borrowers ────────────────────────────────────────────────────────────────

def create_borrower(application_id: int, is_primary: bool = True, **kwargs) -> int:
    """Create a borrower record and return its id."""
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO borrowers
           (application_id, is_primary, first_name, last_name, email, phone,
            ssn_last4, date_of_birth, credit_score, citizenship)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            application_id,
            int(is_primary),
            kwargs.get("first_name", ""),
            kwargs.get("last_name", ""),
            kwargs.get("email", ""),
            kwargs.get("phone", ""),
            kwargs.get("ssn_last4", ""),
            kwargs.get("date_of_birth", ""),
            kwargs.get("credit_score", 0),
            kwargs.get("citizenship", "US_CITIZEN"),
        ),
    )
    borrower_id = cur.lastrowid
    conn.commit()
    conn.close()
    return borrower_id


def get_borrowers(application_id: int) -> list[dict]:
    """Get all borrowers for an application."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM borrowers WHERE application_id = ? ORDER BY is_primary DESC",
        (application_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_borrower(borrower_id: int, **kwargs):
    """Update a borrower's fields."""
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [borrower_id]
    conn = get_connection()
    conn.execute(f"UPDATE borrowers SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def delete_borrower(borrower_id: int):
    """Delete a borrower and their related records."""
    conn = get_connection()
    conn.execute("DELETE FROM employment WHERE borrower_id = ?", (borrower_id,))
    conn.execute("DELETE FROM assets WHERE borrower_id = ?", (borrower_id,))
    conn.execute("DELETE FROM debts WHERE borrower_id = ?", (borrower_id,))
    conn.execute("DELETE FROM borrowers WHERE id = ?", (borrower_id,))
    conn.commit()
    conn.close()


# ── Employment ───────────────────────────────────────────────────────────────

def create_employment(borrower_id: int, **kwargs) -> int:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO employment
           (borrower_id, employer_name, position, years_employed, monthly_income, income_type)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            borrower_id,
            kwargs.get("employer_name", ""),
            kwargs.get("position", ""),
            kwargs.get("years_employed", 0),
            kwargs.get("monthly_income", 0),
            kwargs.get("income_type", "SALARY"),
        ),
    )
    emp_id = cur.lastrowid
    conn.commit()
    conn.close()
    return emp_id


def get_employment(borrower_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM employment WHERE borrower_id = ?", (borrower_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_employment(emp_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM employment WHERE id = ?", (emp_id,))
    conn.commit()
    conn.close()


# ── Assets ───────────────────────────────────────────────────────────────────

def create_asset(borrower_id: int, **kwargs) -> int:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO assets (borrower_id, account_type, institution, balance)
           VALUES (?, ?, ?, ?)""",
        (
            borrower_id,
            kwargs.get("account_type", ""),
            kwargs.get("institution", ""),
            kwargs.get("balance", 0),
        ),
    )
    asset_id = cur.lastrowid
    conn.commit()
    conn.close()
    return asset_id


def get_assets(borrower_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM assets WHERE borrower_id = ?", (borrower_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_asset(asset_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
    conn.commit()
    conn.close()


# ── Debts ────────────────────────────────────────────────────────────────────

def create_debt(borrower_id: int, **kwargs) -> int:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO debts (borrower_id, debt_type, creditor, monthly_payment, balance)
           VALUES (?, ?, ?, ?, ?)""",
        (
            borrower_id,
            kwargs.get("debt_type", ""),
            kwargs.get("creditor", ""),
            kwargs.get("monthly_payment", 0),
            kwargs.get("balance", 0),
        ),
    )
    debt_id = cur.lastrowid
    conn.commit()
    conn.close()
    return debt_id


def get_debts(borrower_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM debts WHERE borrower_id = ?", (borrower_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_debt(debt_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM debts WHERE id = ?", (debt_id,))
    conn.commit()
    conn.close()


# ── Underwriting Decisions ───────────────────────────────────────────────────

def create_underwriting_decision(application_id: int, **kwargs) -> int:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO underwriting_decisions
           (application_id, decision, ltv, cltv, dti, highest_credit_score,
            reasons, conditions, decided_by, decided_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            application_id,
            kwargs.get("decision", ""),
            kwargs.get("ltv", 0),
            kwargs.get("cltv", 0),
            kwargs.get("dti", 0),
            kwargs.get("highest_credit_score", 0),
            kwargs.get("reasons", "[]"),
            kwargs.get("conditions", "[]"),
            kwargs.get("decided_by", ""),
            now_utc(),
        ),
    )
    dec_id = cur.lastrowid
    conn.commit()
    conn.close()
    return dec_id


def get_underwriting_decisions(application_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM underwriting_decisions WHERE application_id = ? ORDER BY decided_at DESC",
        (application_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Pricing Locks ────────────────────────────────────────────────────────────

def create_pricing_lock(application_id: int, **kwargs) -> int:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO pricing_locks
           (application_id, prime_rate, margin, fico_adjustment, ltv_adjustment,
            amount_adjustment, autopay_discount, final_rate, monthly_payment,
            rate_locked, lock_date, lock_expiration, locked_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            application_id,
            kwargs.get("prime_rate", 0),
            kwargs.get("margin", 0),
            kwargs.get("fico_adjustment", 0),
            kwargs.get("ltv_adjustment", 0),
            kwargs.get("amount_adjustment", 0),
            kwargs.get("autopay_discount", 0),
            kwargs.get("final_rate", 0),
            kwargs.get("monthly_payment", 0),
            int(kwargs.get("rate_locked", False)),
            kwargs.get("lock_date"),
            kwargs.get("lock_expiration"),
            kwargs.get("locked_by", ""),
        ),
    )
    lock_id = cur.lastrowid
    conn.commit()
    conn.close()
    return lock_id


def get_pricing_locks(application_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM pricing_locks WHERE application_id = ? ORDER BY id DESC",
        (application_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Conditions ───────────────────────────────────────────────────────────────

def create_condition(application_id: int, **kwargs) -> int:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO conditions
           (application_id, condition_type, description, status, added_by, added_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            application_id,
            kwargs.get("condition_type", "PRIOR_TO_CLOSING"),
            kwargs.get("description", ""),
            kwargs.get("status", "OPEN"),
            kwargs.get("added_by", ""),
            now_utc(),
        ),
    )
    cond_id = cur.lastrowid
    conn.commit()
    conn.close()
    return cond_id


def get_conditions(application_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM conditions WHERE application_id = ? ORDER BY added_at",
        (application_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_condition(condition_id: int, **kwargs):
    set_clause = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [condition_id]
    conn = get_connection()
    conn.execute(f"UPDATE conditions SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


# ── Documents ────────────────────────────────────────────────────────────────

def create_document(application_id: int, **kwargs) -> int:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO documents (application_id, doc_type, filename, uploaded_by, uploaded_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            application_id,
            kwargs.get("doc_type", ""),
            kwargs.get("filename", ""),
            kwargs.get("uploaded_by", ""),
            now_utc(),
        ),
    )
    doc_id = cur.lastrowid
    conn.commit()
    conn.close()
    return doc_id


def get_documents(application_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM documents WHERE application_id = ? ORDER BY uploaded_at",
        (application_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Generated Documents ─────────────────────────────────────────────────────

def create_generated_document(application_id: int, **kwargs) -> int:
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO generated_documents (application_id, doc_type, filename, generated_at)
           VALUES (?, ?, ?, ?)""",
        (
            application_id,
            kwargs.get("doc_type", ""),
            kwargs.get("filename", ""),
            now_utc(),
        ),
    )
    doc_id = cur.lastrowid
    conn.commit()
    conn.close()
    return doc_id


def get_generated_documents(application_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM generated_documents WHERE application_id = ? ORDER BY generated_at",
        (application_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Audit Log ────────────────────────────────────────────────────────────────

def add_audit_entry(application_id: int, action: str, details: str = "", performed_by: str = ""):
    conn = get_connection()
    conn.execute(
        """INSERT INTO audit_log (application_id, action, details, performed_by, performed_at)
           VALUES (?, ?, ?, ?, ?)""",
        (application_id, action, details, performed_by, now_utc()),
    )
    conn.commit()
    conn.close()


def get_audit_log(application_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM audit_log WHERE application_id = ? ORDER BY performed_at DESC",
        (application_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_full_audit_log() -> list[dict]:
    """Get all audit entries across all applications."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT al.*, a.application_number
           FROM audit_log al
           JOIN applications a ON a.id = al.application_id
           ORDER BY al.performed_at DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
