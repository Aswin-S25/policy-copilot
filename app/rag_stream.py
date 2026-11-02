from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.citations import (
    exact_citations,
    remove_invalid_citations,
)
from app.context import build_context
from app.llm import stream_answer
from app.prompt import SYSTEM_PROMPT, build_user_prompt
from app.retrieval import retrieve_chunks


def stream_question(
    db: Session,
    question: str,
    top_k: int=5,
    min_score: float = 0.45,
    max_context_tokens: int = 3000,
) -> Iterator[str]:
    
    retrieved = retrieve_chunks(
        db=db,
        query=question,
        top_k=top_k,
        min_score=min_score,
    )
    
    
    if not retrieved:
        yield (
            "I could not find relevant informatoin "
            "in the available policies"
        )
        return
    
    context = build_context(
        retrieved_chunks=retrieved,
        max_tokens=max_context_tokens,
    )
    
    
    if not context.chunks:
        yield (
            "I could not find enough relevant information "
            "in the available policies."
        )
        return

    prompt = build_user_prompt(
        question=question,
        context=context.text
    )
    
    answer_parts = []
    
    for token in stream_answer(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=prompt,
    ):
        answer_parts.append(token)
    
    answer = "".join(answer_parts)
    
    
    available_sources = {
        item.source_number
        for item in context.chunks
    }
    
    answer = remove_invalid_citations(
        answer,
        available_sources
    )
    
    if not exact_citations(answer):
        answer = (
            "I could not produce a sufficiently supported "
            "answer from the available policies."
        )
    
    yield answer