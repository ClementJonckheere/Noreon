"""generic relation candidates (coverage, alternatives, temporality, origin)

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa


revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "relation_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("connection_id", sa.Integer(), index=True, nullable=False),
        sa.Column("left_schema", sa.String(length=255), server_default="public", nullable=False),
        sa.Column("left_table", sa.String(length=255), nullable=False),
        sa.Column("left_column", sa.String(length=255), nullable=False),
        sa.Column("right_schema", sa.String(length=255), server_default="public", nullable=False),
        sa.Column("right_table", sa.String(length=255), nullable=False),
        sa.Column("right_column", sa.String(length=255), nullable=False),
        sa.Column("direction", sa.String(length=16), server_default="left_to_right", nullable=False),
        sa.Column("cardinality", sa.String(length=16), nullable=True),
        sa.Column("coverage", sa.Float(), nullable=True),
        sa.Column("target_uniqueness", sa.Float(), nullable=True),
        sa.Column("type_compatibility", sa.String(length=24), nullable=True),
        sa.Column("exceptions_count", sa.Integer(), nullable=True),
        sa.Column("exceptions_note", sa.String(), nullable=True),
        sa.Column("alternatives", sa.JSON(), nullable=True),
        sa.Column("origin", sa.String(length=16), server_default="inferred", nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_id", sa.String(length=128), nullable=True),
        sa.Column("source_ids", sa.JSON(), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="candidate", index=True, nullable=False),
        sa.Column("validated_by", sa.String(length=255), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validation_window", sa.JSON(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("relation_candidates")
