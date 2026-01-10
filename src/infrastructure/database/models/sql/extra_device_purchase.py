from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .subscription import Subscription
    from .user import User

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseSql
from .timestamp import TimestampMixin


class ExtraDevicePurchase(BaseSql, TimestampMixin):
    """Модель для хранения покупок дополнительных устройств."""
    
    __tablename__ = "extra_device_purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    subscription_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    user_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    
    device_count: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[int] = mapped_column(Integer, nullable=False)  # Стоимость за месяц
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    
    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    
    # Relationships
    subscription: Mapped["Subscription"] = relationship(
        "Subscription",
        back_populates="extra_device_purchases",
        lazy="selectin",
    )
    
    user: Mapped["User"] = relationship(
        "User",
        back_populates="extra_device_purchases",
        lazy="selectin",
    )
