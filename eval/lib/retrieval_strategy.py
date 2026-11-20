from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.authz import ALL_ROLES
from app.retrieval.experimental.reranked import retrieve_reranked
from app.retrieval.dense import retrieve_chunks
from app.retrieval.hybrid import retrieve_hybrid
from app.retrieval.experimental.diverse import retreive_diverse
from app.retrieval.lexical import retrieve_lexical
from app.retrieval.experimental.query_planner import plan_query


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
            roles=roles,
        )

    if strategy == "lexical":
        return retrieve_lexical(
            db=db,
            query=query,
            top_k=top_k,
            roles=roles,
        )

    if strategy == "hybrid":
        return retrieve_hybrid(
            db=db,
            query=query,
            top_k=top_k,
            candidate_k=20,
            roles=roles,
        )

    if strategy == "reranked":
        return retrieve_reranked(
            db=db,
            query=query,
            top_k=top_k,
            candidate_k=20,
            roles=roles,
        )

    if strategy == "diverse_2":
        return retreive_diverse(
            db=db,
            query=query,
            top_k=top_k,
            candidate_k=20,
            max_per_document=2,
            roles=roles,
        )

    if strategy == "diverse_3":
        return retreive_diverse(
            db=db,
            query=query,
            top_k=top_k,
            candidate_k=20,
            max_per_document=3,
            roles=roles,
        )

    raise ValueError(f"Unknown retrieval strategy: {strategy}")