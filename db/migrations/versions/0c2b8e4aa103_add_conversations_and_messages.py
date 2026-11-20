"""add conversations and messages

Revision ID: 0c2b8e4aa103
Revises: 62318f15d849
Create Date: 2026-11-19 03:13:41.939699

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c2b8e4aa103'
down_revision: Union[str, Sequence[str], None] = '62318f15d849'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_sub", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversations_owner_sub_updated_at",
        "conversations",
        ["owner_sub", "updated_at"],
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("sender", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("standalone_question", sa.Text(), nullable=True),
        sa.Column(
            "source_chunk_ids", postgresql.ARRAY(sa.UUID()), nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id", "position",
            name="uq_message_conversation_position",
        ),
        sa.CheckConstraint(
            "sender IN ('user', 'assistant')",
            name="ck_messages_sender",
        ),
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_index(
        "ix_conversations_owner_sub_updated_at", table_name="conversations",
    )
    op.drop_table("conversations")