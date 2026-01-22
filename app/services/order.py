from __future__ import annotations

import uuid


def create_order() -> str:
    return str(uuid.uuid4())


def confirm_order() -> None:
    return None
