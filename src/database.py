"""Database schema creation and connection helper.

Supports two modes:
  1. **Turso** (production) — when TURSO_DATABASE_URL is set in Streamlit
     secrets or environment variables, connects to the hosted libSQL database.
  2. **Local SQLite** (development) — falls back to data/heloc_los.db.

The rest of the app calls get_connection() and doesn't care which backend
is active. Both return a connection with .execute(), .commit(), .close(),
and dict-style row access by column name.
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "heloc_los.db")

# Cached Turso connection — reused across calls to avoid repeated sync overhead.
_turso_conn = None


def _get_turso_config():
    """Try to read Turso credentials from Streamlit secrets or env vars."""
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")

    # Streamlit secrets take priority
    try:
        import streamlit as st
        url = url or st.secrets.get("TURSO_DATABASE_URL")
        token = token or st.secrets.get("TURSO_AUTH_TOKEN")
    except Exception:
        pass

    if url and token:
        return url, token
    return None, None


# ── Dict-row wrapper for libsql ─────────────────────────────────────────────
# libsql returns plain tuples; our code expects row["column_name"] everywhere.
# This thin wrapper converts results to dict-like rows transparently.

class _DictRow(dict):
    """A dict that also supports integer index access for compatibility."""
    def __init__(self, keys, values):
        super().__init__(zip(keys, values))
        self._values = values

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class _DictCursor:
    """Wraps a libsql cursor to return dict-like rows."""
    def __init__(self, real_cursor):
        self._cursor = real_cursor

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    @property
    def description(self):
        return self._cursor.description

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in self._cursor.description]
        return _DictRow(cols, row)

    def fetchall(self):
        rows = self._cursor.fetchall()
        if not rows:
            return rows
        cols = [d[0] for d in self._cursor.description]
        return [_DictRow(cols, r) for r in rows]

    def execute(self, sql, params=None):
        if params:
            self._cursor.execute(sql, params)
        else:
            self._cursor.execute(sql)
        return self


class _DictConnection:
    """Wraps a libsql connection to return dict-like rows from execute().

    Uses the embedded replica pattern: reads are local (fast), writes sync
    to Turso only on commit(). close() is a no-op since the connection is
    reused across calls.
    """
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        if params:
            result = self._conn.execute(sql, params)
        else:
            result = self._conn.execute(sql)
        return _DictCursor(result)

    def cursor(self):
        return _DictCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()
        self._conn.sync()  # push writes to Turso

    def close(self):
        pass  # no-op — connection is reused via _turso_conn cache


def get_connection():
    """Return a database connection.

    Uses Turso (libsql) when configured, otherwise local SQLite.
    Both return dict-style row access by column name.

    Turso connections are cached and reused. The initial sync() pulls the
    full DB locally; after that, reads hit the local replica (fast) and
    only commit() calls sync back to Turso (one round-trip per write).
    """
    global _turso_conn
    url, token = _get_turso_config()

    if url and token:
        if _turso_conn is None:
            import libsql
            raw = libsql.connect("heloc_los.db", sync_url=url, auth_token=token)
            raw.sync()  # one-time pull on startup
            raw.execute("PRAGMA foreign_keys=ON")
            _turso_conn = _DictConnection(raw)
        return _turso_conn
    else:
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

    # libsql doesn't support executescript, so execute each statement separately
    statements = [
        """CREATE TABLE IF NOT EXISTS applications (
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
        )""",
        "CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status)",
        "CREATE INDEX IF NOT EXISTS idx_applications_number ON applications(application_number)",

        """CREATE TABLE IF NOT EXISTS borrowers (
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
        )""",
        "CREATE INDEX IF NOT EXISTS idx_borrowers_app ON borrowers(application_id)",
        "CREATE INDEX IF NOT EXISTS idx_borrowers_email ON borrowers(email)",

        """CREATE TABLE IF NOT EXISTS employment (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            borrower_id     INTEGER NOT NULL,
            employer_name   TEXT    NOT NULL DEFAULT '',
            position        TEXT    NOT NULL DEFAULT '',
            years_employed  REAL    NOT NULL DEFAULT 0,
            monthly_income  REAL    NOT NULL DEFAULT 0,
            income_type     TEXT    NOT NULL DEFAULT 'SALARY',
            FOREIGN KEY (borrower_id) REFERENCES borrowers(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_employment_borrower ON employment(borrower_id)",

        """CREATE TABLE IF NOT EXISTS assets (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            borrower_id     INTEGER NOT NULL,
            account_type    TEXT    NOT NULL DEFAULT '',
            institution     TEXT    NOT NULL DEFAULT '',
            balance         REAL    NOT NULL DEFAULT 0,
            FOREIGN KEY (borrower_id) REFERENCES borrowers(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_assets_borrower ON assets(borrower_id)",

        """CREATE TABLE IF NOT EXISTS debts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            borrower_id     INTEGER NOT NULL,
            debt_type       TEXT    NOT NULL DEFAULT '',
            creditor        TEXT    NOT NULL DEFAULT '',
            monthly_payment REAL    NOT NULL DEFAULT 0,
            balance         REAL    NOT NULL DEFAULT 0,
            FOREIGN KEY (borrower_id) REFERENCES borrowers(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_debts_borrower ON debts(borrower_id)",

        """CREATE TABLE IF NOT EXISTS underwriting_decisions (
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
        )""",
        "CREATE INDEX IF NOT EXISTS idx_uw_app ON underwriting_decisions(application_id)",

        """CREATE TABLE IF NOT EXISTS pricing_locks (
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
        )""",
        "CREATE INDEX IF NOT EXISTS idx_pricing_app ON pricing_locks(application_id)",

        """CREATE TABLE IF NOT EXISTS conditions (
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
        )""",
        "CREATE INDEX IF NOT EXISTS idx_conditions_app ON conditions(application_id)",

        """CREATE TABLE IF NOT EXISTS documents (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id  INTEGER NOT NULL,
            doc_type        TEXT    NOT NULL,
            filename        TEXT    NOT NULL,
            uploaded_by     TEXT    NOT NULL DEFAULT '',
            uploaded_at     TEXT    NOT NULL,
            FOREIGN KEY (application_id) REFERENCES applications(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_documents_app ON documents(application_id)",

        """CREATE TABLE IF NOT EXISTS generated_documents (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id  INTEGER NOT NULL,
            doc_type        TEXT    NOT NULL,
            filename        TEXT    NOT NULL,
            generated_at    TEXT    NOT NULL,
            FOREIGN KEY (application_id) REFERENCES applications(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_gendocs_app ON generated_documents(application_id)",

        """CREATE TABLE IF NOT EXISTS audit_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id  INTEGER NOT NULL,
            action          TEXT    NOT NULL,
            details         TEXT    NOT NULL DEFAULT '',
            performed_by    TEXT    NOT NULL DEFAULT '',
            performed_at    TEXT    NOT NULL,
            FOREIGN KEY (application_id) REFERENCES applications(id)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_audit_app ON audit_log(application_id)",

        """CREATE TABLE IF NOT EXISTS system_audit_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            action          TEXT    NOT NULL,
            details         TEXT    NOT NULL DEFAULT '',
            performed_by    TEXT    NOT NULL DEFAULT '',
            performed_at    TEXT    NOT NULL
        )""",

        """CREATE TABLE IF NOT EXISTS settings (
            key     TEXT PRIMARY KEY,
            value   TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
    ]

    for stmt in statements:
        cur.execute(stmt)

    conn.commit()
    conn.close()
