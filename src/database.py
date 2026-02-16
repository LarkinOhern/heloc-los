"""Database schema creation and connection helper."""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "heloc_los.db")


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with WAL mode and foreign keys enabled."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS applications (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        application_number      TEXT    NOT NULL UNIQUE,
        status                  TEXT    NOT NULL DEFAULT 'DRAFT',
        property_address        TEXT    NOT NULL DEFAULT '',
        property_city           TEXT    NOT NULL DEFAULT '',
        property_state          TEXT    NOT NULL DEFAULT '',
        property_zip            TEXT    NOT NULL DEFAULT '',
        property_type           TEXT    NOT NULL DEFAULT 'PRIMARY_RESIDENCE',
        property_value          REAL    NOT NULL DEFAULT 0,
        existing_mortgage_balance REAL  NOT NULL DEFAULT 0,
        heloc_amount_requested  REAL    NOT NULL DEFAULT 0,
        heloc_purpose           TEXT    NOT NULL DEFAULT '',
        autopay_enrolled        INTEGER NOT NULL DEFAULT 0,
        econsent_given          INTEGER NOT NULL DEFAULT 0,
        econsent_date           TEXT,
        assigned_employee       TEXT,
        created_at              TEXT    NOT NULL,
        updated_at              TEXT    NOT NULL,
        submitted_at            TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
    CREATE INDEX IF NOT EXISTS idx_applications_number ON applications(application_number);

    CREATE TABLE IF NOT EXISTS borrowers (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id  INTEGER NOT NULL,
        is_primary      INTEGER NOT NULL DEFAULT 1,
        first_name      TEXT    NOT NULL DEFAULT '',
        last_name       TEXT    NOT NULL DEFAULT '',
        email           TEXT    NOT NULL DEFAULT '',
        phone           TEXT    NOT NULL DEFAULT '',
        ssn_last4       TEXT    NOT NULL DEFAULT '',
        date_of_birth   TEXT    NOT NULL DEFAULT '',
        credit_score    INTEGER NOT NULL DEFAULT 0,
        citizenship     TEXT    NOT NULL DEFAULT 'US_CITIZEN',
        FOREIGN KEY (application_id) REFERENCES applications(id),
        UNIQUE(application_id, is_primary)
    );
    CREATE INDEX IF NOT EXISTS idx_borrowers_app ON borrowers(application_id);
    CREATE INDEX IF NOT EXISTS idx_borrowers_email ON borrowers(email);

    CREATE TABLE IF NOT EXISTS employment (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        borrower_id     INTEGER NOT NULL,
        employer_name   TEXT    NOT NULL DEFAULT '',
        position        TEXT    NOT NULL DEFAULT '',
        years_employed  REAL    NOT NULL DEFAULT 0,
        monthly_income  REAL    NOT NULL DEFAULT 0,
        income_type     TEXT    NOT NULL DEFAULT 'SALARY',
        FOREIGN KEY (borrower_id) REFERENCES borrowers(id)
    );
    CREATE INDEX IF NOT EXISTS idx_employment_borrower ON employment(borrower_id);

    CREATE TABLE IF NOT EXISTS assets (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        borrower_id     INTEGER NOT NULL,
        account_type    TEXT    NOT NULL DEFAULT '',
        institution     TEXT    NOT NULL DEFAULT '',
        balance         REAL    NOT NULL DEFAULT 0,
        FOREIGN KEY (borrower_id) REFERENCES borrowers(id)
    );
    CREATE INDEX IF NOT EXISTS idx_assets_borrower ON assets(borrower_id);

    CREATE TABLE IF NOT EXISTS debts (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        borrower_id     INTEGER NOT NULL,
        debt_type       TEXT    NOT NULL DEFAULT '',
        creditor        TEXT    NOT NULL DEFAULT '',
        monthly_payment REAL    NOT NULL DEFAULT 0,
        balance         REAL    NOT NULL DEFAULT 0,
        FOREIGN KEY (borrower_id) REFERENCES borrowers(id)
    );
    CREATE INDEX IF NOT EXISTS idx_debts_borrower ON debts(borrower_id);

    CREATE TABLE IF NOT EXISTS underwriting_decisions (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id      INTEGER NOT NULL,
        decision            TEXT    NOT NULL,
        ltv                 REAL    NOT NULL DEFAULT 0,
        cltv                REAL    NOT NULL DEFAULT 0,
        dti                 REAL    NOT NULL DEFAULT 0,
        highest_credit_score INTEGER NOT NULL DEFAULT 0,
        reasons             TEXT    NOT NULL DEFAULT '[]',
        conditions          TEXT    NOT NULL DEFAULT '[]',
        decided_by          TEXT    NOT NULL DEFAULT '',
        decided_at          TEXT    NOT NULL,
        FOREIGN KEY (application_id) REFERENCES applications(id)
    );
    CREATE INDEX IF NOT EXISTS idx_uw_app ON underwriting_decisions(application_id);

    CREATE TABLE IF NOT EXISTS pricing_locks (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id      INTEGER NOT NULL,
        prime_rate           REAL    NOT NULL DEFAULT 0,
        margin               REAL    NOT NULL DEFAULT 0,
        fico_adjustment      REAL    NOT NULL DEFAULT 0,
        ltv_adjustment       REAL    NOT NULL DEFAULT 0,
        amount_adjustment    REAL    NOT NULL DEFAULT 0,
        autopay_discount     REAL    NOT NULL DEFAULT 0,
        final_rate           REAL    NOT NULL DEFAULT 0,
        monthly_payment      REAL    NOT NULL DEFAULT 0,
        rate_locked          INTEGER NOT NULL DEFAULT 0,
        lock_date            TEXT,
        lock_expiration      TEXT,
        locked_by            TEXT    NOT NULL DEFAULT '',
        FOREIGN KEY (application_id) REFERENCES applications(id)
    );
    CREATE INDEX IF NOT EXISTS idx_pricing_app ON pricing_locks(application_id);

    CREATE TABLE IF NOT EXISTS conditions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id  INTEGER NOT NULL,
        condition_type  TEXT    NOT NULL,
        description     TEXT    NOT NULL,
        status          TEXT    NOT NULL DEFAULT 'OPEN',
        added_by        TEXT    NOT NULL DEFAULT '',
        added_at        TEXT    NOT NULL,
        resolved_by     TEXT,
        resolved_at     TEXT,
        FOREIGN KEY (application_id) REFERENCES applications(id)
    );
    CREATE INDEX IF NOT EXISTS idx_conditions_app ON conditions(application_id);

    CREATE TABLE IF NOT EXISTS documents (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id  INTEGER NOT NULL,
        doc_type        TEXT    NOT NULL,
        filename        TEXT    NOT NULL,
        uploaded_by     TEXT    NOT NULL DEFAULT '',
        uploaded_at     TEXT    NOT NULL,
        FOREIGN KEY (application_id) REFERENCES applications(id)
    );
    CREATE INDEX IF NOT EXISTS idx_documents_app ON documents(application_id);

    CREATE TABLE IF NOT EXISTS generated_documents (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id  INTEGER NOT NULL,
        doc_type        TEXT    NOT NULL,
        filename        TEXT    NOT NULL,
        generated_at    TEXT    NOT NULL,
        FOREIGN KEY (application_id) REFERENCES applications(id)
    );
    CREATE INDEX IF NOT EXISTS idx_gendocs_app ON generated_documents(application_id);

    CREATE TABLE IF NOT EXISTS audit_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        application_id  INTEGER NOT NULL,
        action          TEXT    NOT NULL,
        details         TEXT    NOT NULL DEFAULT '',
        performed_by    TEXT    NOT NULL DEFAULT '',
        performed_at    TEXT    NOT NULL,
        FOREIGN KEY (application_id) REFERENCES applications(id)
    );
    CREATE INDEX IF NOT EXISTS idx_audit_app ON audit_log(application_id);

    CREATE TABLE IF NOT EXISTS settings (
        key     TEXT PRIMARY KEY,
        value   TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    conn.commit()
    conn.close()
