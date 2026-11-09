"""report versions (validated immutable snapshots)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa


revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_versions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(), sa.ForeignKey("reports.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("blocks", sa.JSON(), nullable=True),
        sa.Column("source_connection_id", sa.Integer(), nullable=True),
        sa.Column("source_tables", sa.JSON(), nullable=True),
        sa.Column("validated_by", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("report_versions")
