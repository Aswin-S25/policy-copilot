from dataclasses import dataclass
from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.retrieval.dense import RetrievedChunk


RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    return CrossEncoder(RERANKER_MODEL)


def build_reranker_text(chunk: RetrievedChunk) -> str:
    section = chunk.section_path or "Unknown section"

    return (
        f"Document: {chunk.document_title}\n"
        f"Section: {section}\n\n"
        f"{chunk.content}"
    )


def rerank_chunks(
    query: str,
    chunks: list[RetrievedChunk],
    top_k: int = 5,
) -> list[RetrievedChunk]:

    if not chunks:
        return []

    reranker = get_reranker()

    pairs = [
        (
            query,
            build_reranker_text(chunk),
        )
        for chunk in chunks
    ]

    scores = reranker.predict(
        pairs,
        show_progress_bar=False,
    )

    ranked = sorted(
        zip(chunks, scores),
        key=lambda item: float(item[1]),
        reverse=True,
    )

    return [
        chunk
        for chunk, _ in ranked[:top_k]
    ]