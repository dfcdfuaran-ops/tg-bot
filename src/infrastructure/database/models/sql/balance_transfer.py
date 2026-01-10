from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .user import User

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import BaseSql
from .timestamp import TimestampMixin


class BalanceTransfer(BaseSql, TimestampMixin):
    """Модель для хранения истории переводов баланса."""
    
    __tablename__ = "balance_transfers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Отправитель
    sender_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Получатель
    recipient_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE"),
        nullable=False,
    )
    
    # Сумма перевода (без комиссии)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Комиссия
    commission: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    
    # Сообщение перевода (опционально)
    message: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Связи
    sender: Mapped["User"] = relationship(
        "User",
        foreign_keys=[sender_telegram_id],
        lazy="selectin",
    )
    
    recipient: Mapped["User"] = relationship(
        "User",
        foreign_keys=[recipient_telegram_id],
        lazy="selectin",
    )
