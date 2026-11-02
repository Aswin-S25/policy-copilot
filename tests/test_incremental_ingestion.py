
from sqlalchemy import select, func

from app.models import Document, Chunk
from ingest.models import ParsedDocument, ParsedSection
from ingest.upsert import ingest_document


def make_document(content_a, content_b):

    return ParsedDocument(
        title="Employee Handbook",
        source="employee_handbook.md",
        document_type="markdown",
        content=f"{content_a}\n{content_b}",
        sections=[
            ParsedSection(
                title="Leave Policy",
                level=2,
                content=content_a,
                position=0,
            ),
            ParsedSection(
                title="Remote Work",
                level=2,
                content=content_b,
                position=1,
            ),
        ],
    )


def test_unchanged_document_is_skipped(db):

    parsed = make_document(
        "Employees receive 12 days of leave.",
        "Employees can work remotely.",
    )

    first = ingest_document(db, parsed)

    first_chunks = list(
        db.scalars(
            select(Chunk).where(
                Chunk.document_id == first.id
            )
        )
    )

    second = ingest_document(db, parsed)

    second_chunks = list(
        db.scalars(
            select(Chunk).where(
                Chunk.document_id == second.id
            )
        )
    )

    assert first.id == second.id
    assert len(first_chunks) == len(second_chunks)

    assert {c.id for c in first_chunks} == {
        c.id for c in second_chunks
    }


def test_unchanged_chunk_preserves_embedding(db):

    parsed_v1 = make_document(
        "Employees receive 12 days of leave.",
        "Employees can work remotely.",
    )

    document = ingest_document(db, parsed_v1)

    chunks = list(
        db.scalars(
            select(Chunk).where(
                Chunk.document_id == document.id
            )
        )
    )

    first_chunk = chunks[0]

    fake_embedding = [0.1] * 384

    first_chunk.embedding = fake_embedding
    first_chunk.embedding_model = "test-model"

    db.commit()

    parsed_v2 = make_document(
        "Employees receive 12 days of leave.",
        "Employees can work remotely with approval.",
    )

    ingest_document(db, parsed_v2)

    preserved_chunk = db.get(Chunk, first_chunk.id)

    assert preserved_chunk is not None
    assert preserved_chunk.embedding == fake_embedding
    assert preserved_chunk.embedding_model == "test-model"


def test_changed_chunk_gets_new_identity(db):

    parsed_v1 = make_document(
        "Employees receive 12 days of leave.",
        "Employees can work remotely.",
    )

    document = ingest_document(db, parsed_v1)

    old_chunks = list(
        db.scalars(
            select(Chunk).where(
                Chunk.document_id == document.id
            )
        )
    )

    old_first_id = old_chunks[0].id

    parsed_v2 = make_document(
        "Employees receive 20 days of leave.",
        "Employees can work remotely.",
    )

    ingest_document(db, parsed_v2)

    new_chunks = list(
        db.scalars(
            select(Chunk).where(
                Chunk.document_id == document.id
            )
        )
    )

    assert len(new_chunks) == 2
    assert old_first_id not in {c.id for c in new_chunks}


def test_deleted_chunk_is_removed(db):

    parsed_v1 = make_document(
        "Employees receive 12 days of leave.",
        "Employees can work remotely.",
    )

    document = ingest_document(db, parsed_v1)

    parsed_v2 = ParsedDocument(
        title="Employee Handbook",
        source="employee_handbook.md",
        document_type="markdown",
        content="Employees receive 12 days of leave.",
        sections=[
            ParsedSection(
                title="Leave Policy",
                level=2,
                content="Employees receive 12 days of leave.",
                position=0,
            )
        ],
    )

    ingest_document(db, parsed_v2)

    count = db.scalar(
        select(func.count())
        .select_from(Chunk)
        .where(Chunk.document_id == document.id)
    )

    assert count == 1
