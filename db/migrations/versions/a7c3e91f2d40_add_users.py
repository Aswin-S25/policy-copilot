"""add users for username/password sign-in

Revision ID: a7c3e91f2d40
Revises: 0c2b8e4aa103
Create Date: 2026-11-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c3e91f2d40'
down_revision: Union[str, Sequence[str], None] = '0c2b8e4aa103'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("roles", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(),
            server_default=sa.true(), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )


def downgrade() -> None:
    op.drop_table("users")
