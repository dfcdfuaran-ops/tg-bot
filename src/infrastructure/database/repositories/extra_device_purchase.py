from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, select

from src.infrastructure.database.models.sql import ExtraDevicePurchase

from .base import BaseRepository


class ExtraDevicePurchaseRepository(BaseRepository):
    """Репозиторий для работы с покупками дополнительных устройств."""
    
    async def create(self, purchase: ExtraDevicePurchase) -> ExtraDevicePurchase:
        return await self.create_instance(purchase)

    async def get(self, purchase_id: int) -> Optional[ExtraDevicePurchase]:
        return await self._get_one(ExtraDevicePurchase, ExtraDevicePurchase.id == purchase_id)

    async def get_by_subscription(self, subscription_id: int) -> list[ExtraDevicePurchase]:
        """Получить все покупки для подписки."""
        return await self._get_many(
            ExtraDevicePurchase, 
            ExtraDevicePurchase.subscription_id == subscription_id
        )

    async def get_active_by_subscription(self, subscription_id: int) -> list[ExtraDevicePurchase]:
        """Получить активные покупки для подписки."""
        return await self._get_many(
            ExtraDevicePurchase,
            and_(
                ExtraDevicePurchase.subscription_id == subscription_id,
                ExtraDevicePurchase.is_active == True,  # noqa: E712
            )
        )

    async def get_by_user(self, telegram_id: int) -> list[ExtraDevicePurchase]:
        """Получить все покупки пользователя."""
        return await self._get_many(
            ExtraDevicePurchase,
            ExtraDevicePurchase.user_telegram_id == telegram_id
        )

    async def get_active_by_user(self, telegram_id: int) -> list[ExtraDevicePurchase]:
        """Получить активные покупки пользователя."""
        return await self._get_many(
            ExtraDevicePurchase,
            and_(
                ExtraDevicePurchase.user_telegram_id == telegram_id,
                ExtraDevicePurchase.is_active == True,  # noqa: E712
            )
        )

    async def get_expired_active(self) -> list[ExtraDevicePurchase]:
        """Получить истекшие, но всё ещё активные покупки."""
        return await self._get_many(
            ExtraDevicePurchase,
            and_(
                ExtraDevicePurchase.is_active == True,  # noqa: E712
                ExtraDevicePurchase.expires_at < datetime.utcnow(),
            )
        )

    async def get_expiring_soon(self, before: datetime) -> list[ExtraDevicePurchase]:
        """Получить покупки, истекающие до указанной даты."""
        return await self._get_many(
            ExtraDevicePurchase,
            and_(
                ExtraDevicePurchase.is_active == True,  # noqa: E712
                ExtraDevicePurchase.expires_at <= before,
            )
        )

    async def update(self, purchase_id: int, **data: Any) -> Optional[ExtraDevicePurchase]:
        return await self._update(ExtraDevicePurchase, ExtraDevicePurchase.id == purchase_id, **data)

    async def delete(self, purchase_id: int) -> bool:
        """Удалить покупку."""
        purchase = await self.get(purchase_id)
        if purchase:
            await self.session.delete(purchase)
            await self.session.flush()
            return True
        return False

    async def deactivate(self, purchase_id: int) -> Optional[ExtraDevicePurchase]:
        """Деактивировать покупку (мягкое удаление)."""
        return await self.update(purchase_id, is_active=False)

    async def disable_auto_renew(self, purchase_id: int) -> Optional[ExtraDevicePurchase]:
        """Отключить автопродление."""
        return await self.update(purchase_id, auto_renew=False)

    async def get_total_active_devices(self, subscription_id: int) -> int:
        """Получить общее количество активных дополнительных устройств для подписки."""
        from sqlalchemy import func
        
        stmt = select(func.coalesce(func.sum(ExtraDevicePurchase.device_count), 0)).where(
            and_(
                ExtraDevicePurchase.subscription_id == subscription_id,
                ExtraDevicePurchase.is_active == True,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_total_monthly_cost(self, subscription_id: int) -> int:
        """Получить общую месячную стоимость дополнительных устройств для подписки."""
        from sqlalchemy import func
        
        stmt = select(func.coalesce(func.sum(ExtraDevicePurchase.price), 0)).where(
            and_(
                ExtraDevicePurchase.subscription_id == subscription_id,
                ExtraDevicePurchase.is_active == True,  # noqa: E712
                ExtraDevicePurchase.auto_renew == True,  # noqa: E712
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0
