from __future__ import annotations

import logging
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.schemas import CheckoutRequest, CheckoutResponse
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.checkout import Checkout, CheckoutStatus
from app.observability.context import set_correlation_id
from app.core.config import settings
from app.observability.logging import configure_logging
from app.observability.metrics import Metrics
from app.services.idempotency import IdempotencyService
from app.services.redis_client import get_redis
from app.workers.tasks import process_checkout

logger = logging.getLogger(__name__)

app = FastAPI(title="CartShield")


@app.on_event("startup")
def startup() -> None:
    configure_logging(settings.log_level)
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    correlation_id = request.headers.get("Idempotency-Key") or str(uuid.uuid4())
    set_correlation_id(correlation_id)
    response = await call_next(request)
    response.headers["X-Correlation-Id"] = correlation_id
    return response


def _response_for(checkout: Checkout) -> CheckoutResponse:
    if checkout.status in {CheckoutStatus.pending, CheckoutStatus.in_progress}:
        message = "Checkout is processing."
    elif checkout.status == CheckoutStatus.succeeded:
        message = "Checkout completed."
    else:
        message = "Checkout failed."
    return CheckoutResponse(
        checkout_id=checkout.id,
        status=checkout.status.value,
        order_id=checkout.order_id,
        message=message,
    )


@app.post("/checkout", response_model=CheckoutResponse)
def create_checkout(
    payload: CheckoutRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_db),
) -> CheckoutResponse:
    if not idempotency_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idempotency-Key header required")

    redis_client = get_redis()
    idempotency = IdempotencyService(redis_client)
    payload_dict = payload.model_dump()
    payload_hash = idempotency.payload_hash(payload_dict)
    # Idempotency is enforced at the edge; Postgres remains the source of truth
    # for the checkout state and provides deterministic responses per key+payload.
    decision = idempotency.check_or_set(idempotency_key, payload_hash)

    if decision == "conflict":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key conflict: payload does not match previous request.",
        )

    checkout_id = idempotency.get_checkout_id(idempotency_key)
    checkout = None
    if checkout_id:
        checkout = session.query(Checkout).filter(Checkout.id == checkout_id).one_or_none()
    if not checkout:
        checkout = (
            session.query(Checkout)
            .filter(Checkout.idempotency_key == idempotency_key)
            .one_or_none()
        )
    if not checkout:
        checkout = Checkout(
            id=str(uuid.uuid4()),
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            status=CheckoutStatus.pending,
            request_payload=payload_dict,
        )
        session.add(checkout)
        session.commit()
    idempotency.bind_checkout(idempotency_key, checkout.id)
    process_checkout.delay(checkout.id)
    logger.info("Checkout accepted", extra={"extra": {"checkout_id": checkout.id}})
    return _response_for(checkout)


@app.get("/checkout/{checkout_id}", response_model=CheckoutResponse)
def get_checkout(checkout_id: str, session: Session = Depends(get_db)) -> CheckoutResponse:
    checkout = session.query(Checkout).filter(Checkout.id == checkout_id).one_or_none()
    if not checkout:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkout not found")
    return _response_for(checkout)


@app.get("/metrics")
def metrics() -> dict[str, int]:
    return Metrics(get_redis()).snapshot()
