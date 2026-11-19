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
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.conversations import (
    ConversationNotFound,
    delete_message,
    TITLE_MAX_LENTH,
    append_message,
    get_owned_conversation
)
from app.followup import answer_is_visible, plan_follow_up, readable_chunk_ids
from app.llm import complete
from app.models import Message
from app.observability import record
from app.retrieval import RetrievedChunk
from app.search import search_policies

logger = logging.getLogger("policy_copilot.conversations")
from app.security import Principal


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


def visible_messages(
    db: Session,
    messages: Sequence[Message],
    roles: Sequence[str],
) -> list[dict]:
    """Messages for display, with answers whose sources are no longer
    readable withheld. standalone_question is never exposed."""
    referenced = {
        chunk_id
        for message in messages
        if message.sender == "assistant"
        for chunk_id in (message.source_chunk_ids or [])
    }
    readable = readable_chunk_ids(db, referenced, roles)

    result = []
    for message in messages:
        withheld = (
            message.sender == "assistant"
            and not answer_is_visible(message, readable)
        )
        result.append({
            "id": str(message.id),
            "position": message.position,
            "sender": message.sender,
            "content": WITHHELD_TEXT if withheld else message.content,
            "withheld": withheld,
            "created_at": message.created_at.isoformat(),
        })
    return result
