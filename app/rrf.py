from dataclasses import dataclass
from uuid import UUID

@dataclass
class RankedItem:
    chunk_id: UUID
    score: float


def reciprocal_rank_fusion(
    rankings: list[list[RankedItem]],
    k: int = 60
) -> list[list[UUID, float]]:
    
    scores = dict[UUID, float] = []
    for ranking in rankings:
        for rank, item in enumerate(
            ranking,
            start=1
        ):
            contribution = 1.0 / (k+rank)
            
            scores[item.chunk_id] = (
                scores.get(item.chunk_id, 0.0)
                + contribution
            )
    return sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True
    )