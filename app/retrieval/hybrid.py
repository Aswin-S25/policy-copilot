from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.retrieval.dense import (
    RetrievedChunk,
    retrieve_chunks,
)
from app.retrieval.lexical import retrieve_lexical


@dataclass
class HybridRetrieval:
    chunks: list[RetrievedChunk]
    best_dense_score: int
    lexical_hits: int


def retrieve_hybrid_with_signals(
    db: Session,
    query: str,
    top_k: int = 5,
    candidate_k: int = 20,
    rrf_k: int = 60,
    *,
    roles: Sequence[str],
) -> HybridRetrieval:

    # 1. Dense retrieval
    dense_results = retrieve_chunks(
        db=db,
        query=query,
        top_k=candidate_k,
        min_score=0.0,
        roles=roles
    )

    # 2. Lexical retrieval
    lexical_results = retrieve_lexical(
        db=db,
        query=query,
        top_k=candidate_k,
        roles=roles
    )

    # 3. Calculate RRF scores
    rrf_scores = defaultdict(float)

    for rank, result in enumerate(
        dense_results,
        start=1,
    ):
        rrf_scores[result.chunk_id] += (
            1.0 / (rrf_k + rank)
        )

    for rank, result in enumerate(
        lexical_results,
        start=1,
    ):
        rrf_scores[result.chunk_id] += (
            1.0 / (rrf_k + rank)
        )

    # 4. Keep one representative result per chunk
    chunk_lookup = {}

    for result in dense_results:
        chunk_lookup[result.chunk_id] = result

    for result in lexical_results:
        if result.chunk_id not in chunk_lookup:
            chunk_lookup[result.chunk_id] = result

    # 5. Sort by fused score
    ranked_chunks = sorted(
        rrf_scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    # 6. Convert into existing retrieval response type
    results = []

    for chunk_id, score in ranked_chunks[:top_k]:

        original = chunk_lookup[chunk_id]

        results.append(
            RetrievedChunk(
                chunk_id=original.chunk_id,
                document_id=original.document_id,
                document_title=original.document_title,
                section_path=original.section_path,
                content=original.content,
                chunk_index=original.chunk_index,
                score=score,
            )
        )

    return HybridRetrieval(
        chunks=results,
        best_dense_score=dense_results[0].score if dense_results else 0.0,
        lexical_hits=len(lexical_results),
    )


def retrieve_hybrid(
    db: Session,
    query: str,
    top_k: int = 5,
    candidate_k: int = 20,
    rrf_k: int = 60,
    *,
    roles: Sequence[str],
) -> list[RetrievedChunk]:
    return retrieve_hybrid_with_signals(
        db=db,
        query=query,
        top_k=top_k,
        candidate_k=candidate_k,
        rrf_k=rrf_k,
        roles=roles,
    ).chunks
