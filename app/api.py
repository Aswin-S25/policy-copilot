from pathlib import Path
import shutil
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from celery.result import AsyncResult
from sqlalchemy import select
from pydantic import BaseModel

from app.celery_app import celery_app
from app.db import SessionLocal
from app.models import Document
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