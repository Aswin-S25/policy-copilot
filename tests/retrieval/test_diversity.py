from uuid import uuid4

from app.retrieval.experimental.diversity import apply_document_cap
from app.retrieval.dense import RetrievedChunk


def make_chunk(document_id, index):
    return RetrievedChunk(
        chunk_id=uuid4(),
        document_id=document_id,
        document_title=f"Document {document_id}",
        section_path="Test Section",
        content=f"Chunk {index}",
        chunk_index=index,
        score=0.9 - index * 0.1,
    )


def test_document_cap_limits_chunks_per_document():
    document_a = uuid4()
    document_b = uuid4()

    chunks = [
        make_chunk(document_a, 0),
        make_chunk(document_a, 1),
        make_chunk(document_a, 2),
        make_chunk(document_b, 0),
        make_chunk(document_b, 1),
    ]

    results = apply_document_cap(
        chunks,
        top_k=5,
        max_per_document=2,
    )

    counts = {}

    for chunk in results:
        counts[chunk.document_id] = (
            counts.get(chunk.document_id, 0) + 1
        )

    assert len(results) == 4
    assert all(count <= 2 for count in counts.values())

def test_document_cap_preserves_original_ranking():
    document_a = uuid4()
    document_b = uuid4()

    chunks = [
        make_chunk(document_a, 0),
        make_chunk(document_a, 1),
        make_chunk(document_a, 2),  # skipped by the cap
        make_chunk(document_b, 3),
        make_chunk(document_a, 4),  # skipped by the cap
        make_chunk(document_b, 5),
    ]

    results = apply_document_cap(chunks, top_k=5, max_per_document=2)

    expected = [chunks[0], chunks[1], chunks[3], chunks[5]]
    assert [c.chunk_id for c in results] == [c.chunk_id for c in expected]


def test_document_cap_fills_top_k_when_enough_documents():
    documents = [uuid4() for _ in range(4)]
    chunks = [
        make_chunk(documents[i // 3], i)  # 3 chunks per document, in order
        for i in range(12)
    ]

    results = apply_document_cap(chunks, top_k=5, max_per_document=2)

    assert len(results) == 5


def test_document_cap_is_noop_when_cap_not_binding():
    document_a = uuid4()
    chunks = [make_chunk(document_a, i) for i in range(5)]

    results = apply_document_cap(chunks, top_k=5, max_per_document=5)

    assert [c.chunk_id for c in results] == [c.chunk_id for c in chunks]
