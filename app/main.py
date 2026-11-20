from pathlib import Path
import shutil
import uuid
import logging


from fastapi import (
    FastAPI,
    File, 
    Form, 
    HTTPException,
    UploadFile,
    Depends
)
from celery.result import AsyncResult
from pydantic import BaseModel, ConfigDict
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from app.core.config import get_infra_settings, get_settings
from app.core.observability import (
    RequestContextMiddleware,
    configure_logging,
    current_request_id,
    record,
)
from app.conversations.repository import ConversationNotFound
from app.core.security import Principal, get_current_principal, require_admin
from app.core.authz import normalize_roles
from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.rag.llm import UNAVAILABLE_MESSAGE, LLMBusy, LLMUnavailable
from app.core.rate_limit import llm_rate_limited, search_rate_limited
from app.api.sse import sse_event
from ingest.tasks import ingest_file
from app.rag.context import build_context
from app.rag.pipeline import answer_question, stream_answer_events
from app.retrieval.search import search_policies
from app.api.conversations import router as conversation_router
from app.api.health import lifespan, router as health_router
from app.api.sources import router as sources_router
from app.api.documents import router as documents_router
from app.api.auth import router as auth_router


configure_logging(get_infra_settings().log_level)
logger = logging.getLogger("policy_copilot.api")

app = FastAPI(
    title="Policy Copilot",
    lifespan=lifespan,
)
app.add_middleware(RequestContextMiddleware)

# Cross-origin access for a frontend hosted elsewhere (e.g. Vercel). Only the
# configured origins; no cookies (auth is a bearer header). Retry-After is
# exposed so the browser can show rate-limit countdowns. Added last, so it is
# the outermost middleware and answers preflight requests itself.
_cors_origins = get_infra_settings().cors_origin_list
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["Retry-After", "X-Request-ID"],
        max_age=600,
    )

app.include_router(health_router)
app.include_router(conversation_router)
app.include_router(sources_router)
app.include_router(documents_router)
app.include_router(auth_router)


@app.exception_handler(ConversationNotFound)
def conversation_not_found(request, exc):
    # Identical response for "does not exist" and "belongs to another user",
    # and no ID in the body: never confirm that someone else's ID is valid.
    logger.info("conversation_not_found")
    return JSONResponse(
        status_code=404,
        content={"detail": "Conversation not found."},
    )


@app.exception_handler(LLMUnavailable)
def llm_unavailable(request, exc):
    # Internal detail goes to the log; the client gets the generic message.
    logger.error("llm_unavailable", extra={"detail": str(exc)})
    record(answer_outcome="llm_busy" if isinstance(exc, LLMBusy) else "llm_unavailable")
    return JSONResponse(
        status_code=503,
        content={"detail": UNAVAILABLE_MESSAGE},
        headers={"Retry-After": "10"},
    )


UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True
)
get_settings()


@app.post("/documents/ingest")
async def upload_document(
    file: UploadFile = File(...),
    allowed_roles: list[str] = Form(...),
    principal: Principal = Depends(require_admin),
):
    try:
        roles = normalize_roles(allowed_roles)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    suffix = Path(file.filename).suffix.lower()
    
    if suffix not in {".md"}:
        raise HTTPException(
            status_code=400,
            detail="Only markdown files are currently supported."
        )
        
    file_id = uuid.uuid4()
    
    
    destination = (
        UPLOAD_DIR
        / f"{file_id}{suffix}"
    )
    
    with destination.open("wb") as buffer:
        shutil.copyfileobj(
            file.file,
            buffer
        )
    
    task = ingest_file.delay(
        str(destination),
        roles,
        request_id=current_request_id(),
    )
    
    
    return {
        "task_id": task.id,
        "status": "queued"
    }
    
@app.get("/task/{task_id}")
def get_task_status(
    task_id: str,
    principal: Principal = Depends(require_admin)
):
    result = AsyncResult(
        task_id,
        app=celery_app
    )
    
    response = {
        "task_id": task_id,
        "status": result.status,
    }
    
    if result.successful():
        response["result"] = result.result
    
    if result.failed():
        response["error"] = str(
            result.result
        )
    return response


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str
    top_k: int = 5


@app.post("/search")
def search_documents(
    request: SearchRequest,
    principal: Principal = Depends(search_rate_limited),
):
    db = SessionLocal()
    
    try:
        results = search_policies(
            db=db,
            query=request.query,
            top_k=request.top_k,
            roles=principal.document_roles,
        )
        
        context = build_context(
            retrieved_chunks=results,
            max_tokens=3000,
        )
        
        return {
            "query": request.query,
            "retrieved_chunks": [
                {
                    "chunk_id": str(result.chunk_id),
                    "document_id": str(result.document_id),
                    "document_title": result.document_title,
                    "section_path": result.section_path,
                    "chunk_index": result.chunk_index,
                    "score": result.score,
                    "content": result.content,
                }
                for result in results
            ],
            "context": {
                "text": context.text,
                "estimated_tokens": context.estimated_tokens,
                "sources": len(context.chunks),
            },
        }
    finally:
        db.close()


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    question: str
    top_k: int = 5
    max_context_tokens: int = 3000



@app.post("/talk")
def ask(
    request: AskRequest,
    principal: Principal = Depends(llm_rate_limited),
):
    db = SessionLocal()
    
    try:
        result = answer_question(
            db=db,
            question=request.question,
            top_k=request.top_k,
            max_context_tokens=request.max_context_tokens,
            roles=principal.document_roles,
        )

        return {
            "answer": result.answer,
            "citations": [
                citation.to_dict()
                for citation in result.citations
            ],
            "retrieved_count": result.retrieved_count,
            "context_tokens": result.context_tokens,
        }
    finally:
        db.close()


@app.post("/ask/stream")
def ask_stream(
    request: AskRequest,
    principal: Principal = Depends(llm_rate_limited),
):

    def event_generator():

        yield sse_event("status", {"stage": "retrieval"})

        # Release the DB connection before the (long) LLM call so a slow
        # generation does not hold a pooled connection.
        db = SessionLocal()
        try:
            retrieved = search_policies(
                db=db,
                query=request.question,
                top_k=request.top_k,
                roles=principal.document_roles,
            )
        finally:
            db.close()

        # Same context building, citation validation and refusal rules as
        # /talk (app/rag/pipeline.py); this endpoint only handles SSE transport.
        for event, data in stream_answer_events(
            question=request.question,
            retrieved=retrieved,
            max_context_tokens=request.max_context_tokens,
        ):
            yield sse_event(event, data)

        yield sse_event("done", {})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )