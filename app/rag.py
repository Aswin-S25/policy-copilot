from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.context import build_context
from app.llm import generate_answer
from app.prompt import SYSTEM_PROMPT, build_user_prompt
from app.retrieval import retrieve_chunks
from app.citations import (
    exact_citations,
    remove_invalid_citations,
    validate_citations
)

@dataclass
class Citation:
    source_number: int
    document_title: str
    section_path: str | None
    chunk_id: str
    score: float

@dataclass
class RagResponse:
    answer: str
    citations: list[Citation]
    retrieved_count: int
    context_tokens: int
    context: str = ""
     

def answer_question(
    db: Session,
    question: str,
    top_k: int = 5,
    min_score: float = 0.45,
    max_context_tokens: int = 3000
) -> RagResponse:
    
    retrieved = retrieve_chunks(
        db=db,
        query=question,
        top_k=top_k,
        min_score=min_score,
    )
    
    if not retrieved:
        return RagResponse(
            answer=(
                "I could not find relevant information "
                "in the available policies."
            ),
            citations=[],
            retrieved_count=0,
            context_tokens=0,
            context=""
        )
    
    context = build_context(
        retrieved_chunks=retrieved,
        max_tokens=max_context_tokens
    )
    
    if not context.chunks:
        return RagResponse(
            answer=(
                "I could not find enough relevant information "
                "in the available policies"
            ),
            citations=[],
            retrieved_count=len(retrieved),
            context_tokens=0,
            context="",
        )
    
    
    user_prompt = build_user_prompt(
        question=question,
        context=context.text,
    )
    
    answer = generate_answer(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt
    )
    
    available_sources = {
        item.source_number
        for item in context.chunks
    }
    
    answer = remove_invalid_citations(
        answer,
        available_sources
    )
    
    cited_sources = exact_citations(answer)
    
    if not cited_sources:
        answer = (
            "I could not produce a sufficiently supported answer "
            "from the available policies."
        )
    
    
    citations = [
        Citation(
            source_number=item.source_number,
            document_title=item.chunk.document_title,
            section_path=item.chunk.section_path,
            chunk_id=str(item.chunk.chunk_id),
            score=item.chunk.score,
        )
        for item in context.chunks
    ]
    
    return RagResponse(
        answer=answer,
        citations=citations,
        retrieved_count=len(retrieved),
        context_tokens=context.estimated_tokens,
        context=context.text
    )