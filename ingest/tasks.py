import logging
import time
from pathlib import Path

from celery import Task

from app.core.celery_app import celery_app
from app.core.db import SessionLocal
from app.core.observability import ms_since, request_context

from ingest.embed import embed_document_chunks
from ingest.parse import parse_markdown
from ingest.upsert import ingest_document

logger = logging.getLogger("policy_copilot.ingest")


class DatabaseTask(Task):
    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        pass


@celery_app.task(
    bind=True,
    base=DatabaseTask,
    autoretry_for=(Exception,),
    # Bad input cannot be fixed by retrying.
    dont_autoretry_for=(FileNotFoundError, ValueError),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def ingest_file(
    self,
    file_path: str,
    allowed_roles: list[str],
    request_id: str | None = None,
):
    # The upload request's ID links worker logs to the API request that
    # caused them; fall back to the task ID for tasks queued elsewhere.
    with request_context(request_id or self.request.id):
        started = time.perf_counter()
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File does not exist: {file_path}")

        if path.suffix.lower() != ".md":
            raise ValueError(f"Unsupported file type: {path.suffix}")

        db = SessionLocal()
        try:
            parsed = parse_markdown(str(path))

            document = ingest_document(db, parsed, allowed_roles=allowed_roles)

            embedding_count = embed_document_chunks(db, document.id)

            logger.info("ingest_completed", extra={
                "task_id": self.request.id,
                "document_id": str(document.id),
                "embedded_chunks": embedding_count,
                "allowed_roles": allowed_roles,
                "attempt": self.request.retries + 1,
                "duration_ms": ms_since(started),
            })

            return {
                "document_id": str(document.id),
                "title": document.title,
                "source": document.source,
                "embedding_chunks": embedding_count,
                "allowed_roles": allowed_roles,
            }
        finally:
            db.close()
