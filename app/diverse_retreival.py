from sqlalchemy.orm import Session

from app.diversity import apply_document_cap
from app.hybrid_retrieval import retrieve_hybrid
from app.retrieval import RetrievedChunk


def retreive_diverse(
    db: Session,
    query: str,
    top_k: int = 5,
    candidate_k: int = 20,
    max_per_document: int = 2
) -> list[RetrievedChunk]:
    
    # Fetch the full candidate pool so the cap has chunks to fall back on.
    candidates = retrieve_hybrid(
        db=db,
        query=query,
        top_k=candidate_k,
        candidate_k=candidate_k
    )
    
    
    return apply_document_cap(
        chunks=candidates,
        top_k=top_k,
        max_per_document=max_per_document
    )