import uuid

import pytest
from sqlalchemy import select

from app.conversations.repository import (
    ConversationNotFound,
    append_message,
    create_conversation,
)
from app.conversations.followup import (
    HistoryTurn,
    authorize_history,
    clean_rewrite,
    plan_follow_up,
    rewrite_question,
)
from app.rag.llm import LLMUnavailable
from app.core.models import Chunk
from ingest.models import ParsedDocument, ParsedSection
from ingest.upsert import ingest_document

PUBLIC_ANSWER = "Employees get 24 days of annual leave [Source 1]."
RESTRICTED_ANSWER = "SEV1 pages must be acknowledged within 15 minutes [Source 1]."


def ingest(db, source, text, roles):
    document = ingest_document(
        db,
        ParsedDocument(
            title=source, source=source, document_type="markdown",
            content=text,
            sections=[ParsedSection(title="S", level=2, content=text, position=0)],
        ),
        allowed_roles=roles,
    )
    return db.scalar(select(Chunk.id).where(Chunk.document_id == document.id))


@pytest.fixture
def conversation(db):
    public_chunk = ingest(db, "leave.md", "24 days of annual leave.", ["employee", "security"])
    restricted_chunk = ingest(db, "ir.md", "SEV1 acknowledge in 15 minutes.", ["security"])

    conv = create_conversation(db, "alice")
    turns = [
        ("user", "How much annual leave?", None),
        ("assistant", PUBLIC_ANSWER, [public_chunk]),
        ("user", "How fast must SEV1 be acknowledged?", None),
        ("assistant", RESTRICTED_ANSWER, [restricted_chunk]),
        ("assistant", "I could not find relevant information.", []),   # refusal
        ("assistant", "Legacy answer with unknown sources.", None),
        ("assistant", "Answer from a deleted chunk.", [uuid.uuid4()]),
    ]
    for sender, content, sources in turns:
        append_message(db, conv.id, "alice", sender=sender,
                       content=content, source_chunk_ids=sources)
    return conv


def history_for(db, conv, roles):
    return authorize_history(db, conv.messages, roles)


# ---- history authorization ----------------------------------------------------

def test_employee_history_excludes_restricted_answer(db, conversation):
    db.refresh(conversation)
    turns, dropped = history_for(db, conversation, ["employee"])
    contents = [t.content for t in turns]

    assert PUBLIC_ANSWER in contents
    assert RESTRICTED_ANSWER not in contents
    assert "I could not find relevant information." in contents  # refusal kept
    assert dropped == 3  # restricted, unknown sources, deleted chunk


def test_security_history_includes_restricted_answer(db, conversation):
    db.refresh(conversation)
    turns, dropped = history_for(db, conversation, ["security"])
    contents = [t.content for t in turns]

    assert RESTRICTED_ANSWER in contents
    assert dropped == 2  # unknown sources and deleted chunk still fail closed


def test_user_questions_are_always_replayed(db, conversation):
    db.refresh(conversation)
    turns, _ = history_for(db, conversation, [])

    assert [t.content for t in turns if t.sender == "user"] == [
        "How much annual leave?",
        "How fast must SEV1 be acknowledged?",
    ]


def test_restricted_answer_never_reaches_rewrite_prompt(db, conversation):
    prompts = []

    def capture(**kwargs):
        prompts.append(kwargs["user_prompt"])
        return "What is the SEV2 acknowledgement time?"

    plan = plan_follow_up(db, conversation.id, "alice", ["employee"],
                          "And SEV2?", complete_fn=capture)

    assert RESTRICTED_ANSWER not in prompts[0]
    assert "15 minutes" not in prompts[0]
    assert plan.standalone_question == "What is the SEV2 acknowledgement time?"


def test_plan_requires_ownership(db, conversation):
    with pytest.raises(ConversationNotFound):
        plan_follow_up(db, conversation.id, "mallory", ["security"],
                       "And SEV2?", complete_fn=lambda **_: "x")


# ---- rewriting ------------------------------------------------------------------

def test_no_history_returns_question_without_llm_call():
    def must_not_run(**_):
        raise AssertionError("LLM called without history")

    assert rewrite_question([], "How much leave?", complete_fn=must_not_run) \
        == "How much leave?"


def test_llm_failure_falls_back_to_raw_question():
    def broken(**_):
        raise LLMUnavailable("timeout")

    turns = [HistoryTurn("user", "How much annual leave?")]

    assert rewrite_question(turns, "And sick leave?", complete_fn=broken) \
        == "And sick leave?"


@pytest.mark.parametrize("raw,expected", [
    ("How many sick days do employees get?", "How many sick days do employees get?"),
    ('"How many sick days do employees get?"', "How many sick days do employees get?"),
    ("Standalone question: How many sick days?", "How many sick days?"),
    ("Question: How many sick days?", "How many sick days?"),
    ("Questions about leave go to HR?", "Questions about leave go to HR?"),
    ("<think>reasoning</think>\nHow many sick days?", "How many sick days?"),
    ("How many sick days?\nThis rewrite resolves 'it'.", "How many sick days?"),
    ("", "FALLBACK"),
    ("x" * 600, "FALLBACK"),
])
def test_clean_rewrite(raw, expected):
    assert clean_rewrite(raw, fallback="FALLBACK") == expected
