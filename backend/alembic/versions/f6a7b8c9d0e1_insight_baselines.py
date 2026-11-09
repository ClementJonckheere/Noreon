"""insight baselines (comparable reports)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-24 12:30:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'f6a7b8c9d0e1'
down_revision: str | None = 'e5f6a7b8c9d0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'insight_baselines',
        sa.Column('connection_id', sa.Integer(), nullable=False),
        sa.Column('keys', sa.JSON(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('connection_id'),
    )


def downgrade() -> None:
    op.drop_table('insight_baselines')
