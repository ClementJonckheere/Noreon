"""reports and report blocks (AI docs studio)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-20 12:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: str | None = 'b2c3d4e5f6a7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('space_id', sa.Integer(), nullable=True),
        sa.Column('user_ref', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('title', sa.String(length=255), nullable=False, server_default='Nouveau rapport'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['space_id'], ['spaces.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_reports_tenant_id'), 'reports', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_reports_space_id'), 'reports', ['space_id'], unique=False)
    op.create_index(op.f('ix_reports_user_ref'), 'reports', ['user_ref'], unique=False)

    op.create_table(
        'report_blocks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('report_id', sa.Integer(), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('kind', sa.String(length=16), nullable=False, server_default='markdown'),
        sa.Column('content', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_report_blocks_report_id'), 'report_blocks', ['report_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_report_blocks_report_id'), table_name='report_blocks')
    op.drop_table('report_blocks')
    op.drop_index(op.f('ix_reports_user_ref'), table_name='reports')
    op.drop_index(op.f('ix_reports_space_id'), table_name='reports')
    op.drop_index(op.f('ix_reports_tenant_id'), table_name='reports')
    op.drop_table('reports')
