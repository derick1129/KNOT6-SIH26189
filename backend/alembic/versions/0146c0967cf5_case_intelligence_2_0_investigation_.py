"""case intelligence 2.0 investigation activity

Revision ID: 0146c0967cf5
Revises: b9a1160c19a5
Create Date: 2026-09-13 19:52:55.299505

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0146c0967cf5'
down_revision: Union[str, Sequence[str], None] = 'b9a1160c19a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('investigation_activities',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('investigation_id', sa.String(length=36), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('activity_type', sa.String(length=30), nullable=False),
    sa.Column('target_type', sa.String(length=20), nullable=True),
    sa.Column('target_id', sa.String(length=80), nullable=True),
    sa.Column('target_label', sa.String(length=255), nullable=True),
    sa.Column('extra', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_investigation_activities_investigation_id'), 'investigation_activities', ['investigation_id'], unique=False)
    op.create_index(op.f('ix_investigation_activities_username'), 'investigation_activities', ['username'], unique=False)
    op.create_index(op.f('ix_investigation_activities_created_at'), 'investigation_activities', ['created_at'], unique=False)

    op.add_column('copilot_conversation_turns', sa.Column('mode', sa.String(length=20), nullable=False, server_default='llm'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('copilot_conversation_turns', 'mode')

    op.drop_index(op.f('ix_investigation_activities_created_at'), table_name='investigation_activities')
    op.drop_index(op.f('ix_investigation_activities_username'), table_name='investigation_activities')
    op.drop_index(op.f('ix_investigation_activities_investigation_id'), table_name='investigation_activities')
    op.drop_table('investigation_activities')
