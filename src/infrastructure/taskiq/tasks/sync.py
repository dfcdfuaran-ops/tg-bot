"""Задачи синхронизации данных между ботом и панелью Remnawave."""
from dishka.integrations.taskiq import FromDishka, inject
from loguru import logger
from remnapy import RemnawaveSDK

from src.core.enums import SubscriptionStatus
from src.core.utils.formatters import format_limits_to_plan_type
from src.core.utils.message_payload import MessagePayload
from src.core.utils.time import datetime_now
from src.infrastructure.database.models.dto import PlanSnapshotDto, SubscriptionDto, UserDto
from src.infrastructure.taskiq.broker import broker
from src.services.notification import NotificationService
from src.services.plan import PlanService
from src.services.remnawave import RemnawaveService
from src.services.subscription import SubscriptionService
from src.services.user import UserService


@broker.task
@inject
async def sync_panel_to_bot_task(
    admin_telegram_id: int,
    remnawave: FromDishka[RemnawaveSDK],
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
    plan_service: FromDishka[PlanService],
    remnawave_service: FromDishka[RemnawaveService],
    notification_service: FromDishka[NotificationService],
) -> None:
    """
    Синхронизация данных из панели Remnawave в бота.
    Создает новых пользователей в боте если их нет.
    Обновляет данные подписок в боте данными из панели.
    """
    logger.info(f"Starting panel to bot sync, initiated by admin {admin_telegram_id}")
    
    try:
        # Получаем всех пользователей из панели с пагинацией
        all_panel_users = []
        start = 0
        size = 50
        
        # Сначала получаем общую статистику чтобы узнать количество пользователей
        stats = await remnawave.system.get_stats()
        total_users = stats.users.total_users
        
        logger.info(f"Total users in panel: {total_users}")
        
        # Получаем всех пользователей с пагинацией
        for start in range(0, total_users, size):
            response = await remnawave.users.get_all_users(start=start, size=size)
            if not response.users:
                break
            
            all_panel_users.extend(response.users)
            
            if len(response.users) < size:
                break
        
        logger.info(f"Retrieved {len(all_panel_users)} users from panel")
        
        synced_count = 0
        created_count = 0
        errors_count = 0
        skipped_count = 0
        
        for panel_user_short in all_panel_users:
            try:
                # Получаем полные данные пользователя (с traffic_limit, device_limit и т.д.)
                panel_user = await remnawave.users.get_user(panel_user_short.uuid)
                
                # Проверяем, есть ли telegram_id у пользователя панели
                if not panel_user.telegram_id:
                    skipped_count += 1
                    logger.debug(f"Skipping panel user {panel_user.uuid} - no telegram_id")
                    continue
                    
                telegram_id = int(panel_user.telegram_id)
                
                # Пробуем найти пользователя в боте
                bot_user = await user_service.get(telegram_id)
                
                if bot_user:
                    # Пользователь есть в боте - обновляем/создаём подписку
                    subscription = await subscription_service.get_current(bot_user)
                    
                    if subscription:
                        # Обновляем данные подписки из панели
                        subscription.user_remna_id = panel_user.uuid
                        subscription.url = panel_user.subscription_url
                        subscription.status = panel_user.status
                        subscription.expire_at = panel_user.expire_at
                        subscription.traffic_limit = panel_user.traffic_limit
                        subscription.device_limit = panel_user.device_limit
                        subscription.tag = panel_user.tag
                        subscription.internal_squads = panel_user.internal_squads
                        subscription.external_squad = panel_user.external_squad
                        
                        await subscription_service.update(subscription)
                        synced_count += 1
                        logger.debug(f"Updated subscription for user {telegram_id} from panel")
                    else:
                        # Создаём новую подписку для существующего пользователя
                        # Ищем план по тегу, если есть
                        plan = None
                        if panel_user.tag:
                            plan = await plan_service.get_by_tag(panel_user.tag)
                        
                        # Если план не найден, создаём временный
                        if not plan:
                            plan = PlanSnapshotDto(
                                id=0,
                                name=f"IMPORTED_{panel_user.tag or 'UNKNOWN'}",
                                tag=panel_user.tag or "IMPORTED",
                                type=format_limits_to_plan_type(
                                    traffic=panel_user.traffic_limit,
                                    devices=panel_user.device_limit,
                                ),
                                traffic_limit=panel_user.traffic_limit,
                                device_limit=panel_user.device_limit,
                                duration=-1,
                                traffic_limit_strategy=panel_user.traffic_limit_strategy,
                                internal_squads=panel_user.internal_squads,
                                external_squad=panel_user.external_squad,
                            )
                        
                        expired = panel_user.expire_at and panel_user.expire_at < datetime_now()
                        status = SubscriptionStatus.EXPIRED if expired else panel_user.status
                        
                        new_subscription = SubscriptionDto(
                            user_remna_id=panel_user.uuid,
                            status=status,
                            is_trial=False,
                            traffic_limit=panel_user.traffic_limit,
                            device_limit=panel_user.device_limit,
                            traffic_limit_strategy=panel_user.traffic_limit_strategy,
                            tag=panel_user.tag,
                            internal_squads=panel_user.internal_squads,
                            external_squad=panel_user.external_squad,
                            expire_at=panel_user.expire_at,
                            url=panel_user.subscription_url,
                            plan=plan,
                        )
                        
                        await subscription_service.create(bot_user, new_subscription)
                        synced_count += 1
                        logger.debug(f"Created subscription for existing user {telegram_id} from panel")
                else:
                    # Пользователя нет в боте - создаем нового с подпиской
                    created_user = await user_service.create_from_panel(panel_user)
                    
                    # Ищем план по тегу
                    plan = None
                    if panel_user.tag:
                        plan = await plan_service.get_by_tag(panel_user.tag)
                    
                    # Если план не найден, создаём временный
                    if not plan:
                        plan = PlanSnapshotDto(
                            id=0,
                            name=f"IMPORTED_{panel_user.tag or 'UNKNOWN'}",
                            tag=panel_user.tag or "IMPORTED",
                            type=format_limits_to_plan_type(
                                traffic=panel_user.traffic_limit,
                                devices=panel_user.device_limit,
                            ),
                            traffic_limit=panel_user.traffic_limit,
                            device_limit=panel_user.device_limit,
                            duration=-1,
                            traffic_limit_strategy=panel_user.traffic_limit_strategy,
                            internal_squads=panel_user.internal_squads,
                            external_squad=panel_user.external_squad,
                        )
                    
                    expired = panel_user.expire_at and panel_user.expire_at < datetime_now()
                    status = SubscriptionStatus.EXPIRED if expired else panel_user.status
                    
                    new_subscription = SubscriptionDto(
                        user_remna_id=panel_user.uuid,
                        status=status,
                        is_trial=False,
                        traffic_limit=panel_user.traffic_limit,
                        device_limit=panel_user.device_limit,
                        traffic_limit_strategy=panel_user.traffic_limit_strategy,
                        tag=panel_user.tag,
                        internal_squads=panel_user.internal_squads,
                        external_squad=panel_user.external_squad,
                        expire_at=panel_user.expire_at,
                        url=panel_user.subscription_url,
                        plan=plan,
                    )
                    
                    await subscription_service.create(created_user, new_subscription)
                    created_count += 1
                    logger.debug(f"Created user {telegram_id} with subscription from panel data")
                    
            except Exception as e:
                logger.error(f"Error processing panel user {panel_user_short.uuid}: {e}")
                logger.exception(e)
                errors_count += 1
        
        # Уведомляем администратора о результате
        admin = await user_service.get(admin_telegram_id)
        await notification_service.notify_user(
            user=admin,
            payload=MessagePayload(
                i18n_key="ntf-sync-panel-to-bot-completed",
                i18n_kwargs={
                    "total_panel_users": len(all_panel_users),
                    "created": created_count,
                    "synced": synced_count,
                    "skipped": skipped_count,
                    "errors": errors_count,
                },
            ),
        )
        
        logger.info(
            f"Panel to bot sync completed: total={len(all_panel_users)}, "
            f"created={created_count}, synced={synced_count}, "
            f"skipped={skipped_count}, errors={errors_count}"
        )
        
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
