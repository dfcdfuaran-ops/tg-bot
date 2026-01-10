from typing import Optional

from sqlalchemy import desc

from src.infrastructure.database.models.sql import BalanceTransfer

from .base import BaseRepository


class BalanceTransferRepository(BaseRepository):
    """Репозиторий для работы с историей переводов."""
    
    async def create(self, transfer: BalanceTransfer) -> BalanceTransfer:
        """Создать запись о переводе."""
        return await self.create_instance(transfer)
    
    async def get_by_sender(
        self,
        sender_telegram_id: int,
        limit: int = 50,
    ) -> list[BalanceTransfer]:
        """Получить историю переводов отправителя (уникальные получатели)."""
        # Получаем все переводы отправителя, сортируя по дате
        transfers = await self._get_many(
            BalanceTransfer,
            BalanceTransfer.sender_telegram_id == sender_telegram_id,
            order_by=desc(BalanceTransfer.created_at),
            limit=limit * 3,  # Берём с запасом для фильтрации уникальных
        )
        
        # Оставляем только уникальных получателей (последний перевод каждому)
        seen_recipients = set()
        unique_transfers = []
        for transfer in transfers:
            if transfer.recipient_telegram_id not in seen_recipients:
                seen_recipients.add(transfer.recipient_telegram_id)
                unique_transfers.append(transfer)
                if len(unique_transfers) >= limit:
                    break
        
        return unique_transfers
    
    async def get_unique_recipients(
        self,
        sender_telegram_id: int,
        limit: int = 20,
    ) -> list[int]:
        """Получить уникальные ID получателей переводов от отправителя."""
        transfers = await self.get_by_sender(sender_telegram_id, limit)
        return [t.recipient_telegram_id for t in transfers]
