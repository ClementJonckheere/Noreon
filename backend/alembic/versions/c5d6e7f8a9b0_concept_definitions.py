"""generic concept definitions — substrate for domain-agnostic arbitration

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa


revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "concept_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("concept_id", sa.Integer(), sa.ForeignKey("business_concepts.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("scope", sa.String(length=16), server_default="universe", nullable=False),
        sa.Column("space_id", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("definition_text", sa.String(), server_default="", nullable=False),
        sa.Column("count_sql", sa.String(), nullable=True),
        sa.Column("entity_label", sa.String(length=64), server_default="entités", nullable=False),
        sa.Column("definition_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(length=24), server_default="candidate", index=True, nullable=False),
        sa.Column("is_reference", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("impact_count", sa.Integer(), nullable=True),
        sa.Column("rationale", sa.String(), server_default="", nullable=False),
        sa.Column("owner_ref", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("concept_definitions")
