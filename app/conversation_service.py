"""Conversation turns: orchestration shared by the blocking and streaming
endpoints.

A turn runs in two short database sessions with the LLM call between them,
so no connection or row lock is held while the model generates:

  prepare_turn   ownership check, authorized history, rewrite, store the
                 user message, retrieve under CURRENT roles      -> commit
  (LLM)          answer_from_chunks / stream_answer_events          (no DB)
  record_answer  store the answer with its context chunk ids     -> commit
"""

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.conversations import (
    TITLE_MAX_LENTH,
    append_message,
    get_owned_conversation
)
from app.followup import answer_is_visible, plan_follow_up, readable_chunk_ids
from app.llm import complete
from app.models import Message
from app.retrieval import RetrievedChunk
from app.search import search_policies
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
    
    conversation = get_owned_conversation(db, conversation_id, principal.subject)
    if not conversation.title:
        conversation.title = question.strip()[:TITLE_MAX_LENTH]
    
    
    append_message(
        db,
        conversation_id,
        principal.subject,
        sender="user",
        content=question,
        standalone_question=plan.standalone_question,
    )

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
