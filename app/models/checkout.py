from __future__ import annotations

import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CheckoutStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    succeeded = "succeeded"
    failed = "failed"
    dead_lettered = "dead_lettered"


class CheckoutStepName(str, enum.Enum):
    reserve_inventory = "reserve_inventory"
    charge_payment = "charge_payment"
    create_order = "create_order"
    confirm_order = "confirm_order"


class CheckoutStepStatus(str, enum.Enum):
    not_started = "not_started"
    succeeded = "succeeded"
    failed = "failed"
    compensated = "compensated"


class Checkout(Base):
    __tablename__ = "checkouts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[CheckoutStatus] = mapped_column(
        Enum(CheckoutStatus), default=CheckoutStatus.pending, index=True
    )
    current_step: Mapped[CheckoutStepName | None] = mapped_column(
        Enum(CheckoutStepName), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    order_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class CheckoutStep(Base):
    __tablename__ = "checkout_steps"
    __table_args__ = (UniqueConstraint("checkout_id", "step_name", name="uq_checkout_step"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    checkout_id: Mapped[str] = mapped_column(String(36), index=True)
    step_name: Mapped[CheckoutStepName] = mapped_column(Enum(CheckoutStepName))
    status: Mapped[CheckoutStepStatus] = mapped_column(
        Enum(CheckoutStepStatus), default=CheckoutStepStatus.not_started
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
