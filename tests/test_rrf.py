from uuid import uuid4

from app.rrf import (
    RankedItem,
    reciprocal_rank_fusion,
)


def test_rrf_rewards_documents_in_both_rankings():

    chunk_a = uuid4()
    chunk_b = uuid4()
    chunk_c = uuid4()

    dense = [
        RankedItem(chunk_id=chunk_a, score=0.9),
        RankedItem(chunk_id=chunk_b, score=0.8),
    ]

    lexical = [
        RankedItem(chunk_id=chunk_b, score=0.7),
        RankedItem(chunk_id=chunk_c, score=0.6),
    ]

    results = reciprocal_rank_fusion(
        rankings=[dense, lexical],
        k=60,
    )

    ranked_ids = [
        chunk_id
        for chunk_id, _ in results
    ]

    assert ranked_ids[0] == chunk_b