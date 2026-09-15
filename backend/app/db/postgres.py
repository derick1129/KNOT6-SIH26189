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

from sqlalchemy import create_engine, inspect, text
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

    `create_all` only creates *missing tables* -- it never adds a column to
    a table that already exists, so a SQLite dev/demo database created
    before a model gained a new column (e.g. `Investigation.is_demo_seed`)
    would otherwise 500 on first query with "no such column". `_backfill_
    missing_columns` is the zero-infra-path equivalent of the Alembic
    migration's own backfill: a minimal, additive `ALTER TABLE ... ADD
    COLUMN` for exactly the columns SQLAlchemy's model knows about but the
    on-disk table doesn't, never a destructive change.
    """
    Base.metadata.create_all(bind=engine)
    _backfill_missing_columns()


def _backfill_missing_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return  # the reviewable Alembic migration is the path of record here
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in inspector.get_table_names():
                continue
            existing = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                default = "0" if str(column.type) == "BOOLEAN" else "NULL"
                conn.execute(text(
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type} DEFAULT {default}'
                ))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
