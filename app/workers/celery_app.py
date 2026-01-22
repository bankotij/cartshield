from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "cartshield",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_default_queue="checkout",
    task_routes={
        "app.workers.tasks.process_checkout": {"queue": "checkout"},
        "app.workers.tasks.dead_letter_checkout": {"queue": "dead_letter"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)

celery_app.autodiscover_tasks(["app.workers"])
