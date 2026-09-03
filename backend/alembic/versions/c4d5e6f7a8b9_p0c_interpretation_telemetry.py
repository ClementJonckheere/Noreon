"""P0-C: separate provider JSON from normalized interpretation.

Revision ID: c4d5e6f7a8b9
Revises: c2d3e4f5a6b7
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa


revision = "c4d5e6f7a8b9"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = "planner_shadow_evaluations"
    op.add_column(table, sa.Column("provider_raw_json", sa.JSON(), nullable=True))
    op.add_column(table, sa.Column("normalized_interpretation_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    table = "planner_shadow_evaluations"
    op.drop_column(table, "normalized_interpretation_json")
    op.drop_column(table, "provider_raw_json")
