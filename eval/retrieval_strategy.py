from sqlalchemy.orm import Session

from app.retrieval import retrieve_chunks
from app.hybrid_retrieval import retrieve_hybrid


def retrieve_by_strategy(
    db: Session,
    query: str,
    strategy: str,
    top_k: int = 5,
):

    if strategy == "dense":
        return retrieve_chunks(
            db=db,
            query=query,
            top_k=top_k,
            min_score=0.0,
        )

    if strategy == "hybrid":
        return retrieve_hybrid(
            db=db,
            query=query,
            top_k=top_k,
            candidate_k=20,
        )

    raise ValueError(
        f"Unknown retrieval strategy: {strategy}"
    )