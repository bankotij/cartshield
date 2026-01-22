from __future__ import annotations

from app.services.errors import PermanentError, TimeoutError, TransientError


def reserve_inventory(mode: str) -> None:
    if mode == "timeout":
        raise TimeoutError("Inventory service timeout")
    if mode == "transient":
        raise TransientError("Inventory service transient error")
    if mode == "permanent":
        raise PermanentError("Inventory service permanent failure")


def release_inventory() -> None:
    # Compensating action. In real systems this can also fail and needs monitoring.
    return None
