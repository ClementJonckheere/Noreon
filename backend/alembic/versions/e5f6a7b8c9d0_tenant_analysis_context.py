"""tenant analysis context (company conventions memory)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-23 15:40:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: str | None = 'd4e5f6a7b8c9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'tenant_settings',
        sa.Column('analysis_context', sa.JSON(), nullable=True),
    )
    op.execute(
        """
        UPDATE tenant_settings
        SET analysis_context = '{"amount_basis": null, "period_grain": null, "conventions": []}'
        WHERE analysis_context IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column('tenant_settings', 'analysis_context')
