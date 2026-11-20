import uuid

from fastapi import APIRouter, Depends, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.conversations.service import (
    discard_turn,
    prepare_turn,
    record_answer,
    visible_messages
)
from app.rag.llm import LLMUnavailable
from app.conversations.repository import (
    ConversationNotFound,
    create_conversation,
    delete_conversation,
    get_messages,
    get_owned_conversation,
    list_conversations,
)
from app.core.db import SessionLocal
from app.core.display import relabel_citations
from app.rag.pipeline import answer_from_chunks, stream_answer_events
from app.core.rate_limit import llm_rate_limited
from app.core.security import Principal, get_current_principal
from app.api.sse import sse_event

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=200)


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    max_context_tokens: int = Field(default=3000, ge=500, le=8000)


def conversation_summary(conversation) -> dict:
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "updated_at": conversation.updated_at.isoformat(),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create(
    request: ConversationCreate | None = None,
    principal: Principal = Depends(get_current_principal),
):
    with SessionLocal() as db:
        conversation = create_conversation(
            db, principal.subject, request.title if request else None
        )
        db.commit()
        return conversation_summary(conversation)


@router.get("")
def list_own(principal: Principal = Depends(get_current_principal)):
    with SessionLocal() as db:
        return {
            "conversations": [
                conversation_summary(c)
                for c in list_conversations(db, principal.subject)
            ]
        }


@router.get("/{conversation_id}")
def read(
    conversation_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
):
    with SessionLocal() as db:
        conversation = get_owned_conversation(db, conversation_id, principal.subject)
        messages = get_messages(db, conversation_id, principal.subject)
        return {
            **conversation_summary(conversation),
            "messages": visible_messages(db, messages, principal.document_roles),
        }


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    conversation_id: uuid.UUID,
    principal: Principal = Depends(get_current_principal),
):
    with SessionLocal() as db:
        delete_conversation(db, conversation_id, principal.subject)
        db.commit()


@router.post("/{conversation_id}/messages")
def post_message(
    conversation_id: uuid.UUID,
    request: MessageRequest,
    principal: Principal = Depends(llm_rate_limited),
):
    with SessionLocal() as db:
        turn = prepare_turn(
            db, conversation_id, principal, request.question, top_k=request.top_k
        )

    try:
        response = answer_from_chunks(
            question=turn.standalone_question,
            retrieved=turn.retrieved,
            max_context_tokens=request.max_context_tokens,
        )
    except LLMUnavailable:
        with SessionLocal() as db:
            discard_turn(db, conversation_id, principal.subject, turn.user_message_id)
        raise  # mapped to 503 by the handler in app/main.py


    with SessionLocal() as db:
        message_id = record_answer(
            db,
            conversation_id,
            principal.subject,
            response.answer,
            [uuid.UUID(c.chunk_id) for c in response.citations],
        )

    with SessionLocal() as db:
        citations = relabel_citations(db, [c.to_dict() for c in response.citations])

    return {
        "message_id": str(message_id),
        "standalone_question": turn.standalone_question,
        "answer": response.answer,
        "citations": citations,
    }


@router.post("/{conversation_id}/messages/stream")
def post_message_stream(
    conversation_id: uuid.UUID,
    request: MessageRequest,
    principal: Principal = Depends(llm_rate_limited),
):
    # Check ownership before the response starts: once SSE bytes are sent
    # the status is already 200, so a 404 is only possible up front.
    with SessionLocal() as db:
        get_owned_conversation(db, conversation_id, principal.subject)

    def events():
        yield sse_event("status", {"stage": "rewriting"})

        try:
            with SessionLocal() as db:
                turn = prepare_turn(
                    db, conversation_id, principal, request.question,
                    top_k=request.top_k,
                )
        except ConversationNotFound:
            yield sse_event("error", {"detail": "Conversation not found."})
            yield sse_event("done", {})
            return

        saved = False
        try:
            yield sse_event("question", {"standalone": turn.standalone_question})

            answer, sources, failed = None, [], False
            for event, data in stream_answer_events(
                question=turn.standalone_question,
                retrieved=turn.retrieved,
                max_context_tokens=request.max_context_tokens,
            ):
                if event == "answer":
                    answer = data["text"]
                elif event == "citations":
                    sources = [uuid.UUID(s["chunk_id"]) for s in data["sources"]]
                    with SessionLocal() as db:
                        data = {"sources": relabel_citations(db, data["sources"])}
                elif event == "error":
                    failed = True
                yield sse_event(event, data)

            if not failed and answer is not None:
                try:
                    with SessionLocal() as db:
                        message_id = record_answer(
                            db, conversation_id, principal.subject, answer, sources
                        )
                    # Set before yielding: a disconnect at the next yield
                    # must not discard a turn that is already stored.
                    saved = True
                    yield sse_event("saved", {"message_id": str(message_id)})
                except ConversationNotFound:
                    saved = True  # conversation is gone: nothing to discard
                    yield sse_event(
                        "error", {"detail": "Conversation was deleted; answer not saved."}
                    )

            yield sse_event("done", {})
        finally:
            # LLM failure, client disconnect, or any error before the answer
            # was stored: remove the question so history stays consistent.
            if not saved:
                with SessionLocal() as db:
                    discard_turn(
                        db, conversation_id, principal.subject, turn.user_message_id
                    )


    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
