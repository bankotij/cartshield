from __future__ import annotations

import logging

from celery.exceptions import MaxRetriesExceededError

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.checkout import Checkout, CheckoutStatus
from app.observability.context import set_correlation_id
from app.observability.logging import configure_logging
from app.observability.metrics import Metrics
from app.services.checkout_orchestrator import (
    NonRetryableStepError,
    RetryableStepError,
    compensate,
    run_steps,
)
from app.services.redis_client import get_redis
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
BASE_DELAY_SECONDS = 2

configure_logging(settings.log_level)


def _backoff_delay(retries: int) -> int:
    return min(60, BASE_DELAY_SECONDS * (2**retries))


@celery_app.task(bind=True, name="app.workers.tasks.process_checkout", max_retries=MAX_RETRIES)
def process_checkout(self, checkout_id: str) -> None:
    set_correlation_id(checkout_id)
    metrics = Metrics(get_redis())
    session = SessionLocal()
    try:
        checkout = session.query(Checkout).filter(Checkout.id == checkout_id).one_or_none()
        if not checkout:
            logger.error("Checkout not found", extra={"extra": {"checkout_id": checkout_id}})
            return
        if checkout.status in {CheckoutStatus.succeeded, CheckoutStatus.failed, CheckoutStatus.dead_lettered}:
            return
        # Celery delivers tasks at-least-once; we use persisted step state to make
        # the workflow effectively-once by skipping completed steps on retries.
        checkout.status = CheckoutStatus.in_progress
        checkout.attempts += 1
        session.commit()
        try:
            run_steps(session, checkout)
            checkout.status = CheckoutStatus.succeeded
            checkout.current_step = None
            session.commit()
            metrics.increment_success()
        except RetryableStepError as exc:
            checkout.last_error = str(exc)
            session.commit()
            metrics.increment_retry()
            logger.warning(
                "Retryable checkout failure",
                extra={
                    "extra": {
                        "checkout_id": checkout.id,
                        "attempt": self.request.retries + 1,
                        "error": str(exc),
                    }
                },
            )
            try:
                raise self.retry(countdown=_backoff_delay(self.request.retries))
            except MaxRetriesExceededError:
                checkout.status = CheckoutStatus.failed
                session.commit()
                metrics.increment_failure()
                compensate(session, checkout)
                dead_letter_checkout.delay(checkout_id, reason="max_retries_exceeded")
        except NonRetryableStepError as exc:
            checkout.status = CheckoutStatus.failed
            checkout.last_error = str(exc)
            session.commit()
            metrics.increment_failure()
            logger.error(
                "Non-retryable checkout failure",
                extra={"extra": {"checkout_id": checkout.id, "error": str(exc)}},
            )
            compensate(session, checkout)
            dead_letter_checkout.delay(checkout_id, reason="permanent_failure")
    finally:
        session.close()


@celery_app.task(name="app.workers.tasks.dead_letter_checkout")
def dead_letter_checkout(checkout_id: str, reason: str) -> None:
    set_correlation_id(checkout_id)
    session = SessionLocal()
    try:
        checkout = session.query(Checkout).filter(Checkout.id == checkout_id).one_or_none()
        if not checkout:
            return
        checkout.status = CheckoutStatus.dead_lettered
        checkout.last_error = f"dead_lettered:{reason}"
        session.commit()
        logger.error(
            "Checkout moved to dead letter queue",
            extra={"extra": {"checkout_id": checkout_id, "reason": reason}},
        )
    finally:
        session.close()
