from __future__ import annotations

import contextvars
import uuid

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default=""
)


def get_correlation_id() -> str:
    value = _correlation_id.get()
    if value:
        return value
    generated = str(uuid.uuid4())
    _correlation_id.set(generated)
    return generated


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)
