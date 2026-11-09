"""generic WorkItem (actionable) + ActivityEvent (informational)

Revision ID: a9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-08-14
"""
from alembic import op
import sqlalchemy as sa


revision = "a9b0c1d2e3f4"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("kind", sa.String(length=32), index=True, nullable=False),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("object_id", sa.String(length=64), nullable=False),
        sa.Column("space_id", sa.Integer(), nullable=True),
        sa.Column("assignee_id", sa.Integer(), nullable=True),
        sa.Column("required_capability", sa.String(length=48), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="a_traiter", index=True, nullable=False),
        sa.Column("title", sa.String(length=255), server_default="", nullable=False),
        sa.Column("reason", sa.String(), server_default="", nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "activity_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("kind", sa.String(length=32), index=True, nullable=False),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("object_id", sa.String(length=64), nullable=False),
        sa.Column("space_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), server_default="", nullable=False),
        sa.Column("detail", sa.String(), server_default="", nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("activity_events")
    op.drop_table("work_items")
