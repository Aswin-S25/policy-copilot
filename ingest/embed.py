from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chunk, Document, Section
from ingest.chunk import build_contextual_text
from ingest.embeddings import embed_texts, EMBEDDING_MODEL

def embed_document_chunks(
    db: Session,
    document_id,
) -> int:
    rows = db.execute(
        select(
            Chunk,
            Document.title,
            Section.section_path,
        )
        .join(Document, Document.id == Chunk.document_id)
        .outerjoin(Section, Section.id == Chunk.section_id)
        .where(
            Chunk.document_id == document_id,
            Chunk.embedding.is_(None),
        )
        .order_by(Chunk.chunk_index)
    ).all()
    
    
    if not rows:
        return 0
    
    texts = [
        build_contextual_text(
            document_title=document_title,
            section_path=section_path or "Unknown section",
            content=chunk.content,
        )
        for chunk, document_title, section_path in rows
    ]
    
    embeddings = embed_texts(texts)
    
    for (chunk, _, _), embedding in zip(rows, embeddings):
        chunk.embedding = embedding
        chunk.embedding_model = EMBEDDING_MODEL
        
    db.commit()
    
    return len(rows)
    