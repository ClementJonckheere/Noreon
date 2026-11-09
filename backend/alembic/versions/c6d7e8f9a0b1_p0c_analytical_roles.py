"""P0-C: explicit analytical roles on semantic mappings.

Revision ID: c6d7e8f9a0b1
Revises: c4d5e6f7a8b9
Create Date: 2026-09-03
"""
from alembic import op
import sqlalchemy as sa


revision = "c6d7e8f9a0b1"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "concept_mappings",
        sa.Column("analytical_roles", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("concept_mappings", "analytical_roles")
