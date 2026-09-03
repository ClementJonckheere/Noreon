"""report source tracking for posterior quality incidents

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-08-12

Un rapport est un INSTANTANÉ validé. Pour signaler un « incident postérieur »
(une réserve de qualité apparue APRÈS validation) sans altérer son contenu, on
mémorise la source et les tables sur lesquelles il s'appuie.
"""
from alembic import op
import sqlalchemy as sa


revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reports", sa.Column("source_connection_id", sa.Integer(), nullable=True))
    op.add_column("reports", sa.Column("source_tables", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("reports", "source_tables")
    op.drop_column("reports", "source_connection_id")
