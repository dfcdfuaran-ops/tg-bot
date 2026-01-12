"""Задачи синхронизации данных между ботом и панелью Remnawave."""
from dishka.integrations.taskiq import FromDishka, inject
from loguru import logger
from remnapy import RemnawaveSDK

from src.core.utils.time import datetime_now
from src.infrastructure.taskiq.broker import broker
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
) -> dict | None:
    """
    Синхронизация данных из панели Remnawave в бота.
    Создает новых пользователей в боте если их нет.
    Обновляет данные подписок в боте данными из панели.
    
    Возвращает dict с результатами синхронизации.
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
        
        for panel_user in all_panel_users:
            try:
                # Проверяем, есть ли telegram_id у пользователя панели
                if not panel_user.telegram_id:
                    skipped_count += 1
                    logger.debug(f"Skipping panel user {panel_user.uuid} - no telegram_id")
                    continue
                    
                telegram_id = int(panel_user.telegram_id)
                
                # Проверяем, есть ли пользователь в боте
                bot_user = await user_service.get(telegram_id)
                
                if bot_user:
                    # Обновляем имя и username пользователя из панели
                    # description содержит "name: Имя\nusername: @username"
                    new_name = str(panel_user.telegram_id)
                    new_username = None
                    if panel_user.description:
                        # Извлекаем имя и username из description
                        for line in panel_user.description.split('\n'):
                            if line.startswith('name:'):
                                extracted_name = line.replace('name:', '').strip()
                                if extracted_name:
                                    new_name = extracted_name
                            elif line.startswith('username:'):
                                extracted_username = line.replace('username:', '').strip()
                                if extracted_username:
                                    new_username = extracted_username
                    
                    needs_update = False
                    if bot_user.name != new_name:
                        bot_user.name = new_name
                        needs_update = True
                    if bot_user.username != new_username:
                        bot_user.username = new_username
                        needs_update = True
                    
                    if needs_update:
                        await user_service.update(bot_user)
                        logger.debug(f"Updated user {telegram_id}: name={new_name}, username={new_username}")
                    
                    # Пользователь существует - синхронизируем
                    await remnawave_service.sync_user(panel_user, creating=False)
                    synced_count += 1
                    logger.debug(f"Synced user {telegram_id}")
                else:
                    # Создаём нового пользователя и синхронизируем
                    await remnawave_service.sync_user(panel_user, creating=True)
                    created_count += 1
                    logger.debug(f"Created user {telegram_id}")
                    
            except Exception as e:
                logger.error(f"Error processing panel user {panel_user.uuid}: {e}")
                logger.exception(e)
                errors_count += 1
        
        logger.info(
            f"Panel to bot sync completed: total={len(all_panel_users)}, "
            f"created={created_count}, synced={synced_count}, "
            f"skipped={skipped_count}, errors={errors_count}"
        )
        
        return {
            "total_panel_users": len(all_panel_users),
            "created": created_count,
            "synced": synced_count,
            "skipped": skipped_count,
            "errors": errors_count,
        }
        
    except Exception as e:
        logger.exception(f"Panel to bot sync failed: {e}")
        raise
