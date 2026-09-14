"""Phase 4: evidence integrity + tamper-evident audit chain

Adds `evidence.sha256_hash` (populated going forward at upload time; empty
for pre-existing rows -- see app/db/models.py:Evidence's docstring) and
three chaining columns to `audit_entries` (`seq`, `prev_hash`,
`entry_hash`). The data migration below *backfills* real chain hashes for
every audit row that already exists, rather than leaving them at
placeholder values -- see app/services/integrity.py for the hash formula
this duplicates (deliberately inlined rather than imported: a migration
should not depend on application code that might change shape later).

Revision ID: 5289bb42d89a
Revises: 0146c0967cf5
Create Date: 2026-09-14
"""
from __future__ import annotations

import hashlib
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5289bb42d89a'
down_revision: Union[str, Sequence[str], None] = '0146c0967cf5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _canonical_details(details) -> str:
    return json.dumps(details or {}, sort_keys=True, separators=(",", ":"), default=str)


def _compute_entry_hash(prev_hash: str, action: str, actor: str, timestamp, target, details) -> str:
    payload = "|".join([
        prev_hash or "", action, actor,
        timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
        target or "", _canonical_details(details),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.add_column('evidence', sa.Column('sha256_hash', sa.String(length=64), nullable=False, server_default=''))

    op.add_column('audit_entries', sa.Column('seq', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('audit_entries', sa.Column('prev_hash', sa.String(length=64), nullable=False, server_default=''))
    op.add_column('audit_entries', sa.Column('entry_hash', sa.String(length=64), nullable=False, server_default=''))
    op.create_index(op.f('ix_audit_entries_seq'), 'audit_entries', ['seq'], unique=False)

    # Backfill: assign every pre-existing audit row a real position in the
    # chain (ordered by timestamp -- the only ordering available for rows
    # written before `seq` existed) and compute its real hash, so the chain
    # is verifiable from the very first row ever written, not just from
    # this migration forward.
    #
    # Deliberately selected through a typed `sa.table()`/`sa.column()`
    # Core construct rather than raw `sa.text()` SQL: a bare `sa.text()`
    # query hands back whatever the raw DBAPI driver returns for each
    # column (for SQLite, `timestamp` comes back as a plain string in
    # SQLite's own storage format, e.g. "2026-09-12 14:03:00.123456"),
    # whereas the application later reads these same rows through the ORM,
    # which applies SQLAlchemy's DateTime *type decoder* and hands back a
    # real `datetime` object whose `.isoformat()` uses a different
    # separator/precision ("2026-09-12T14:03:00.123456"). Hashing the raw
    # string form here would make every single backfilled hash permanently
    # unverifiable against what verify_audit_chain() recomputes at
    # verification time -- not a hypothetical, this was caught by actually
    # running the verifier against a freshly migrated database.
    conn = op.get_bind()
    audit_table = sa.table(
        'audit_entries',
        sa.column('id', sa.String),
        sa.column('timestamp', sa.DateTime(timezone=True)),
        sa.column('actor', sa.String),
        sa.column('action', sa.String),
        sa.column('target', sa.String),
        sa.column('details', sa.JSON),
    )
    rows = conn.execute(sa.select(audit_table).order_by(audit_table.c.timestamp.asc())).fetchall()

    prev_hash = ""
    for i, row in enumerate(rows, start=1):
        details = row.details
        if isinstance(details, str):  # belt-and-suspenders: some dialects hand back raw JSON text regardless
            details = json.loads(details) if details else {}
        entry_hash = _compute_entry_hash(prev_hash, row.action, row.actor, row.timestamp, row.target, details)
        conn.execute(
            sa.text("UPDATE audit_entries SET seq = :seq, prev_hash = :prev_hash, entry_hash = :entry_hash "
                    "WHERE id = :id"),
            {"seq": i, "prev_hash": prev_hash, "entry_hash": entry_hash, "id": row.id},
        )
        prev_hash = entry_hash


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_entries_seq'), table_name='audit_entries')
    op.drop_column('audit_entries', 'entry_hash')
    op.drop_column('audit_entries', 'prev_hash')
    op.drop_column('audit_entries', 'seq')
    op.drop_column('evidence', 'sha256_hash')
