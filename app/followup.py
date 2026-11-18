import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz import readable_by
from app.conversations import get_messages
from app.llm import complete
from app.models import Chunk, Message
from app.prompt import REWRITE_SYSTEM_PROMPT, build_rewrite_prompt


MAX_HISTORY_MESSAGES = 6
MAX_TURN_CHARS = 800
MAX_REWRITE_CHARS = 500

REWRITE_PREFIXES = ("standalone question:", "question:", "rewritten question:")


@dataclass
class HistoryTurn:
    sender: str
    content: str


@dataclass
class FollowUpPlan:
    standalone_question: str
    history_turns: int
    dropped_answers: int


def readable_chunk_ids(
    db: Session,
    chunk_ids: Iterable[uuid.UUID],
    roles: Sequence[str],
) -> set[uuid.UUID]:
    chunk_ids = list(chunk_ids)
    if not chunk_ids or not roles:
        return set()
    
    return set(
        db.scalars(
            select(Chunk.id).where(
                Chunk.id.in_(chunk_ids),
                readable_by(roles),
            )
        )
    )


def authorize_history(
    db: Session,
    messages: Sequence[Message],
    roles: Sequence[str],
) -> tuple[list[HistoryTurn], int]:
    """Return (turns safe to replay, number of answers dropped).

    User turns are the user's own words and are always kept; only their
    raw text is replayed, never the stored standalone_question, which may
    have been derived from history authorized under older roles.

    An assistant turn is kept only if every chunk it was generated from
    still exists and is readable under the current roles. Unknown sources
    (None) or deleted chunks fail closed.
    """
    
    referenced = (
        chunk_id
        for message in messages
        if message.sender == "assistant"
        for chunk_id in (message.source_chunk_ids or [])
    )
    
    readable = readable_chunk_ids(db, referenced, roles)
    
    turns, dropped = [], 0
    for message in messages:
        if message.sender == "assistant":
            sources = message.source_chunk_ids
            if sources is None or not set(sources) <= readable:
                dropped += 1
                continue
        turns.append(HistoryTurn(sender=message.sender, content=message.content))

    return turns, dropped


def format_history(turns: Sequence[HistoryTurn]) -> str:
    lines = []
    for turn in turns:
        text = turn.content
        if len(text) > MAX_TURN_CHARS:
            text = text[:MAX_TURN_CHARS] + " ..."
        speaker = "User" if turn.sender == "user" else "Assistant"
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def clean_rewrite(raw: str, fallback: str) -> str:
    text = raw.strip()
    if "</think>" in text:  # never let leaked reasoning become the query
        text = text.split("</think>", 1)[1].strip()

    line = next((l.strip() for l in text.splitlines() if l.strip()), "")
    for prefix in REWRITE_PREFIXES:
        if line.lower().startswith(prefix):
            line = line[len(prefix):].strip()
    line = line.strip("\"'").strip()

    if not line or len(line) > MAX_REWRITE_CHARS:
        return fallback
    return line


def rewrite_question(
    turns: Sequence[HistoryTurn],
    question: str,
    *,
    complete_fn: Callable[..., str] = complete,
) -> str:
    if not turns:
        return question

    try:
        raw = complete_fn(
            system_prompt=REWRITE_SYSTEM_PROMPT,
            user_prompt=build_rewrite_prompt(format_history(turns), question),
        )
    except Exception:
        # Degrade to the raw follow-up: worse retrieval, but the turn works.
        return question

    return clean_rewrite(raw, fallback=question)


# ---- entry point -----------------------------------------------------------------

def plan_follow_up(
    db: Session,
    conversation_id: uuid.UUID,
    owner_sub: str,
    roles: Sequence[str],
    question: str,
    *,
    complete_fn: Callable[..., str] = complete,
) -> FollowUpPlan:
    # Raises ConversationNotFound if the caller does not own the conversation.
    messages = get_messages(
        db, conversation_id, owner_sub, last_n=MAX_HISTORY_MESSAGES
    )
    turns, dropped = authorize_history(db, messages, roles)

    return FollowUpPlan(
        standalone_question=rewrite_question(
            turns, question, complete_fn=complete_fn
        ),
        history_turns=len(turns),
        dropped_answers=dropped,
    )