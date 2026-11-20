"""add full text search to chunks

Revision ID: 62318f15d849
Revises: 5720227a88c6
Create Date: 2026-11-03 00:52:39.462698

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '62318f15d849'
down_revision: Union[str, Sequence[str], None] = '5720227a88c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("""
        ALTER TABLE chunks
        ADD COLUMN search_vector tsvector
    """)

    op.execute("""
        UPDATE chunks c
        SET search_vector =
            setweight(
                to_tsvector(
                    'english',
                    coalesce(d.title, '')
                ),
                'A'
            )
            ||
            setweight(
                to_tsvector(
                    'english',
                    coalesce(s.section_path, '')
                ),
                'B'
            )
            ||
            setweight(
                to_tsvector(
                    'english',
                    coalesce(c.content, '')
                ),
                'C'
            )
        FROM chunks c2
        JOIN documents d
            ON d.id = c2.document_id
        LEFT JOIN sections s
            ON s.id = c2.section_id
        WHERE c.id = c2.id
    """)

    op.execute("""
        CREATE INDEX ix_chunks_search_vector
        ON chunks
        USING GIN(search_vector)
    """)


def downgrade():
    op.execute("""
        DROP INDEX IF EXISTS ix_chunks_search_vector
    """)

    op.execute("""
        ALTER TABLE chunks
        DROP COLUMN IF EXISTS search_vector
    """)