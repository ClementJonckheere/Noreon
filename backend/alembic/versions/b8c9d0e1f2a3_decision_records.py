"""decision records (business memory of decisions)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-24 14:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: str | None = 'a7b8c9d0e1f2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'decision_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('connection_id', sa.Integer(), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=128), nullable=False),
        sa.Column('recommendation', sa.String(), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='retained'),
        sa.Column('note', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_decision_records_connection_id', 'decision_records', ['connection_id'])
    op.create_index('ix_decision_records_subject', 'decision_records', ['subject'])
    op.create_index('ix_decision_records_tenant_id', 'decision_records', ['tenant_id'])


def downgrade() -> None:
    op.drop_table('decision_records')
