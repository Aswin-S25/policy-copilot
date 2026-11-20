import uuid

from sqlalchemy import select

from app.core.display import chunk_display_titles, display_titles, is_file_name, relabel_citations
from app.core.models import Chunk
from ingest.models import ParsedDocument, ParsedSection
from ingest.upsert import ingest_document


def ingest(db, title, sections):
    content = "\n\n".join(text for _, text in sections) or "body"
    return ingest_document(
        db,
        ParsedDocument(
            title=title,
            source=f"data/uploads/{title}.md",
            document_type="markdown",
            content=content,
            sections=[
                ParsedSection(title=heading, level=1, content=text, position=i)
                for i, (heading, text) in enumerate(sections)
            ],
        ),
        allowed_roles=["employee"],
    )


def test_file_names_are_recognised():
    assert is_file_name("23551930-db17-4ccf-a993-85ca0b825190")
    assert is_file_name("remote_hybrid_work_policy")
    assert is_file_name("leave.md")
    assert not is_file_name("Remote and Hybrid Work Policy")


def test_upload_name_is_replaced_by_first_heading(db):
    upload = str(uuid.uuid4())
    document = ingest(db, upload, [("Remote and Hybrid Work Policy", "Intro."), ("1. Eligibility", "Who.")])

    assert display_titles(db, [document.id]) == {document.id: "Remote and Hybrid Work Policy"}


def test_preamble_stored_under_the_file_name_is_skipped(db):
    # parse_markdown stores text before the first heading as a section
    # titled with the file name.
    document = ingest(db, "hr_policy", [("hr_policy", "Preamble."), ("HR Policy", "Body.")])

    assert display_titles(db, [document.id])[document.id] == "HR Policy"


def test_real_titles_are_kept(db):
    document = ingest(db, "Employee Handbook", [("1. Leave", "Leave text.")])

    assert display_titles(db, [document.id])[document.id] == "Employee Handbook"


def test_citations_are_relabelled_by_chunk(db):
    document = ingest(db, str(uuid.uuid4()), [("Travel Policy", "Book through the portal.")])
    chunk_id = db.scalars(select(Chunk.id).where(Chunk.document_id == document.id)).first()

    assert chunk_display_titles(db, [chunk_id]) == {chunk_id: "Travel Policy"}
    citation = {"source": 1, "document": document.title, "section": None,
                "chunk_id": str(chunk_id), "score": 0.5}
    assert relabel_citations(db, [citation]) == [{**citation, "document": "Travel Policy"}]


def test_unknown_ids_are_ignored(db):
    assert display_titles(db, [uuid.uuid4()]) == {}
    assert display_titles(db, []) == {}
