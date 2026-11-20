from celery import Celery
from celery.signals import setup_logging

from app.core.config import get_infra_settings
from app.core.observability import configure_logging

_settings = get_infra_settings()

celery_app = Celery(
    "policy_copilot",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    # Register tasks so "celery -A app.core.celery_app worker" finds them.
    include=["ingest.tasks"],
)


@setup_logging.connect
def _configure_worker_logging(**kwargs):
    # Connecting to this signal stops Celery from installing its own
    # handlers: the worker logs the same JSON lines as the API.
    configure_logging(_settings.log_level)



celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    timezone="UTC",
    enable_utc=True,

    task_track_started=True,

    task_acks_late=True,

    worker_prefetch_multiplier=1,

    task_default_retry_delay=5,

    task_time_limit=300,

    task_soft_time_limit=240,
)