from uuid import uuid4

from app.context import (
    build_context,
    estimate_tokens,
    format_chunk,
)
from app.retrieval import RetrievedChunk
from ingest.models import ParsedSection
from ingest.upsert import build_section_path


def make_chunk(content: str, score: float = 0.9):
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=uuid4(),
        document_title="Employee Policy",
        section_path="Leave > Annual Leave",
        content=content,
        chunk_index=0,
        score=score,
    )


def test_estimate_tokens():
    text = "a" * 400

    assert estimate_tokens(text) == 100


def test_format_chunk():
    chunk = make_chunk("Employees get 20 days of annual leave.")

    result = format_chunk(
        source_number=1,
        chunk=chunk,
    )

    assert "[Source 1]" in result
    assert "Employee Policy" in result
    assert "Leave > Annual Leave" in result
    assert "20 days" in result


def test_context_respects_budget():
    chunks = [
        make_chunk("A" * 400),
        make_chunk("B" * 400),
        make_chunk("C" * 400),
    ]

    context = build_context(
        chunks,
        max_tokens=250,
    )

    assert context.estimated_tokens <= 250
    assert len(context.chunks) >= 1


def test_section_path():
    sections = [
        ParsedSection(
            title="Leave",
            level=1,
            content="...",
            position=0,
        ),
        ParsedSection(
            title="Annual Leave",
            level=2,
            content="...",
            position=1,
            parent_position=0,
        ),
        ParsedSection(
            title="Carry Forward",
            level=3,
            content="...",
            position=2,
            parent_position=1,
        ),
    ]

    sections_by_position = {
        section.position: section
        for section in sections
    }

    assert build_section_path(
        sections[0],
        sections_by_position,
    ) == "Leave"

    assert build_section_path(
        sections[1],
        sections_by_position,
    ) == "Leave > Annual Leave"

    assert build_section_path(
        sections[2],
        sections_by_position,
    ) == "Leave > Annual Leave > Carry Forward"