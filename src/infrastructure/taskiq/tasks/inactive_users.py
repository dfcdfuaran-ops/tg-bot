"""Задачи проверки неактивных/неподключенных пользователей."""
from datetime import timedelta

from dishka.integrations.taskiq import FromDishka, inject
from loguru import logger

from src.bot.keyboards import get_user_keyboard
from src.core.utils.message_payload import MessagePayload
from src.core.utils.time import datetime_now
from src.infrastructure.taskiq.broker import broker
from src.services.notification import NotificationService
from src.services.settings import SettingsService
from src.services.subscription import SubscriptionService
from src.services.user import UserService


@broker.task(schedule=[{"cron": "0 * * * *"}])  # Каждый час
@inject
async def check_inactive_users_task(
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
    settings_service: FromDishka[SettingsService],
    notification_service: FromDishka[NotificationService],
) -> None:
    """
    Проверяет пользователей, которые зарегистрировались, но не подключились.
    Отправляет уведомление администратору если пользователь не подключился
    в течение N часов после регистрации.
    """
    try:
        # Получаем настройки
        settings = await settings_service.get()
        
        # Проверяем, включена ли функция
        if not settings.features.inactive_notifications.enabled:
            logger.debug("Inactive user notifications are disabled")
            return
        
        hours_threshold = settings.features.inactive_notifications.hours_threshold
        threshold_time = datetime_now() - timedelta(hours=hours_threshold)
        
        logger.info(f"Checking for inactive users (threshold: {hours_threshold} hours)")
        
        # Получаем пользователей, зарегистрированных более N часов назад
        # у которых нет активной подписки или нет подключения
        users = await user_service.get_users_without_connection(
            registered_before=threshold_time,
            notified=False,  # Еще не уведомляли об этом пользователе
        )
        
        notified_count = 0
        
        for user in users:
            try:
                # Проверяем, есть ли у пользователя подписка
                subscription = await subscription_service.get_current(user)
                
                # Если нет подписки - пользователь не подключился
                if not subscription:
                    await notification_service.system_notify(
                        payload=MessagePayload.not_deleted(
                            i18n_key="ntf-event-user-not-connected",
                            i18n_kwargs={
                                "user_id": str(user.telegram_id),
                                "user_name": user.name,
                                "username": user.username or False,
                                "hours": hours_threshold,
                                "registered_at": user.created_at.strftime("%d.%m.%Y %H:%M"),
                            },
                            reply_markup=get_user_keyboard(user.telegram_id),
                        ),
                    )
                    
                    # Помечаем пользователя как уведомленного
                    await user_service.mark_inactive_notified(user.telegram_id)
                    notified_count += 1
                    
            except Exception as e:
                logger.error(f"Error checking user {user.telegram_id}: {e}")
        
        if notified_count > 0:
            logger.info(f"Sent {notified_count} inactive user notifications")
            
    except Exception as e:
        logger.exception(f"Check inactive users task failed: {e}")
