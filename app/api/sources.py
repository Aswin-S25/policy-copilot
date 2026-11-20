"""Cited source passages.

A citation names a chunk; this returns the chunk's text so a reader can
check an answer against the policy wording. The same document ACL as
retrieval applies (readable_by), so the endpoint cannot be used to read a
document the caller's roles do not grant.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.authz import readable_by
from app.core.db import SessionLocal
from app.core.display import display_titles
from app.core.models import Chunk, Document, Section
from app.core.security import Principal, get_current_principal

router = APIRouter(prefix="/chunks", tags=["sources"])


def _not_found() -> HTTPException:
    # Identical for "does not exist" and "not readable by you": never
    # confirm that a restricted chunk id is valid.
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found.")


@router.get("/{chunk_id}")
def read_chunk(
    chunk_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
):
    roles = principal.document_roles
    if not roles:
        raise _not_found()

    with SessionLocal() as db:
        row = db.execute(
            select(
                Chunk.id,
                Chunk.document_id,
                Chunk.chunk_index,
                Chunk.content,
                Document.title,
                Section.section_path,
            )
            .join(Document, Document.id == Chunk.document_id)
            .outerjoin(Section, Section.id == Chunk.section_id)
            .where(Chunk.id == chunk_id, readable_by(roles))
        ).one_or_none()

        if row is None:
            raise _not_found()
        title = display_titles(db, [row.document_id]).get(row.document_id, row.title)

    # Same keys as the retrieved_chunks entries of POST /search.
    return {
        "chunk_id": str(row.id),
        "document_id": str(row.document_id),
        "document_title": title,
        "section_path": row.section_path,
        "chunk_index": row.chunk_index,
        "content": row.content,
    }
