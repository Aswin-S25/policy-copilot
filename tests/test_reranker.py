from uuid import uuid4

from app.retrieval import RetrievedChunk
from app.reranker import rerank_chunks


def test_reranker_returns_top_k(monkeypatch):

    chunks = [
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_title="Policy",
            section_path="Working Hours",
            content="Employees work from 9 AM to 6 PM.",
            chunk_index=0,
            score=0.8,
        ),
        RetrievedChunk(
            chunk_id=uuid4(),
            document_id=uuid4(),
            document_title="Policy",
            section_path="Leave",
            content="Employees receive annual leave.",
            chunk_index=1,
            score=0.7,
        ),
    ]

    result = rerank_chunks(
        query="What are the working hours?",
        chunks=chunks,
        top_k=1,
    )

    assert len(result) == 1