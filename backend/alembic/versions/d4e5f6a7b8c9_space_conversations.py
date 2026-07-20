"""space-scoped conversations (space_id on conversations/folders, connection on turns)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-07-20 13:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e5f6a7b8c9'
down_revision: str | None = 'c3d4e5f6a7b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # conversations : connection_id devient optionnel, ajout de space_id.
    op.alter_column('conversations', 'connection_id', existing_type=sa.Integer(), nullable=True)
    op.add_column('conversations', sa.Column('space_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_conversations_space_id'), 'conversations', ['space_id'], unique=False)
    op.create_foreign_key(
        'fk_conversations_space', 'conversations', 'spaces', ['space_id'], ['id'], ondelete='CASCADE'
    )

    # conversation_folders : idem.
    op.alter_column('conversation_folders', 'connection_id', existing_type=sa.Integer(), nullable=True)
    op.add_column('conversation_folders', sa.Column('space_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_conversation_folders_space_id'), 'conversation_folders', ['space_id'], unique=False)
    op.create_foreign_key(
        'fk_conversation_folders_space', 'conversation_folders', 'spaces', ['space_id'], ['id'], ondelete='CASCADE'
    )

    # conversation_turns : mémorise la source du tour.
    op.add_column('conversation_turns', sa.Column('connection_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_conversation_turns_connection', 'conversation_turns', 'connections',
        ['connection_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_conversation_turns_connection', 'conversation_turns', type_='foreignkey')
    op.drop_column('conversation_turns', 'connection_id')

    op.drop_constraint('fk_conversation_folders_space', 'conversation_folders', type_='foreignkey')
    op.drop_index(op.f('ix_conversation_folders_space_id'), table_name='conversation_folders')
    op.drop_column('conversation_folders', 'space_id')
    op.alter_column('conversation_folders', 'connection_id', existing_type=sa.Integer(), nullable=False)

    op.drop_constraint('fk_conversations_space', 'conversations', type_='foreignkey')
    op.drop_index(op.f('ix_conversations_space_id'), table_name='conversations')
    op.drop_column('conversations', 'space_id')
    op.alter_column('conversations', 'connection_id', existing_type=sa.Integer(), nullable=False)
