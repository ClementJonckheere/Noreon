"""spaces, membership, connection attach, table/column governance

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-20 11:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: str | None = 'a1b2c3d4e5f6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'spaces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(), nullable=False, server_default=''),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'slug', name='uq_space_tenant_slug'),
    )
    op.create_index(op.f('ix_spaces_tenant_id'), 'spaces', ['tenant_id'], unique=False)

    op.create_table(
        'space_connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('space_id', sa.Integer(), nullable=False),
        sa.Column('connection_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['space_id'], ['spaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('space_id', 'connection_id', name='uq_space_connection'),
    )
    op.create_index(op.f('ix_space_connections_space_id'), 'space_connections', ['space_id'], unique=False)
    op.create_index(op.f('ix_space_connections_connection_id'), 'space_connections', ['connection_id'], unique=False)

    op.create_table(
        'space_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('space_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False, server_default='member'),
        sa.ForeignKeyConstraint(['space_id'], ['spaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('space_id', 'user_id', name='uq_space_member'),
    )
    op.create_index(op.f('ix_space_members_space_id'), 'space_members', ['space_id'], unique=False)
    op.create_index(op.f('ix_space_members_user_id'), 'space_members', ['user_id'], unique=False)

    op.create_table(
        'space_table_access',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('space_id', sa.Integer(), nullable=False),
        sa.Column('connection_id', sa.Integer(), nullable=False),
        sa.Column('schema_name', sa.String(length=255), nullable=False),
        sa.Column('table_name', sa.String(length=255), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['space_id'], ['spaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('space_id', 'connection_id', 'schema_name', 'table_name', name='uq_space_table_access'),
    )
    op.create_index(op.f('ix_space_table_access_space_id'), 'space_table_access', ['space_id'], unique=False)
    op.create_index(op.f('ix_space_table_access_connection_id'), 'space_table_access', ['connection_id'], unique=False)

    op.create_table(
        'space_column_access',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('space_id', sa.Integer(), nullable=False),
        sa.Column('connection_id', sa.Integer(), nullable=False),
        sa.Column('schema_name', sa.String(length=255), nullable=False),
        sa.Column('table_name', sa.String(length=255), nullable=False),
        sa.Column('column_name', sa.String(length=255), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['space_id'], ['spaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('space_id', 'connection_id', 'schema_name', 'table_name', 'column_name',
                            name='uq_space_column_access'),
    )
    op.create_index(op.f('ix_space_column_access_space_id'), 'space_column_access', ['space_id'], unique=False)
    op.create_index(op.f('ix_space_column_access_connection_id'), 'space_column_access', ['connection_id'], unique=False)


def downgrade() -> None:
    op.drop_table('space_column_access')
    op.drop_table('space_table_access')
    op.drop_table('space_members')
    op.drop_table('space_connections')
    op.drop_index(op.f('ix_spaces_tenant_id'), table_name='spaces')
    op.drop_table('spaces')
