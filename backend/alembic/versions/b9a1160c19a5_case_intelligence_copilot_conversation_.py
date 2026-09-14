"""KNOT6 Case Intelligence: copilot conversation turns

Revision ID: b9a1160c19a5
Revises: 4da0bcb52c2d
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b9a1160c19a5'
down_revision: Union[str, Sequence[str], None] = '4da0bcb52c2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('copilot_conversation_turns',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('investigation_id', sa.String(length=36), nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('question', sa.Text(), nullable=False),
    sa.Column('answer', sa.Text(), nullable=False),
    sa.Column('citations', sa.JSON(), nullable=False),
    sa.Column('actions', sa.JSON(), nullable=False),
    sa.Column('context_entity_ids', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_copilot_conversation_turns_investigation_id'), 'copilot_conversation_turns', ['investigation_id'], unique=False)
    op.create_index(op.f('ix_copilot_conversation_turns_username'), 'copilot_conversation_turns', ['username'], unique=False)
    op.create_index(op.f('ix_copilot_conversation_turns_created_at'), 'copilot_conversation_turns', ['created_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_copilot_conversation_turns_created_at'), table_name='copilot_conversation_turns')
    op.drop_index(op.f('ix_copilot_conversation_turns_username'), table_name='copilot_conversation_turns')
    op.drop_index(op.f('ix_copilot_conversation_turns_investigation_id'), table_name='copilot_conversation_turns')
    op.drop_table('copilot_conversation_turns')
