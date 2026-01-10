from typing import Optional

from aiogram import Bot
from fluentogram import TranslatorHub
from loguru import logger
from redis.asyncio import Redis

from src.core.config import AppConfig
from src.infrastructure.database import UnitOfWork
from src.infrastructure.database.models.dto import BalanceTransferDto, UserDto
from src.infrastructure.database.models.sql import BalanceTransfer
from src.infrastructure.redis import RedisRepository

from .base import BaseService


class BalanceTransferService(BaseService):
    """Сервис для работы с историей переводов баланса."""
    
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

    async def create_transfer(
        self,
        sender_telegram_id: int,
        recipient_telegram_id: int,
        amount: int,
        commission: int = 0,
        message: Optional[str] = None,
    ) -> BalanceTransferDto:
        """Создать запись о переводе."""
        transfer = BalanceTransfer(
            sender_telegram_id=sender_telegram_id,
            recipient_telegram_id=recipient_telegram_id,
            amount=amount,
            commission=commission,
            message=message,
        )
        
        db_transfer = await self.uow.repository.balance_transfers.create(transfer)
        await self.uow.commit()
        
        logger.info(
            f"Created balance transfer record: {sender_telegram_id} -> {recipient_telegram_id}, "
            f"amount={amount}, commission={commission}"
        )
        
        return BalanceTransferDto.from_model(db_transfer)  # type: ignore[return-value]

    async def get_transfer_recipients(
        self,
        sender_telegram_id: int,
        limit: int = 20,
    ) -> list[UserDto]:
        """Получить список пользователей, которым отправитель делал переводы."""
        transfers = await self.uow.repository.balance_transfers.get_by_sender(
            sender_telegram_id=sender_telegram_id,
            limit=limit,
        )
        
        # Получаем пользователей по их ID
        recipient_ids = [t.recipient_telegram_id for t in transfers]
        if not recipient_ids:
            return []
        
        users = await self.uow.repository.users.get_by_ids(recipient_ids)
        
        # Сортируем в том же порядке, что и переводы (последние первые)
        user_map = {u.telegram_id: u for u in users}
        sorted_users = []
        for recipient_id in recipient_ids:
            if recipient_id in user_map:
                sorted_users.append(UserDto.from_model(user_map[recipient_id]))
        
        logger.debug(f"Retrieved {len(sorted_users)} transfer recipients for user {sender_telegram_id}")
        return sorted_users
