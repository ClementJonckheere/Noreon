"""conversations history (server-side chat, folders, archive)

Revision ID: a1b2c3d4e5f6
Revises: 6c77ce12453d
Create Date: 2026-07-20 10:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '6c77ce12453d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'conversation_folders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('connection_id', sa.Integer(), nullable=False),
        sa.Column('user_ref', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_conversation_folders_tenant_id'), 'conversation_folders', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_conversation_folders_connection_id'), 'conversation_folders', ['connection_id'], unique=False)
    op.create_index(op.f('ix_conversation_folders_user_ref'), 'conversation_folders', ['user_ref'], unique=False)

    op.create_table(
        'conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.Integer(), nullable=False),
        sa.Column('connection_id', sa.Integer(), nullable=False),
        sa.Column('folder_id', sa.Integer(), nullable=True),
        sa.Column('user_ref', sa.String(length=255), nullable=False, server_default=''),
        sa.Column('title', sa.String(length=255), nullable=False, server_default='Nouvelle conversation'),
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['connection_id'], ['connections.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['folder_id'], ['conversation_folders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_conversations_tenant_id'), 'conversations', ['tenant_id'], unique=False)
    op.create_index(op.f('ix_conversations_connection_id'), 'conversations', ['connection_id'], unique=False)
    op.create_index(op.f('ix_conversations_user_ref'), 'conversations', ['user_ref'], unique=False)
    op.create_index(op.f('ix_conversations_archived'), 'conversations', ['archived'], unique=False)

    op.create_table(
        'conversation_turns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('question', sa.Text(), nullable=False),
        sa.Column('deep', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('response', sa.JSON(), nullable=True),
        sa.Column('error', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_conversation_turns_conversation_id'), 'conversation_turns', ['conversation_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_conversation_turns_conversation_id'), table_name='conversation_turns')
    op.drop_table('conversation_turns')
    op.drop_index(op.f('ix_conversations_archived'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_user_ref'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_connection_id'), table_name='conversations')
    op.drop_index(op.f('ix_conversations_tenant_id'), table_name='conversations')
    op.drop_table('conversations')
    op.drop_index(op.f('ix_conversation_folders_user_ref'), table_name='conversation_folders')
    op.drop_index(op.f('ix_conversation_folders_connection_id'), table_name='conversation_folders')
    op.drop_index(op.f('ix_conversation_folders_tenant_id'), table_name='conversation_folders')
    op.drop_table('conversation_folders')
