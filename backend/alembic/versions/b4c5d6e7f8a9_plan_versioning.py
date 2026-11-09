"""immutable protocol versioning — a revision supersedes, never mutates

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa


revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Successeur d'un plan révisé (protocol_version + 1) : l'ancien reste intact.
    op.add_column("measurement_plans", sa.Column("superseded_by_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("measurement_plans", "superseded_by_id")
