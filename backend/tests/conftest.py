"""
KNOT6 Phase 1 test configuration.

Points `DATABASE_URL` at an isolated, throwaway SQLite file for the whole
test session, set *before* any `app.*` module is imported -- `get_settings()`
is process-wide `@lru_cache`d and several modules (postgres.py, security.py,
audit.py) build a SQLAlchemy engine/session at import time, so the env var
has to land here, in conftest.py, which pytest always loads before
collecting test modules. This mirrors how the pre-Phase-1 tests already
isolate the *graph* (a fresh `NetworkXGraphStore()` per test) -- this file
is the equivalent seam for the new PostgreSQL-shaped layer.

The pre-Phase-1 tests (`test_analytics.py`, `test_entity_extraction.py`,
`test_entity_resolution.py`) never touch the database at all, so they are
completely unaffected by any of this.
"""
from __future__ import annotations

import os
from pathlib import Path

_TEST_DB = Path(__file__).resolve().parent / "test_knot6.db"
_TEST_DB.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"
os.environ.setdefault("AUTO_SEED_DEMO", "true")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _cleanup_test_db():
    yield
    # Windows keeps a file lock for as long as any pooled SQLAlchemy
    # connection is open; dispose the engine first so the unlink doesn't
    # racily fail with WinError 32. Best-effort either way -- a leftover
    # tests/test_knot6.db is harmless (gitignored) and gets removed at the
    # start of the next run regardless.
    from app.db.postgres import engine
    engine.dispose()
    try:
        _TEST_DB.unlink(missing_ok=True)
    except PermissionError:
        pass


@pytest.fixture(scope="session")
def client():
    """
    A single TestClient for the whole test session (so the demo-seeding
    startup event -- a real NLP pass over the bundled dataset -- runs once,
    not per test). Individual tests create their own Investigation/Case via
    the API rather than relying on a reset-between-tests database, which
    keeps them independent of each other and of the auto-seeded demo data.
    """
    from app.main import app
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, username: str, password: str) -> str:
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


@pytest.fixture
def admin_token(client):
    return _login(client, "admin", "admin123")


@pytest.fixture
def investigator_token(client):
    return _login(client, "investigator", "investigator123")


@pytest.fixture
def analyst_token(client):
    return _login(client, "analyst", "analyst123")


@pytest.fixture
def viewer_token(client):
    return _login(client, "viewer", "viewer123")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
