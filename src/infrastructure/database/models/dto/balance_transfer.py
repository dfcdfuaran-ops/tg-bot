from datetime import datetime
from typing import Optional

from .base import BaseDto


class BalanceTransferDto(BaseDto):
    """DTO для истории переводов баланса."""
    
    id: Optional[int] = None
    sender_telegram_id: int
    recipient_telegram_id: int
    amount: int
    commission: int = 0
    message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Данные получателя (для отображения в истории)
    recipient_name: Optional[str] = None
    recipient_username: Optional[str] = None
