"""
SQLAlchemy engine/session setup for KNOT6's application database.

Deliberately separate from `graph_store.py` -- the graph never lives here,
see that module's docstring and docs/KNOT6_ARCHITECTURE.md for the split.
`settings.database_url` follows the exact same dual-mode pattern already
established for `GRAPH_BACKEND`: a local SQLite file by default (zero-infra
dev/demo, nothing to install) and a real PostgreSQL URL in
`docker-compose.yml` / production.
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import Base

settings = get_settings()

# SQLite needs this to be usable from FastAPI's threadpool-executed sync
# routes; it's a no-op for PostgreSQL (psycopg) connections.
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """
    Create tables if they don't exist yet. Used for the zero-infra SQLite
    dev path and by the test suite; the Docker/production PostgreSQL path
    uses the Alembic migration in `backend/alembic/versions/` instead (see
    docs/KNOT6_ARCHITECTURE.md's Database Migrations section) so schema
    changes are reproducible and reviewable rather than inferred at
    startup.
    """
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
