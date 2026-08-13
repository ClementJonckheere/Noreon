"""concept definition version frozen by the measurement protocol

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa


revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Version de la définition MÉTIER du concept mesuré, figée au protocole (audit).
    op.add_column("measurement_plans", sa.Column("metric_definition_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("measurement_plans", "metric_definition_version")
