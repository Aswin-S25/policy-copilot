from pathlib import Path

from celery import Task

from app.celery_app import celery_app
from app.db import SessionLocal

from ingest.parse import parse_markdown
from ingest.upsert import ingest_document
from ingest.embed import embed_document_chunks


class DatabaseTask(Task):
    def after_return(
        self,
        status,
        retval,
        task_id,
        args,
        kwargs,
        einfo,
    ):
        pass


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def ingest_file(
    self,
    file_path: str,
):
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(
            f"File does not exist: {file_path}"
        )

    if path.suffix.lower() != ".md":
        raise ValueError(
            f"Unsupported file type: {path.suffix}"
        )

    db = SessionLocal()

    try:
        parsed = parse_markdown(
            str(path)
        )

        document = ingest_document(
            db,
            parsed,
        )
        
        embedding_count = embed_document_chunks(
            db,
            document.id
        )

        return {
            "document_id": str(document.id),
            "title": document.title,
            "source": document.source,
            "embedding_chunks": embedding_count,
        }

    finally:
        db.close()