from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import noload, selectinload

from src.core.enums import PromocodeRewardType
from src.infrastructure.database.models.sql import Promocode

from .base import BaseRepository


class PromocodeRepository(BaseRepository):
    async def create(self, promocode: Promocode) -> Promocode:
        return await self.create_instance(promocode)

    async def get(self, promocode_id: int) -> Optional[Promocode]:
        from src.infrastructure.database.models.sql import PromocodeActivation
        stmt = (
            select(Promocode)
            .options(
                selectinload(Promocode.activations).noload(PromocodeActivation.promocode)
            )
            .where(Promocode.id == promocode_id)
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().one_or_none()

    async def get_by_code(self, code: str) -> Optional[Promocode]:
        return await self._get_one(Promocode, Promocode.code == code)

    async def get_by_code_with_activations(self, code: str) -> Optional[Promocode]:
        from src.infrastructure.database.models.sql import PromocodeActivation
        stmt = (
            select(Promocode)
            .options(
                selectinload(Promocode.activations).noload(PromocodeActivation.promocode)
            )
            .where(Promocode.code == code)
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().one_or_none()

    async def get_all(self) -> list[Promocode]:
        from src.infrastructure.database.models.sql import PromocodeActivation
        stmt = (
            select(Promocode)
            .options(
                selectinload(Promocode.activations).noload(PromocodeActivation.promocode)
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().unique().all()

    async def update(self, promocode_id: int, **data: Any) -> Optional[Promocode]:
        return await self._update(Promocode, Promocode.id == promocode_id, **data)

    async def delete(self, promocode_id: int) -> bool:
        return bool(await self._delete(Promocode, Promocode.id == promocode_id))

    async def filter_by_type(self, promocode_type: PromocodeRewardType) -> list[Promocode]:
        return await self._get_many(Promocode, Promocode.reward_type == promocode_type)

    async def filter_active(self, is_active: bool) -> list[Promocode]:
        return await self._get_many(Promocode, Promocode.is_active == is_active)
