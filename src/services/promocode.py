from typing import Optional

from aiogram import Bot
from fluentogram import TranslatorHub
from loguru import logger
from redis.asyncio import Redis

from src.core.config import AppConfig
from src.core.enums import PromocodeRewardType
from src.infrastructure.database import UnitOfWork
from src.infrastructure.database.models.dto import PromocodeDto
from src.infrastructure.database.models.sql import Promocode
from src.infrastructure.redis import RedisRepository

from .base import BaseService


class PromocodeService(BaseService):
    uow: UnitOfWork

    def __init__(
        self,
        config: AppConfig,
        bot: Bot,
        redis_client: Redis,
        redis_repository: RedisRepository,
        translator_hub: TranslatorHub,
        #
        uow: UnitOfWork,
    ) -> None:
        super().__init__(config, bot, redis_client, redis_repository, translator_hub)
        self.uow = uow

    async def create(self, promocode: PromocodeDto) -> Optional[PromocodeDto]:
        """Создание нового промокода."""
        db_promocode = Promocode(
            code=promocode.code,
            name=promocode.name,
            is_active=promocode.is_active,
            reward_type=promocode.reward_type,
            reward=promocode.reward,
            plan=promocode.plan,
            lifetime=promocode.lifetime,
            max_activations=promocode.max_activations,
            allowed_plan_ids=promocode.allowed_plan_ids or [],
        )
        
        db_created_promocode = await self.uow.repository.promocodes.create(db_promocode)
        await self.uow.commit()
        
        logger.info(f"Created promocode '{promocode.code}'")
        return PromocodeDto.from_model(db_created_promocode)

    async def get(self, promocode_id: int) -> Optional[PromocodeDto]:
        db_promocode = await self.uow.repository.promocodes.get(promocode_id)

        if db_promocode:
            logger.debug(f"Retrieved promocode '{promocode_id}'")
        else:
            logger.warning(f"Promocode '{promocode_id}' not found")

        return PromocodeDto.from_model(db_promocode)

    async def get_by_code(self, promocode_code: str) -> Optional[PromocodeDto]:
        db_promocode = await self.uow.repository.promocodes.get_by_code_with_activations(
            promocode_code
        )

        if db_promocode:
            logger.debug(f"Retrieved promocode by code '{promocode_code}'")
        else:
            logger.warning(f"Promocode with code '{promocode_code}' not found")

        return PromocodeDto.from_model(db_promocode)

    async def get_all(self) -> list[PromocodeDto]:
        db_promocodes = await self.uow.repository.promocodes.get_all()
        logger.debug(f"Retrieved '{len(db_promocodes)}' promocodes")
        return PromocodeDto.from_model_list(db_promocodes)

    async def update(self, promocode: PromocodeDto) -> Optional[PromocodeDto]:
        # Обновляем все поля промокода, а не только changed_data, потому что
        # DTO в dialog_data сериализуется/десериализуется и changed_data теряется.
        # Поэтому собираем словарь из model_dump и исключаем служебные поля.
        promocode_data = promocode.model_dump()
        for field in ["id", "created_at", "updated_at", "activations", "availability"]:
            promocode_data.pop(field, None)

        db_updated_promocode = await self.uow.repository.promocodes.update(
            promocode_id=promocode.id,  # type: ignore[arg-type]
            **promocode_data,
        )

        if db_updated_promocode:
            logger.info(f"Updated promocode '{promocode.code}' successfully")
        else:
            logger.warning(
                f"Attempted to update promocode '{promocode.code}' "
                f"(ID: '{promocode.id}'), but promocode was not found or update failed"
            )

        return PromocodeDto.from_model(db_updated_promocode)

    async def delete(self, promocode_id: int) -> bool:
        # Получаем промокод с активациями для восстановления скидок у пользователей
        db_promocode = await self.uow.repository.promocodes.get(promocode_id)
        
        if db_promocode:
            # Восстанавливаем скидки у пользователей на основе сохраненных previous_discount
            if db_promocode.activations:
                for activation in db_promocode.activations:
                    user = await self.uow.repository.users.get(activation.user_telegram_id)
                    if not user:
                        continue
                    
                    if db_promocode.reward_type == PromocodeRewardType.PURCHASE_DISCOUNT:
                        # Восстанавливаем предыдущую скидку purchase_discount и её срок действия
                        await self.uow.repository.users.update(
                            activation.user_telegram_id,
                            purchase_discount=activation.previous_discount,
                            purchase_discount_expires_at=activation.previous_discount_expires_at
                        )
                        logger.info(
                            f"Restored purchase_discount to {activation.previous_discount} "
                            f"(expires: {activation.previous_discount_expires_at}) "
                            f"for user '{activation.user_telegram_id}' due to promocode deletion"
                        )
                    
                    elif db_promocode.reward_type == PromocodeRewardType.PERSONAL_DISCOUNT:
                        # Восстанавливаем предыдущую скидку personal_discount
                        await self.uow.repository.users.update(
                            activation.user_telegram_id,
                            personal_discount=activation.previous_discount
                        )
                        logger.info(
                            f"Restored personal_discount to {activation.previous_discount} "
                            f"for user '{activation.user_telegram_id}' due to promocode deletion"
                        )
                    
                    # Очищаем кэш пользователя для обновления данных
                    await self.redis_client.delete(f"cache:get_user:{activation.user_telegram_id}")
                
                # Коммитим изменения скидок пользователей до удаления промокода
                await self.uow.commit()
        
        result = await self.uow.repository.promocodes.delete(promocode_id)

        if result:
            await self.uow.commit()
            logger.info(f"Promocode '{promocode_id}' deleted successfully")
        else:
            logger.warning(
                f"Failed to delete promocode '{promocode_id}'. "
                f"Promocode not found or deletion failed"
            )

        return result

    async def filter_by_type(self, promocode_type: PromocodeRewardType) -> list[PromocodeDto]:
        db_promocodes = await self.uow.repository.promocodes.filter_by_type(promocode_type)
        logger.debug(
            f"Filtered promocodes by type '{promocode_type}', found '{len(db_promocodes)}'"
        )
        return PromocodeDto.from_model_list(db_promocodes)

    async def filter_active(self, is_active: bool = True) -> list[PromocodeDto]:
        db_promocodes = await self.uow.repository.promocodes.filter_active(is_active)
        logger.debug(f"Filtered active promocodes: '{is_active}', found '{len(db_promocodes)}'")
        return PromocodeDto.from_model_list(db_promocodes)
