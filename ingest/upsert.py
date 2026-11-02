
from collections import defaultdict

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.models import Document, Section, Chunk
from ingest.hashing import hash_content
from ingest.models import ParsedDocument, ParsedSection
from ingest.chunk import chunk_sections


def build_section_path(
    section: ParsedSection,
    sections_by_position: dict[int, ParsedSection],
) -> str:
    path = [section.title]

    parent_position = section.parent_position

    while parent_position is not None:
        parent = sections_by_position[parent_position]
        path.append(parent.title)
        parent_position = parent.parent_position

    path.reverse()

    return " > ".join(path)

def ingest_document(
    db: Session,
    parsed: ParsedDocument,
) -> Document:

    document_hash = hash_content(parsed.content)

    # Not `with db.begin()`: the session may already be in an
    # autobegun transaction from earlier queries by the caller.
    try:

        # 1. Find existing document
        document = db.scalar(
            select(Document).where(
                Document.source == parsed.source
            )
        )

        # 2. Skip completely unchanged documents
        if document and document.content_hash == document_hash:
            return document

        # 3. Create or update document
        if document is None:
            document = Document(
                title=parsed.title,
                source=parsed.source,
                document_type=parsed.document_type,
                content_hash=document_hash,
            )
            db.add(document)
            db.flush()

            old_chunks = []

        else:
            document.title = parsed.title
            document.document_type = parsed.document_type
            document.content_hash = document_hash

            old_chunks = list(
                db.scalars(
                    select(Chunk).where(
                        Chunk.document_id == document.id
                    )
                )
            )

        # 4. Temporarily move existing chunk indexes.
        # This avoids UNIQUE constraint collisions when indexes shift.
        for i, chunk in enumerate(old_chunks):
            chunk.chunk_index = -(i + 1)

        db.flush()

        # 5. Rebuild section hierarchy
        db.execute(
            delete(Section).where(
                Section.document_id == document.id
            )
        )
        db.flush()

        sections_by_position = {
            section.position: section
            for section in parsed.sections
        }
        section_map = {}

        for section in parsed.sections:
            parent_id = None

            if section.parent_position is not None:
                parent_id = section_map.get(
                    section.parent_position
                )

            db_section = Section(
                document_id=document.id,
                parent_id=parent_id,
                title=section.title,
                section_path=build_section_path(
                    section,
                    sections_by_position,
                ),
                position=section.position,
            )

            db.add(db_section)
            db.flush()

            section_map[section.position] = db_section.id

        # 6. Generate new chunks
        new_chunks = chunk_sections(parsed.sections)

        # Group existing chunks by content hash.
        # Lists handle duplicate identical chunks.
        existing_by_hash = defaultdict(list)

        for chunk in old_chunks:
            existing_by_hash[chunk.content_hash].append(chunk)

        reused_ids = set()

        # 7. Reconcile new chunks against existing chunks
        for new_chunk in new_chunks:

            new_hash = hash_content(new_chunk.content)

            section_id = section_map.get(
                new_chunk.section_position
            )

            candidates = existing_by_hash[new_hash]

            if candidates:
                # Same content: reuse existing database row
                # and preserve its embedding.
                existing_chunk = candidates.pop(0)

                existing_chunk.chunk_index = new_chunk.index
                existing_chunk.section_id = section_id

                reused_ids.add(existing_chunk.id)

            else:
                # New content: insert without an embedding.
                db.add(
                    Chunk(
                        document_id=document.id,
                        section_id=section_id,
                        chunk_index=new_chunk.index,
                        content=new_chunk.content,
                        content_hash=new_hash,
                        embedding=None,
                        embedding_model=None,
                    )
                )

        # 8. Delete chunks that no longer exist
        for old_chunk in old_chunks:
            if old_chunk.id not in reused_ids:
                db.delete(old_chunk)

        db.commit()

    except Exception:
        db.rollback()
        raise

    db.refresh(document)

    return document
