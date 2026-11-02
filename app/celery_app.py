from celery import Celery


celery_app = Celery(
    "policy_copilot",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",
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