"""updated embedding dimention to 384

Revision ID: 5720227a88c6
Revises: 56a4157f4ae2
Create Date: 2026-11-02 00:16:05.247773

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5720227a88c6'
down_revision: Union[str, Sequence[str], None] = '56a4157f4ae2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute(
        """
        ALTER TABLE chunks
        ALTER COLUMN embedding TYPE vector(384)
        USING NULL
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE chunks
        ALTER COLUMN embedding TYPE vector(1536)
        USING NULL
        """
    )