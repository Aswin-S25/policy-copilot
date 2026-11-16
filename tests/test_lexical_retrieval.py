from app.lexical_retreival import retrieve_lexical
from ingest.models import ParsedDocument, ParsedSection
from ingest.upsert import ingest_document


def seed_document(db):

    annual = "Employees receive 24 days of annual leave per year."
    remote = "Employees can work remotely with manager approval."

    ingest_document(
        db,
        ParsedDocument(
            title="Employee Handbook",
            source="employee_handbook.md",
            document_type="markdown",
            content=f"{annual}\n{remote}",
            sections=[
                ParsedSection(
                    title="Annual Leave",
                    level=2,
                    content=annual,
                    position=0,
                ),
                ParsedSection(
                    title="Remote Work",
                    level=2,
                    content=remote,
                    position=1,
                ),
            ],
        ),
    )


def test_lexical_retrieval(db):
    seed_document(db)

    results = retrieve_lexical(
        db=db,
        query="annual leave",
        top_k=5,
    )

    assert len(results) > 0

    for result in results:
        assert result.chunk_id is not None
        assert result.score >= 0

    assert results[0].section_path == "Annual Leave"
