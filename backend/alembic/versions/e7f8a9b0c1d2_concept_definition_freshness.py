"""impact freshness on concept definitions (evaluated_at, snapshot, sources)

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa


revision = "e7f8a9b0c1d2"
down_revision = "d6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("concept_definitions", sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("concept_definitions", sa.Column("snapshot_id", sa.String(length=128), nullable=True))
    op.add_column("concept_definitions", sa.Column("source_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("concept_definitions", "source_ids")
    op.drop_column("concept_definitions", "snapshot_id")
    op.drop_column("concept_definitions", "evaluated_at")
