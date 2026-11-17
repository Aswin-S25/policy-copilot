from dataclasses import dataclass
from uuid import UUID
from collections.abc import Sequence

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.authz import readable_by
from app.models import Chunk, Document, Section


@dataclass
class LexicalResult:
    chunk_id: UUID
    document_id: UUID
    document_title: str
    section_path: str | None
    content: str
    chunk_index: int
    score: float


def retrieve_lexical(
    db: Session,
    query: str,
    top_k:int = 5,
    *,
    roles: Sequence[str],
) -> list[LexicalResult]:
    
    if not roles:
        return []

    search_query = func.websearch_to_tsquery(
        'english',
        query
    )
    
    rank = func.ts_rank_cd(
        Chunk.search_vector,
        search_query
    )
    
    
    rows = db.execute(
        select(
            Chunk,
            Document.title,
            Section.section_path,
            rank.label("rank"),
        )
        .join(
            Document,
            Document.id == Chunk.document_id,
        )
        .outerjoin(
            Section,
            Section.id == Chunk.section_id,
        )
        .where(
            Chunk.search_vector.op("@@")(
                search_query
            ),
            readable_by(roles),
        )
        .order_by(
            rank.desc()
        )
        .limit(top_k)
    ).all()
    
    return [
        LexicalResult(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_title=document_title,
            section_path=section_path,
            content=chunk.content,
            chunk_index=chunk.chunk_index,
            score=float(rank_value),
        )
        for (
            chunk,
            document_title,
            section_path,
            rank_value,
        ) in rows
    ]