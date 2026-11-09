"""control group selection metadata (frozen before observation)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa


revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # {control_ids, matching_features, matching_score, pretrend_score, selection_at}
    op.add_column("measurement_plans", sa.Column("control_selection", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("measurement_plans", "control_selection")
