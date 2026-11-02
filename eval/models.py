from dataclasses import dataclass

@dataclass
class GoldenCase:
    id: str
    question: str
    relevant_chunk_ids: set[str]
    answerable: bool


@dataclass
class RetrievalResult:
    case_id: int
    retrieved_chunk_ids: list[str]
    relevant_chunk_ids: set[str]


@dataclass
class RetrievalMetrics:
    recall_at_5: float
    mrr: float
    