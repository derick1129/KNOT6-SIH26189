"""Hypothesis Lab persistence

Adds `hypotheses` and `hypothesis_evidence` -- see app/db/models.py's
Hypothesis/HypothesisEvidence docstrings for the design rationale (why the
graph path and live analytics are deliberately NOT frozen into this table).

Revision ID: c1861ad64545
Revises: 5289bb42d89a
Create Date: 2026-09-14
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c1861ad64545'
down_revision: Union[str, Sequence[str], None] = '5289bb42d89a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'hypotheses',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('investigation_id', sa.String(length=36), nullable=False),
        sa.Column('case_id', sa.String(length=36), nullable=True),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='OPEN'),
        sa.Column('subject_entity_id', sa.String(length=80), nullable=True),
        sa.Column('target_entity_id', sa.String(length=80), nullable=True),
        sa.Column('related_entity_ids', sa.JSON(), nullable=False),
        sa.Column('notes', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_hypotheses_investigation_id'), 'hypotheses', ['investigation_id'], unique=False)
    op.create_index(op.f('ix_hypotheses_case_id'), 'hypotheses', ['case_id'], unique=False)
    op.create_index(op.f('ix_hypotheses_created_at'), 'hypotheses', ['created_at'], unique=False)

    op.create_table(
        'hypothesis_evidence',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('hypothesis_id', sa.String(length=36), nullable=False),
        sa.Column('evidence_id', sa.String(length=36), nullable=False),
        sa.Column('relationship_type', sa.String(length=15), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('created_by', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['hypothesis_id'], ['hypotheses.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_hypothesis_evidence_hypothesis_id'), 'hypothesis_evidence', ['hypothesis_id'], unique=False)
    op.create_index(op.f('ix_hypothesis_evidence_evidence_id'), 'hypothesis_evidence', ['evidence_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_hypothesis_evidence_evidence_id'), table_name='hypothesis_evidence')
    op.drop_index(op.f('ix_hypothesis_evidence_hypothesis_id'), table_name='hypothesis_evidence')
    op.drop_table('hypothesis_evidence')

    op.drop_index(op.f('ix_hypotheses_created_at'), table_name='hypotheses')
    op.drop_index(op.f('ix_hypotheses_case_id'), table_name='hypotheses')
    op.drop_index(op.f('ix_hypotheses_investigation_id'), table_name='hypotheses')
    op.drop_table('hypotheses')
