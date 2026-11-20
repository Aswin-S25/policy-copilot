"""Human-readable document names for API responses.

Ingestion stores a document's file name as its title (ingest/parse.py uses
the file stem), and uploads are saved under random names, so stored titles
look like "23551930-db17-...". The document's real name is its first
heading, which ingestion stores as the section at the lowest position.

This is presentation only. Stored titles are left alone because they feed
chunk embeddings, chunk content hashes and the model's context; changing
them would re-create every chunk (new ids) and move evaluation results.
"""
import re
import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import Chunk, Document, Section

# A stored title with no whitespace is a file name ("leave.md", "hr_policy",
# a UUID), not a name a person gave the document.
_FILE_NAME = re.compile(r"^\S+$")


def is_file_name(title: str) -> bool:
    return bool(_FILE_NAME.match(title.strip()))


def display_titles(db: Session, document_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Display name per document: its first heading when the stored title is
    a file name, otherwise the stored title. Missing ids are omitted."""
    document_ids = list(set(document_ids))
    if not document_ids:
        return {}

    titles = dict(
        db.execute(select(Document.id, Document.title).where(Document.id.in_(document_ids))).all()
    )
    needs_heading = [doc_id for doc_id, title in titles.items() if is_file_name(title)]
    if needs_heading:
        # First section by position whose title isn't the file name itself
        # (a preamble before the first heading is stored under the file name).
        first_headings = db.execute(
            select(Section.document_id, Section.title)
            .join(Document, Document.id == Section.document_id)
            .where(Section.document_id.in_(needs_heading), Section.title != Document.title)
            .order_by(Section.document_id, Section.position)
            .distinct(Section.document_id)
        ).all()
        titles.update(first_headings)
    return titles


def chunk_display_titles(db: Session, chunk_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Display name of each chunk's document."""
    chunk_ids = list(set(chunk_ids))
    if not chunk_ids:
        return {}
    chunk_documents = dict(
        db.execute(select(Chunk.id, Chunk.document_id).where(Chunk.id.in_(chunk_ids))).all()
    )
    names = display_titles(db, chunk_documents.values())
    return {chunk_id: names[doc_id] for chunk_id, doc_id in chunk_documents.items() if doc_id in names}


def relabel_citations(db: Session, citations: list[dict]) -> list[dict]:
    """Citation dicts (Citation.to_dict() shape) with display document names."""
    names = chunk_display_titles(db, (uuid.UUID(c["chunk_id"]) for c in citations))
    return [
        {**c, "document": names.get(uuid.UUID(c["chunk_id"]), c["document"])}
        for c in citations
    ]
