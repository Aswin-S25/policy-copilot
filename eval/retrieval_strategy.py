from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.authz import ALL_ROLES
from app.reranked_retrieval import retrieve_reranked
from app.retrieval import retrieve_chunks
from app.hybrid_retrieval import retrieve_hybrid
from app.diverse_retreival import retreive_diverse
from app.lexical_retreival import retrieve_lexical
from app.query_planner import plan_query


def retrieve_by_strategy(
    db: Session,
    query: str,
    strategy: str,
    top_k: int = 5,
    roles: Sequence[str] = ALL_ROLES,
):
    if strategy == "auto":
        plan = plan_query(query)
        strategy = plan.strategy

    if strategy == "dense":
        return retrieve_chunks(
            db=db,
            query=query,
            top_k=top_k,
            min_score=0.0,
        )

    if strategy == "lexical":
        return retrieve_lexical(
            db=db,
            query=query,
            top_k=top_k,
        )

    if strategy == "hybrid":
        return retrieve_hybrid(
            db=db,
            query=query,
            top_k=top_k,
            candidate_k=20,
        )

    if strategy == "reranked":
        return retrieve_reranked(
            db=db,
            query=query,
            top_k=top_k,
            candidate_k=20,
        )

    if strategy == "diverse_2":
        return retreive_diverse(
            db=db,
            query=query,
            top_k=top_k,
            candidate_k=20,
            max_per_document=2,
        )

    if strategy == "diverse_3":
        return retreive_diverse(
            db=db,
            query=query,
            top_k=top_k,
            candidate_k=20,
            max_per_document=3,
        )

    raise ValueError(f"Unknown retrieval strategy: {strategy}")