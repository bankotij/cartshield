from __future__ import annotations

from app.services.errors import PermanentError, TimeoutError, TransientError


def charge_payment(mode: str) -> str:
    if mode == "timeout":
        raise TimeoutError("Payment gateway timeout")
    if mode == "transient":
        raise TransientError("Payment gateway transient error")
    if mode == "permanent":
        raise PermanentError("Payment gateway permanent failure")
    return "payment_ref_123"


def refund_payment() -> None:
    # Compensating action. This can also be retried separately in a real system.
    return None
