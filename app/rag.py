from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.citations import exact_citations, remove_invalid_citations
from app.context import BuildContext, build_context
from app.llm import generate_answer, stream_answer
from app.prompt import SYSTEM_PROMPT, build_user_prompt
from app.search import search_policies

NO_CONTEXT_REFUSAL = (
    "I could not find relevant information in the available policies."
)
CONTEXT_TOO_SMALL_REFUSAL = (
    "I could not find enough relevant information in the available policies."
)
UNSUPPORTED_REFUSAL = (
    "I could not produce a sufficiently supported answer "
    "from the available policies."
)


@dataclass
class Citation:
    source_number: int
    document_title: str
    section_path: str | None
    chunk_id: str
    score: float

    def to_dict(self) -> dict:
        return {
            "source": self.source_number,
            "document": self.document_title,
            "section": self.section_path,
            "chunk_id": self.chunk_id,
            "score": self.score,
        }


@dataclass
class RagResponse:
    answer: str
    citations: list[Citation]
    retrieved_count: int
    context_tokens: int
    context: str = ""


# ---- pipeline steps shared by the blocking and streaming paths -------------

def context_or_refusal(
    retrieved: list,
    max_context_tokens: int,
) -> tuple[BuildContext | None, str | None]:
    """Return (context, None) or (None, refusal) when there is nothing
    to ground an answer on."""
    if not retrieved:
        return None, NO_CONTEXT_REFUSAL

    context = build_context(
        retrieved_chunks=retrieved,
        max_tokens=max_context_tokens,
    )

    if not context.chunks:
        return None, CONTEXT_TOO_SMALL_REFUSAL

    return context, None


def finalize_answer(raw_answer: str, context: BuildContext) -> str:
    """Drop citations to sources that were not provided; an answer with
    no valid citation is not grounded and is replaced by a refusal."""
    available_sources = {item.source_number for item in context.chunks}

    answer = remove_invalid_citations(raw_answer, available_sources)

    if not exact_citations(answer):
        return UNSUPPORTED_REFUSAL

    return answer


def citations_for(context: BuildContext) -> list[Citation]:
    return [
        Citation(
            source_number=item.source_number,
            document_title=item.chunk.document_title,
            section_path=item.chunk.section_path,
            chunk_id=str(item.chunk.chunk_id),
            score=item.chunk.score,
        )
        for item in context.chunks
    ]


# ---- entry points ------------------------------------------------------------

def answer_question(
    db: Session,
    question: str,
    top_k: int = 5,
    max_context_tokens: int = 3000,
    *,
    roles: Sequence[str],
) -> RagResponse:

    retrieved = search_policies(
        db=db,
        query=question,
        top_k=top_k,
        roles=roles,
    )

    return answer_from_chunks(
        question=question,
        retrieved=retrieved,
        max_context_tokens=max_context_tokens,
    )


def answer_from_chunks(
    question: str,
    retrieved: list,
    max_context_tokens: int = 3000,
) -> RagResponse:
    """Build context, call the LLM and validate citations for chunks
    that were already retrieved (by any retrieval strategy)."""

    context, refusal = context_or_refusal(retrieved, max_context_tokens)

    if refusal is not None:
        return RagResponse(
            answer=refusal,
            citations=[],
            retrieved_count=len(retrieved),
            context_tokens=0,
            context="",
        )

    raw_answer = generate_answer(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(question=question, context=context.text),
    )

    return RagResponse(
        answer=finalize_answer(raw_answer, context),
        citations=citations_for(context),
        retrieved_count=len(retrieved),
        context_tokens=context.estimated_tokens,
        context=context.text,
    )


def stream_answer_events(
    question: str,
    retrieved: list,
    max_context_tokens: int = 3000,
) -> Iterator[tuple[str, dict]]:
    """Streaming counterpart of answer_from_chunks, as (event, data) pairs.

    "token" events carry raw model output as it is generated. The final
    "answer" event carries the validated answer (invalid citations removed,
    uncited answers replaced by a refusal) and is authoritative: clients
    must render it in place of the concatenated tokens.
    """
    context, refusal = context_or_refusal(retrieved, max_context_tokens)

    if refusal is not None:
        yield "answer", {"text": refusal}
        return

    yield "status", {"stage": "generation"}

    parts = []
    for token in stream_answer(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(question=question, context=context.text),
    ):
        parts.append(token)
        yield "token", {"text": token}

    yield "answer", {"text": finalize_answer("".join(parts), context)}
    yield "citations", {
        "sources": [citation.to_dict() for citation in citations_for(context)]
    }
