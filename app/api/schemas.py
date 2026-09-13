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
    sku: str = Field(min_length=1)
    quantity: int = Field(ge=1)


class CheckoutRequest(BaseModel):
    customer_id: str = Field(min_length=1)
    items: list[Item] = Field(min_length=1)
    payment_method: str = Field(min_length=1)
    total_amount: float = Field(gt=0, allow_inf_nan=False)
    inventory_mode: FailureMode = FailureMode.none
    payment_mode: FailureMode = FailureMode.none


class CheckoutResponse(BaseModel):
    checkout_id: str
    status: Literal["pending", "in_progress", "succeeded", "failed", "dead_lettered"]
    order_id: str | None = None
    message: str
