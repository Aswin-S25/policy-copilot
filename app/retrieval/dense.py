from dataclasses import dataclass
from uuid import UUID
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.authz import readable_by
from app.core.models import Chunk, Document, Section
from ingest.embeddings import embed_text

@dataclass
class RetrievedChunk:
    chunk_id: UUID
    document_id: UUID
    document_title: str
    section_path: str | None
    content: str
    chunk_index: int
    score: float


def retrieve_chunks(
    db: Session,
    query: str,
    top_k: int=5,
    min_score: float = 0.45,
    *,
    roles: Sequence[str]
) -> list[RetrievedChunk]:
    
    if not roles:
        return []
    
    query_embedding = embed_text(query)
    
    distance = Chunk.embedding.cosine_distance(query_embedding)
    
    rows = db.execute(
        select(
            Chunk,
            Document.title,
            Section.section_path,
            distance.label("distance"),
        )
        .join(Document, Document.id == Chunk.document_id)
        .outerjoin(Section, Section.id == Chunk.section_id)
        .where(Chunk.embedding.is_not(None))
        .where(readable_by(roles))
        .order_by(distance)
        .limit(top_k)
    ).all()
    
    result = []
    
    for chunk, document_title, section_path, distance in rows:
        score = 1.0 - float(distance)
        
        if score < min_score:
            continue

        result.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=document_title,
                section_path=section_path,
                content=chunk.content,
                chunk_index=chunk.chunk_index,
                score=1.0 - float(distance)
            )
        )
    
    return result