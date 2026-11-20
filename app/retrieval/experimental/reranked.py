from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.retrieval.hybrid import retrieve_hybrid
from app.retrieval.dense import RetrievedChunk
from app.retrieval.experimental.reranker import rerank_chunks


def retrieve_reranked(
    db: Session,
    query: str,
    top_k: int = 5,
    candidate_k: int = 20,
    *,
    roles: Sequence[str],
) -> list[RetrievedChunk]:

    candidates = retrieve_hybrid(
        db=db,
        query=query,
        top_k=candidate_k,
        candidate_k=candidate_k,
        roles=roles,
    )

    return rerank_chunks(
        query=query,
        chunks=candidates,
        top_k=top_k,
    )