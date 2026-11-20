"""Conversation turns: orchestration shared by the blocking and streaming
endpoints.

A turn runs in two short database sessions with the LLM call between them,
so no connection or row lock is held while the model generates:

  prepare_turn   ownership check, authorized history, rewrite, store the
                 user message, retrieve under CURRENT roles      -> commit
  (LLM)          answer_from_chunks / stream_answer_events          (no DB)
  record_answer  store the answer with its context chunk ids     -> commit
"""

import logging
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.conversations.repository import (
    ConversationNotFound,
    delete_message,
    TITLE_MAX_LENTH,
    append_message,
    get_owned_conversation
)
from app.conversations.followup import answer_is_visible, plan_follow_up, readable_chunk_ids
from app.rag.llm import complete
from app.core.display import display_titles
from app.core.models import Chunk, Message, Section
from app.core.observability import record
from app.retrieval.dense import RetrievedChunk
from app.retrieval.search import search_policies

logger = logging.getLogger("policy_copilot.conversations")
from app.core.security import Principal


WITHHELD_TEXT = (
    "This answer is hidden because you no longer have access to the "
    "document it was based on"
)


@dataclass
class PreparedTurn:
    standalone_question: str
    retrieved: list[RetrievedChunk]
    history_turns: int
    dropped_answers: int
    user_message_id: uuid.UUID
    

def prepare_turn(
    db: Session,
    conversation_id: uuid.UUID,
    principal: Principal,
    question: str,
    *,
    top_k: int = 5,
    complete_fn: Callable[..., str] | None = None,
) -> PreparedTurn:
    roles = principal.document_roles
    
    plan = plan_follow_up(
        db,
        conversation_id,
        principal.subject,
        roles,
        question,
        complete_fn=complete_fn or complete,
    )
    record(history_turns=plan.history_turns, dropped_answers=plan.dropped_answers)

    conversation = get_owned_conversation(db, conversation_id, principal.subject)
    if not conversation.title:
        conversation.title = question.strip()[:TITLE_MAX_LENTH]
    
    
    user_message = append_message(
        db,
        conversation_id,
        principal.subject,
        sender="user",
        content=question,
        standalone_question=plan.standalone_question,
    )
    user_message_id = user_message.id

    retrieved = search_policies(
        db=db,
        query=plan.standalone_question,
        top_k=top_k,
        roles=roles,
    )

    db.commit()
    
    return PreparedTurn(
        standalone_question=plan.standalone_question,
        retrieved=retrieved,
        history_turns=plan.history_turns,
        dropped_answers=plan.dropped_answers,
        user_message_id=user_message_id,
    )


def record_answer(
    db: Session,
    conversation_id: uuid.UUID,
    owner_sub: str,
    answer: str,
    source_chunk_ids: Sequence[uuid.UUID],
) -> uuid.UUID:
    message = append_message(
        db,
        conversation_id,
        owner_sub,
        sender="assistant",
        content=answer,
        source_chunk_ids=list(source_chunk_ids),
    )
    message_id = message.id  # read before commit expires the instance
    db.commit()
    return message_id



def discard_turn(
    db: Session,
    conversation_id: uuid.UUID,
    owner_sub: str,
    user_message_id: uuid.UUID,
) -> None:
    """Undo a turn whose answer could not be produced, so history never
    holds a question without an answer and the client can simply retry."""
    try:
        delete_message(db, conversation_id, owner_sub, user_message_id)
        db.commit()
        logger.info("turn_discarded")
    except ConversationNotFound:
        # Conversation deleted meanwhile: nothing left to clean up.
        logger.info("turn_discard_skipped", extra={"reason": "conversation_gone"})


def source_details(
    db: Session,
    chunk_ids: Iterable[uuid.UUID],
) -> dict[uuid.UUID, tuple[str, str | None]]:
    """Document display name and section path for each chunk id that still
    exists. Callers pass only chunk ids the user is already authorized to read."""
    chunk_ids = list(chunk_ids)
    if not chunk_ids:
        return {}
    rows = db.execute(
        select(Chunk.id, Chunk.document_id, Section.section_path)
        .outerjoin(Section, Section.id == Chunk.section_id)
        .where(Chunk.id.in_(chunk_ids))
    ).all()
    names = display_titles(db, (document_id for _, document_id, _ in rows))
    return {
        chunk_id: (names[document_id], section_path)
        for chunk_id, document_id, section_path in rows
        if document_id in names
    }


def message_citations(
    message: Message,
    details: dict[uuid.UUID, tuple[str, str | None]],
) -> list[dict]:
    """Rebuild an answer's citations from its stored context chunk ids.

    source_chunk_ids is stored in context order, and build_context numbers
    sources 1..n in that order, so position i is "[Source i+1]" in the
    answer text. Same keys as Citation.to_dict(); the retrieval score is not
    stored, so it is null for history.
    """
    citations = []
    for number, chunk_id in enumerate(message.source_chunk_ids or [], start=1):
        if chunk_id not in details:
            continue
        title, section_path = details[chunk_id]
        citations.append({
            "source": number,
            "document": title,
            "section": section_path,
            "chunk_id": str(chunk_id),
            "score": None,
        })
    return citations


def visible_messages(
    db: Session,
    messages: Sequence[Message],
    roles: Sequence[str],
) -> list[dict]:
    """Messages for display, with answers whose sources are no longer
    readable withheld. standalone_question is never exposed.

    Visible answers carry their citations. A withheld answer carries none:
    the titles of documents the user can no longer read are not revealed."""
    referenced = {
        chunk_id
        for message in messages
        if message.sender == "assistant"
        for chunk_id in (message.source_chunk_ids or [])
    }
    readable = readable_chunk_ids(db, referenced, roles)
    details = source_details(db, readable)

    result = []
    for message in messages:
        withheld = (
            message.sender == "assistant"
            and not answer_is_visible(message, readable)
        )
        shows_sources = message.sender == "assistant" and not withheld
        result.append({
            "id": str(message.id),
            "position": message.position,
            "sender": message.sender,
            "content": WITHHELD_TEXT if withheld else message.content,
            "withheld": withheld,
            "citations": message_citations(message, details) if shows_sources else [],
            "created_at": message.created_at.isoformat(),
        })
    return result
