from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.models.checkout import Checkout, CheckoutStep, CheckoutStepName, CheckoutStepStatus
from app.services.errors import ExternalServiceError, PermanentError
from app.services.inventory import release_inventory, reserve_inventory
from app.services.order import confirm_order, create_order
from app.services.payment import charge_payment, refund_payment

logger = logging.getLogger(__name__)


class RetryableStepError(Exception):
    pass


class NonRetryableStepError(Exception):
    pass


def _create_order_wrapper(checkout: Checkout) -> None:
    checkout.order_id = create_order()


@dataclass(frozen=True)
class StepDefinition:
    name: CheckoutStepName
    action: Callable[[Checkout], None]
    compensate: Callable[[], None] | None


STEPS: list[StepDefinition] = [
    StepDefinition(
        CheckoutStepName.reserve_inventory,
        lambda checkout: reserve_inventory(checkout.request_payload["inventory_mode"]),
        release_inventory,
    ),
    StepDefinition(
        CheckoutStepName.charge_payment,
        lambda checkout: charge_payment(checkout.request_payload["payment_mode"]),
        refund_payment,
    ),
    StepDefinition(CheckoutStepName.create_order, lambda checkout: _create_order_wrapper(checkout), None),
    StepDefinition(CheckoutStepName.confirm_order, lambda checkout: confirm_order(), None),
]


def get_or_create_step(session: Session, checkout_id: str, step_name: CheckoutStepName) -> CheckoutStep:
    step = (
        session.query(CheckoutStep)
        .filter(CheckoutStep.checkout_id == checkout_id, CheckoutStep.step_name == step_name)
        .one_or_none()
    )
    if step:
        return step
    step = CheckoutStep(checkout_id=checkout_id, step_name=step_name)
    session.add(step)
    session.commit()
    session.refresh(step)
    return step


def run_steps(session: Session, checkout: Checkout) -> None:
    for definition in STEPS:
        checkout.current_step = definition.name
        session.commit()
        step = get_or_create_step(session, checkout.id, definition.name)
        if step.status == CheckoutStepStatus.succeeded:
            continue
        step.attempts += 1
        session.commit()
        try:
            definition.action(checkout)
            step.status = CheckoutStepStatus.succeeded
            step.last_error = None
            session.commit()
        except PermanentError as exc:
            step.status = CheckoutStepStatus.failed
            step.last_error = str(exc)
            session.commit()
            raise NonRetryableStepError(str(exc)) from exc
        except ExternalServiceError as exc:
            step.status = CheckoutStepStatus.failed
            step.last_error = str(exc)
            session.commit()
            raise RetryableStepError(str(exc)) from exc


def compensate(session: Session, checkout: Checkout) -> None:
    # Compensation is best-effort; failures are logged and the checkout is dead-lettered.
    for definition in reversed(STEPS):
        if definition.compensate is None:
            continue
        step = (
            session.query(CheckoutStep)
            .filter(
                CheckoutStep.checkout_id == checkout.id,
                CheckoutStep.step_name == definition.name,
            )
            .one_or_none()
        )
        if not step or step.status != CheckoutStepStatus.succeeded:
            continue
        try:
            definition.compensate()
            step.status = CheckoutStepStatus.compensated
            session.commit()
        except Exception as exc:  # noqa: BLE001 - best-effort compensation
            logger.warning(
                "Compensation failed",
                extra={"extra": {"checkout_id": checkout.id, "step": definition.name, "error": str(exc)}},
            )
