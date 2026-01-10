"""Задачи синхронизации данных между ботом и панелью Remnawave."""
from dishka.integrations.taskiq import FromDishka, inject
from loguru import logger

from src.core.utils.message_payload import MessagePayload
from src.infrastructure.database.models.dto import UserDto
from src.infrastructure.taskiq.broker import broker
from src.services.notification import NotificationService
from src.services.remnawave import RemnawaveService
from src.services.subscription import SubscriptionService
from src.services.user import UserService


@broker.task
@inject
async def sync_panel_to_bot_task(
    admin_telegram_id: int,
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
    remnawave_service: FromDishka[RemnawaveService],
    notification_service: FromDishka[NotificationService],
) -> None:
    """
    Синхронизация данных из панели Remnawave в бота.
    Обновляет данные подписок в боте данными из панели.
    Создает новых пользователей в боте если их нет.
    """
    logger.info(f"Starting panel to bot sync, initiated by admin {admin_telegram_id}")
    
    try:
        # Получаем всех пользователей из панели
        panel_users = await remnawave_service.get_all_users()
        
        synced_count = 0
        created_count = 0
        errors_count = 0
        
        for panel_user in panel_users:
            try:
                # Проверяем, есть ли telegram_id у пользователя панели
                if not panel_user.telegram_id:
                    continue
                    
                telegram_id = int(panel_user.telegram_id)
                
                # Пробуем найти пользователя в боте
                bot_user = await user_service.get(telegram_id)
                
                if bot_user:
                    # Пользователь есть в боте - обновляем подписку
                    subscription = await subscription_service.get_current(bot_user)
                    
                    if subscription:
                        # Обновляем данные подписки из панели
                        subscription.status = panel_user.status
                        subscription.expire_at = panel_user.expire_at
                        subscription.traffic_limit = panel_user.traffic_limit
                        subscription.device_limit = panel_user.device_limit
                        
                        await subscription_service.update(subscription)
                        synced_count += 1
                        logger.debug(f"Synced subscription for user {telegram_id} from panel")
                else:
                    # Пользователя нет в боте - создаем нового
                    new_user = UserDto(
                        telegram_id=telegram_id,
                        username=panel_user.username,
                        name=panel_user.username or f"User_{telegram_id}",
                    )
                    await user_service.create(new_user)
                    created_count += 1
                    logger.debug(f"Created user {telegram_id} from panel data")
                    
            except Exception as e:
                logger.error(f"Error processing panel user: {e}")
                errors_count += 1
        
        # Уведомляем администратора о результате
        admin = await user_service.get(admin_telegram_id)
        await notification_service.notify_user(
            user=admin,
            payload=MessagePayload(
                i18n_key="ntf-sync-completed",
                i18n_kwargs={
                    "direction": "panel_to_bot",
                    "synced": synced_count,
                    "created": created_count,
                    "errors": errors_count,
                },
            ),
        )
        
        logger.info(f"Panel to bot sync completed: synced={synced_count}, created={created_count}, errors={errors_count}")
        
    except Exception as e:
        logger.exception(f"Panel to bot sync failed: {e}")
        admin = await user_service.get(admin_telegram_id)
        await notification_service.notify_user(
            user=admin,
            payload=MessagePayload(
                i18n_key="ntf-sync-failed",
                i18n_kwargs={"error": str(e)},
            ),
        )
