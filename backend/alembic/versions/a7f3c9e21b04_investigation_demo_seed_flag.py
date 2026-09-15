"""Investigation demo-seed protection flag

Adds `investigations.is_demo_seed` (default false). Set true only for the
single auto-seeded "Operation Nexus" investigation (see app/main.py) so new
intelligence uploads can be refused against it -- see
app/services/evidence_processing.py's `ensure_not_demo_protected` and
docs/DEMO_DATA.md. This is a data-integrity fix: without it, the bundled
demo dataset had no way to distinguish itself from a real investigation and
could be silently grown by a real "Add Intelligence" upload.

Revision ID: a7f3c9e21b04
Revises: c1861ad64545
Create Date: 2026-09-15
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7f3c9e21b04'
down_revision: Union[str, Sequence[str], None] = 'c1861ad64545'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'investigations',
        sa.Column('is_demo_seed', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Backfill: whichever existing investigation is literally named
    # "Operation Nexus" is the bundled demo dataset (see app/main.py's
    # DEMO_INVESTIGATION_NAME) -- flag it retroactively so upgrading an
    # already-seeded database doesn't leave the demo unprotected.
    op.execute("UPDATE investigations SET is_demo_seed = TRUE WHERE name = 'Operation Nexus'")


def downgrade() -> None:
    op.drop_column('investigations', 'is_demo_seed')
