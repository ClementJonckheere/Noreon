"""concept references (E1 propagation ledger) + arbitration audit

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa


revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "concept_references",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("concept_id", sa.Integer(), sa.ForeignKey("business_concepts.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("ref_label", sa.String(length=255), server_default="", nullable=False),
        sa.Column("ref_id", sa.String(length=64), nullable=True),
        sa.Column("connection_id", sa.Integer(), nullable=True),
        sa.Column("immutable", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="active", index=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "concept_arbitrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("concept_id", sa.Integer(), sa.ForeignKey("business_concepts.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("chosen_definition_id", sa.Integer(), nullable=False),
        sa.Column("definition_version", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column("propagation", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("concept_arbitrations")
    op.drop_table("concept_references")
