from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class FailureMode(str, Enum):
    none = "none"
    timeout = "timeout"
    transient = "transient"
    permanent = "permanent"


class Item(BaseModel):
    sku: str
    quantity: int = Field(ge=1)


class CheckoutRequest(BaseModel):
    customer_id: str
    items: list[Item]
    payment_method: str
    total_amount: float = Field(gt=0)
    inventory_mode: FailureMode = FailureMode.none
    payment_mode: FailureMode = FailureMode.none


class CheckoutResponse(BaseModel):
    checkout_id: str
    status: Literal["pending", "in_progress", "succeeded", "failed", "dead_lettered"]
    order_id: str | None = None
    message: str
