import re
from dataclasses import dataclass

@dataclass
class QueryPlan:
    strategy: str
    reason: str


IDENTIFIER_PATTERN = re.compile(
    r"\b[A-Z]{2,}[-_]?\d+[A-Z0-9_-]*\b"
)


def plan_query(query: str) -> QueryPlan:
    
    normalized = query.strip()
    
    if IDENTIFIER_PATTERN.search(normalized):
        return QueryPlan(
            strategy="lexical",
            reason="Contains a structured identifier or policy code",
        )
        
    return QueryPlan(
        strategy="hybrid",
        reason="Uses natural-language retrieval"
    )