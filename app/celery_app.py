from celery import Celery

from app.config import get_infra_settings

_settings = get_infra_settings()

celery_app = Celery(
    "policy_copilot",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
)



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