"""reasoning memory (effective strategies learned by the agent)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-24 13:10:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: str | None = 'f6a7b8c9d0e1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'reasoning_memory',
        sa.Column('connection_id', sa.Integer(), nullable=False),
        sa.Column('subject_table', sa.String(length=255), nullable=False),
        sa.Column('dimension_label', sa.String(length=255), nullable=False),
        sa.Column('effectiveness', sa.Float(), nullable=False, server_default='0'),
        sa.Column('observations', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('connection_id', 'subject_table', 'dimension_label'),
    )


def downgrade() -> None:
    op.drop_table('reasoning_memory')
