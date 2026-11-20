"""Policy document library: the documents the caller's roles can read.

Read-only. Uploading stays at POST /documents/ingest (admin only).

What is deliberately NOT returned:
- `source`: the server-side file path (uploads are stored under random
  names); meaningless to readers and it exposes the server's layout.
- the full ACL: `access` lists only the caller's own roles that grant the
  document, so the list never reveals which other roles can read it.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select

from app.core.db import SessionLocal
from app.core.display import display_titles
from app.core.models import Chunk, Document, DocumentACL, Section
from app.core.security import Principal, get_current_principal

router = APIRouter(prefix="/documents", tags=["documents"])


def document_status(chunks: int, unembedded: int) -> str:
    """ready: fully searchable. indexing: ingestion stored chunks that are
    still waiting for embeddings. empty: no searchable text was found."""
    if chunks == 0:
        return "empty"
    return "indexing" if unembedded else "ready"


def readable_documents_query(roles: list[str]):
    """Documents readable by any of `roles`, with the granting roles,
    chunk/embedding counts and section count. Unordered: the endpoint sorts
    by display name, which is computed after the query."""
    # The caller's roles that grant read access; the inner join below also
    # makes this the permission filter.
    access = (
        select(
            DocumentACL.document_id,
            func.array_agg(DocumentACL.role).label("roles"),
        )
        .where(DocumentACL.role.in_(roles), DocumentACL.permission == "read")
        .group_by(DocumentACL.document_id)
        .subquery()
    )
    chunks = (
        select(
            Chunk.document_id,
            func.count().label("total"),
            func.count().filter(Chunk.embedding.is_(None)).label("unembedded"),
        )
        .group_by(Chunk.document_id)
        .subquery()
    )
    sections = (
        select(Section.document_id, func.count().label("total"))
        .group_by(Section.document_id)
        .subquery()
    )

    return (
        select(
            Document,
            access.c.roles,
            func.coalesce(chunks.c.total, 0),
            func.coalesce(chunks.c.unembedded, 0),
            func.coalesce(sections.c.total, 0),
        )
        .join(access, access.c.document_id == Document.id)
        .outerjoin(chunks, chunks.c.document_id == Document.id)
        .outerjoin(sections, sections.c.document_id == Document.id)
    )


@router.get("")
def list_documents(principal: Principal = Depends(get_current_principal)):
    roles = principal.document_roles
    if not roles:
        return {"documents": []}

    with SessionLocal() as db:
        rows = db.execute(readable_documents_query(roles)).all()
        names = display_titles(db, (document.id for document, *_ in rows))

    rows.sort(key=lambda row: names.get(row[0].id, row[0].title).casefold())
    return {
        "documents": [
            {
                "id": str(document.id),
                "title": names.get(document.id, document.title),
                "document_type": document.document_type,
                "section_count": section_count,
                "status": document_status(chunk_count, unembedded),
                "access": sorted(access_roles),
                "created_at": document.created_at.isoformat(),
                "updated_at": (document.updated_at or document.created_at).isoformat(),
            }
            for document, access_roles, chunk_count, unembedded, section_count in rows
        ]
    }
