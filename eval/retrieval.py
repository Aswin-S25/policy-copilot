from sqlalchemy.orm import Session

from app.retrieval import retrieve_chunks
from eval.models import (
    GoldenCase,
    RetrievalMetrics,
    RetrievalResult,
)

def evaluate_retrieval_case(
    db: Session,
    case: GoldenCase,
    top_k: int = 5,
) -> RetrievalResult:
    
    results = retrieve_chunks(
        db=db,
        query=case.question,
        top_k=top_k,
        min_score=0.0,
    )
    
    retrieved_ids = [
        str(result.chunk_id)
        for result in results
    ]
    
    return RetrievalResult(
        case_id=case.id,
        retrieved_chunk_ids=retrieved_ids,
        relevant_chunk_ids=case.relevant_chunk_ids
    )

def recall_at_k(
    result: RetrievalResult,
    k: int,
) -> float:

    if not result.relevant_chunk_ids:
        return 1.0

    retrieved = set(
        result.retrieved_chunk_ids[:k]
    )

    relevant = result.relevant_chunk_ids

    return (
        len(retrieved & relevant)
        / len(relevant)
    )

def reciprocal_rank(
    result: RetrievalResult,
) -> float:

    if not result.relevant_chunk_ids:
        return 1.0

    for rank, chunk_id in enumerate(
        result.retrieved_chunk_ids,
        start=1,
    ):
        if chunk_id in result.relevant_chunk_ids:
            return 1.0 / rank

    return 0.0


def calculate_metrics(
    results: list[RetrievalResult],
) -> RetrievalMetrics:

    answerable = [
        result
        for result in results
        if result.relevant_chunk_ids
    ]

    if not answerable:
        return RetrievalMetrics(
            recall_at_5=0.0,
            mrr=0.0,
        )

    recall = sum(
        recall_at_k(result, 5)
        for result in answerable
    ) / len(answerable)

    mrr = sum(
        reciprocal_rank(result)
        for result in answerable
    ) / len(answerable)

    return RetrievalMetrics(
        recall_at_5=recall,
        mrr=mrr,
    )