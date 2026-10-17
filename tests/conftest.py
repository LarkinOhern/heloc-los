"""Shared fixtures: every test gets its own throwaway SQLite database.

The app reads ``src.database.DB_PATH`` on every connection, so pointing that
at a temp file isolates tests from data/heloc_los.db (and from Turso, which
is only used when secrets are configured).
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Fresh database with schema, default settings and the five demo apps."""
    from src import database
    from src.documents import generator

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(generator, "OUTPUT_DIR", str(tmp_path / "generated"))
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)

    from src.database import init_db
    from src.seed import seed_database

    init_db()
    seed_database()
    return tmp_path


@pytest.fixture
def app_by_number(db):
    """Look up an application row by its number."""
    from src.utils.db_helpers import get_application_by_number

    def _get(number):
        app = get_application_by_number(number)
        assert app, f"{number} not seeded"
        return app

    return _get


@pytest.fixture
def apptest(db):
    """Factory for a Streamlit AppTest of the real entry point."""
    from streamlit.testing.v1 import AppTest

    def _make():
        at = AppTest.from_file(str(ROOT / "src" / "app.py"), default_timeout=60)
        at.run()
        return at

    return _make
