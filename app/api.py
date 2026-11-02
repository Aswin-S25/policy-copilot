from pathlib import Path
import shutil
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from celery.result import AsyncResult
from sqlalchemy import select
from pydantic import BaseModel
from fastapi.responses import StreamingResponse

from app.citations import remove_invalid_citations
from app.llm import stream_answer
from app.prompt import SYSTEM_PROMPT, build_user_prompt
from app.rag_stream import stream_question
from app.celery_app import celery_app
from app.db import SessionLocal
from app.models import Document
from app.sse import sse_event
from ingest.tasks import ingest_file
from app.retrieval import retrieve_chunks
from app.context import build_context
from app.rag import answer_question


app = FastAPI(
    title="Policy Copilot"
)

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True
)


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


@app.post("/documents/ingest")
async def upload_document(
    file: UploadFile = File(...),
):
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
        str(destination)
    )
    
    
    return {
        "task_id": task.id,
        "status": "queued"
    }
    
@app.get("/task/{task_id}")
def get_task_status(
    task_id: str,
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
    query: str
    top_k: int = 5


@app.post("/search")
def search_documents(request: SearchRequest):
    db = SessionLocal()
    
    try:
        results = retrieve_chunks(
            db = db,
            query=request.query,
            top_k=request.top_k
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
    question: str
    top_k: int = 5
    min_score: float = 0.45
    max_context_tokens: int = 3000



@app.post("/talk")
def ask(request: AskRequest):
    db = SessionLocal()
    
    try:
        result = answer_question(
            db=db,
            question=request.question,
            top_k=request.top_k,
            min_score=request.min_score,
            max_context_tokens=request.max_context_tokens,
        )
        
        return {
            "answer": result.answer,
            "citations": [
                {
                    "source": citation.source_number,
                    "document": citation.document_title,
                    "section": citation.section_path,
                    "chunk_id": citation.chunk_id,
                    "score": citation.score,
                }
                for citation in result.citations
            ],
            "retrieved_count": result.retrieved_count,
            "context_tokens": result.context_tokens,
        }
    finally:
        db.close()


@app.post("/ask/stream")
def ask_stream(request: AskRequest):

    def event_generator():

        db = SessionLocal()

        try:
            yield sse_event(
                "status",
                {
                    "stage": "retrieval",
                },
            )

            retrieved = retrieve_chunks(
                db=db,
                query=request.question,
                top_k=request.top_k,
                min_score=request.min_score,
            )

            if not retrieved:
                yield sse_event(
                    "answer",
                    {
                        "text": (
                            "I could not find relevant information "
                            "in the available policies."
                        )
                    },
                )

                yield sse_event(
                    "done",
                    {},
                )

                return

            yield sse_event(
                "status",
                {
                    "stage": "generation",
                },
            )

            context = build_context(
                retrieved_chunks=retrieved,
                max_tokens=request.max_context_tokens,
            )

            prompt = build_user_prompt(
                question=request.question,
                context=context.text,
            )

            answer_parts = []

            for token in stream_answer(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
            ):
                answer_parts.append(token)

                yield sse_event(
                    "token",
                    {
                        "text": token,
                    },
                )

            answer = "".join(answer_parts)

            available_sources = {
                item.source_number
                for item in context.chunks
            }

            answer = remove_invalid_citations(
                answer,
                available_sources,
            )

            citations = [
                {
                    "source": item.source_number,
                    "document": item.chunk.document_title,
                    "section": item.chunk.section_path,
                    "chunk_id": str(item.chunk.chunk_id),
                    "score": item.chunk.score,
                }
                for item in context.chunks
            ]

            yield sse_event(
                "citations",
                {
                    "sources": citations,
                },
            )

            yield sse_event(
                "done",
                {},
            )

        finally:
            db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )