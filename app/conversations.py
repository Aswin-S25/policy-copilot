import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import Conversation, Message

TITLE_MAX_LENTH = 200
SENDERS = ("user", "assistant")


class ConversationNotFound(Exception):
    """Missing, or not owned by the caller. Deliberately the same error."""


def create_conversation(
    db: Session,
    owner_sub: str,
    title: str | None = None,
) -> Conversation:
    conversation = Conversation(
        owner_sub = owner_sub,
        title = (title or "").strip()[:TITLE_MAX_LENTH] or None
    )
    db.add(conversation)
    db.flush()
    return conversation


def get_owned_conversation(
    db: Session,
    conversation_id: uuid.UUID,
    owner_sub: str,
    *,
    for_update: bool = False,
) -> Conversation:
    statement = select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.owner_sub == owner_sub
    )
    
    if for_update:
        statement = statement.with_for_update()
    
    
    conversation = db.scalar(statement)
    if conversation is None:
        raise ConversationNotFound(str(conversation_id))
    return conversation


def list_conversations(
    db: Session,
    owner_sub: str,
    limit: int = 50,
) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(Conversation.owner_sub == owner_sub)
            .order_by(Conversation.updated_at.desc())
            .limit(limit)
        )
    )


def append_message(
    db: Session,
    conversation_id: uuid.UUID,
    owner_sub: str,
    *,
    sender: str,
    content: str,
    standalone_question: str | None = None,
    source_chunk_ids: Sequence[uuid.UUID] | None = None,
) -> Message:
    if sender not in SENDERS:
        raise ValueError(f"Sender must be one of {SENDERS}, got {sender!r}")
    
    # Lock the conversation row so concurrent turns on the same
    # conversation get sequential positions instead of a unique violation.
    
    conversation = get_owned_conversation(
        db, conversation_id, owner_sub, for_update=True
    )
    
    last_position = db.scalar(
        select(func.max(Message.position)).where(
            Message.conversation_id == conversation.id
        )
    )
    
    message = Message(
        conversation_id=conversation_id,
        position=0 if last_position is None else last_position + 1,
        sender=sender,
        content=content,
        standalone_question=standalone_question,
        source_chunk_ids=(
            list(source_chunk_ids) if source_chunk_ids is not None else None
        ),
    )
    
    db.add(message)
    conversation.updated_at = func.now()
    db.flush()
    return message


def get_messages(
    db: Session,
    conversation_id: uuid.UUID,
    owner_sub: str,
    *,
    last_n: int | None = None,
) -> list[Message]:
    
    conversation = get_owned_conversation(db, conversation_id, owner_sub)
    
    statement = (
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.position.desc())
    )
    if last_n is not None:
        statement = statement.limit(last_n)

    return list(reversed(db.scalars(statement).all()))


def delete_conversation(
    db: Session,
    conversation_id: uuid.UUID,
    owner_sub: str,
) -> None:
    conversation = get_owned_conversation(db, conversation_id, owner_sub)
    db.delete(conversation)  # messages go via ON DELETE CASCADE
    db.flush()

def delete_message(
    db: Session,
    conversation_id: uuid.UUID,
    owner_sub: str,
    message_id: uuid.UUID,
) -> None:
    """Remove one message; used to discard a turn whose answer failed."""
    conversation = get_owned_conversation(
        db, conversation_id, owner_sub, for_update=True
    )
    db.execute(
        delete(Message).where(
            Message.id == message_id,
            Message.conversation_id == conversation.id,
        )
    )
    db.flush()
