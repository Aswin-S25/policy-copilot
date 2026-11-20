import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.conversations.repository import (
    ConversationNotFound,
    append_message,
    create_conversation,
    delete_conversation,
    get_messages,
    get_owned_conversation,
    list_conversations,
)
from app.core.models import Message

ALICE = "alice"
BOB = "bob"


def message_count(db):
    return db.scalar(select(func.count()).select_from(Message))


# ---- ownership ------------------------------------------------------------

def test_owner_can_read_own_conversation(db):
    conversation = create_conversation(db, ALICE, "Leave question")

    found = get_owned_conversation(db, conversation.id, ALICE)

    assert found.id == conversation.id


def test_other_user_gets_same_error_as_missing(db):
    conversation = create_conversation(db, ALICE)

    with pytest.raises(ConversationNotFound):
        get_owned_conversation(db, conversation.id, BOB)

    with pytest.raises(ConversationNotFound):
        get_owned_conversation(db, uuid.uuid4(), ALICE)


def test_cannot_append_to_someone_elses_conversation(db):
    conversation = create_conversation(db, ALICE)

    with pytest.raises(ConversationNotFound):
        append_message(db, conversation.id, BOB, sender="user", content="hi")

    assert message_count(db) == 0


def test_cannot_read_someone_elses_messages(db):
    conversation = create_conversation(db, ALICE)
    append_message(db, conversation.id, ALICE, sender="user", content="secret")

    with pytest.raises(ConversationNotFound):
        get_messages(db, conversation.id, BOB)


def test_list_returns_only_own_conversations_most_recent_first(db):
    first = create_conversation(db, ALICE, "first")
    db.commit()
    second = create_conversation(db, ALICE, "second")
    create_conversation(db, BOB, "bob's")
    db.commit()

    # New transaction, later now(): appending makes "first" most recent.
    append_message(db, first.id, ALICE, sender="user", content="again")
    db.commit()

    titles = [c.title for c in list_conversations(db, ALICE)]

    assert titles == ["first", "second"]


def test_non_owner_cannot_delete(db):
    conversation = create_conversation(db, ALICE)

    with pytest.raises(ConversationNotFound):
        delete_conversation(db, conversation.id, BOB)

    assert get_owned_conversation(db, conversation.id, ALICE)


# ---- messages ---------------------------------------------------------------

def test_messages_get_sequential_positions_in_order(db):
    conversation = create_conversation(db, ALICE)
    chunk_ids = [uuid.uuid4(), uuid.uuid4()]

    append_message(db, conversation.id, ALICE, sender="user",
                   content="How much leave?",
                   standalone_question="How many days of annual leave?")
    append_message(db, conversation.id, ALICE, sender="assistant",
                   content="24 days [Source 1].", source_chunk_ids=chunk_ids)
    append_message(db, conversation.id, ALICE, sender="user",
                   content="And sick leave?")

    messages = get_messages(db, conversation.id, ALICE)

    assert [m.position for m in messages] == [0, 1, 2]
    assert [m.sender for m in messages] == ["user", "assistant", "user"]
    assert messages[0].standalone_question == "How many days of annual leave?"
    assert messages[1].source_chunk_ids == chunk_ids


def test_last_n_returns_most_recent_in_chronological_order(db):
    conversation = create_conversation(db, ALICE)
    for i in range(5):
        append_message(db, conversation.id, ALICE, sender="user", content=f"m{i}")

    messages = get_messages(db, conversation.id, ALICE, last_n=2)

    assert [m.content for m in messages] == ["m3", "m4"]


def test_delete_cascades_to_messages(db):
    conversation = create_conversation(db, ALICE)
    append_message(db, conversation.id, ALICE, sender="user", content="hi")

    delete_conversation(db, conversation.id, ALICE)

    assert message_count(db) == 0


def test_invalid_sender_rejected_in_code(db):
    conversation = create_conversation(db, ALICE)

    with pytest.raises(ValueError):
        append_message(db, conversation.id, ALICE, sender="system", content="x")


def test_invalid_sender_rejected_by_database(db):
    # Defence in depth: the CHECK constraint holds even if code bypasses
    # append_message.
    conversation = create_conversation(db, ALICE)
    db.add(Message(conversation_id=conversation.id, position=0,
                   sender="system", content="x"))

    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_title_is_trimmed_and_truncated(db):
    conversation = create_conversation(db, ALICE, "  " + "x" * 500)

    assert conversation.title == "x" * 200
