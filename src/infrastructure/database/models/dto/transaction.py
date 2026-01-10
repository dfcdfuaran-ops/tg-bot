from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from src.core.utils.time import datetime_now

if TYPE_CHECKING:
    from .plan import PlanSnapshotDto
    from .user import BaseUserDto

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from src.core.enums import Currency, PaymentGatewayType, PurchaseType, TransactionStatus

from .base import TrackableDto


class PriceDetailsDto(TrackableDto):
    original_amount: Decimal = Decimal(2)
    discount_percent: int = 0
    final_amount: Decimal = Decimal(2)
    global_discount_amount: Decimal = Decimal(0)  # Сумма глобальной скидки

    @model_validator(mode='after')
    def set_final_amount_if_not_provided(self):
        # Если final_amount не был явно задан (остался с дефолтным значением),
        # установить его равным original_amount
        if self.final_amount == Decimal(2) and self.original_amount != Decimal(2):
            self.final_amount = self.original_amount
        return self

    @property
    def is_free(self) -> bool:
        return self.final_amount == 0


class BaseTransactionDto(TrackableDto):
    id: Optional[int] = Field(default=None, frozen=True)
    payment_id: UUID

    status: TransactionStatus
    is_test: bool = False

    purchase_type: PurchaseType
    gateway_type: PaymentGatewayType

    pricing: PriceDetailsDto
    currency: Currency
    plan: "PlanSnapshotDto"

    created_at: Optional[datetime] = Field(default=None, frozen=True)
    updated_at: Optional[datetime] = Field(default=None, frozen=True)

    @property
    def is_completed(self) -> bool:
        return self.status == TransactionStatus.COMPLETED

    @property
    def has_old(self) -> bool:
        if not self.created_at:
            return False
        return (
            self.status == TransactionStatus.PENDING
            and datetime_now() - self.created_at > timedelta(minutes=30)
        )


class TransactionDto(BaseTransactionDto):
    user: Optional["BaseUserDto"] = None
