from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import Field

from .base import TrackableDto


class ExtraDevicePurchaseDto(TrackableDto):
    """DTO для покупки дополнительных устройств."""
    
    id: Optional[int] = Field(default=None, frozen=True)
    
    subscription_id: int
    user_telegram_id: int
    
    device_count: int
    price: int  # Стоимость за месяц
    
    is_active: bool = True
    auto_renew: bool = True  # Автопродление
    
    purchased_at: datetime
    expires_at: datetime
    
    created_at: Optional[datetime] = Field(default=None, frozen=True)
    updated_at: Optional[datetime] = Field(default=None, frozen=True)
    
    @property
    def is_expired(self) -> bool:
        """Проверяет, истёк ли срок действия."""
        from src.core.utils.time import datetime_now
        return datetime_now() > self.expires_at
    
    @property
    def days_remaining(self) -> int:
        """Возвращает количество оставшихся дней."""
        from src.core.utils.time import datetime_now
        if self.is_expired:
            return 0
        delta = self.expires_at - datetime_now()
        return max(0, delta.days + (1 if delta.seconds > 0 else 0))
