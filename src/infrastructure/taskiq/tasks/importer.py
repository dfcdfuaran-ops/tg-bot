import traceback
from uuid import UUID

from dishka.integrations.taskiq import FromDishka, inject
from loguru import logger
from remnapy import RemnawaveSDK
from remnapy.exceptions import BadRequestError
from remnapy.models import CreateUserRequestDto, UserResponseDto, UpdateUserRequestDto

from src.core.config import AppConfig
from src.core.storage.keys import SyncRunningKey
from src.core.utils.formatters import format_device_count, format_gb_to_bytes
from src.core.utils.message_payload import MessagePayload
from src.bot.keyboards import get_user_keyboard
from src.infrastructure.redis.repository import RedisRepository
from src.infrastructure.taskiq.broker import broker
from src.services.notification import NotificationService
from src.services.plan import PlanService
from src.services.remnawave import RemnawaveService
from src.services.subscription import SubscriptionService
from src.services.user import UserService


@broker.task(retry_on_error=False)
@inject
async def import_exported_users_task(
    imported_users: list[dict],
    active_internal_squads: list[UUID],
    remnawave: FromDishka[RemnawaveSDK],
) -> tuple[int, int]:
    logger.info(f"Starting import of '{len(imported_users)}' users")

    success_count = 0
    failed_count = 0

    for user in imported_users:
        try:
            username = user["username"]
            created_user = CreateUserRequestDto.model_validate(user)
            created_user.active_internal_squads = active_internal_squads
            await remnawave.users.create_user(created_user)
            success_count += 1
        except BadRequestError as error:
            logger.warning(f"User '{username}' already exists, skipping. Error: {error}")
            failed_count += 1

        except Exception as exception:
            logger.exception(f"Failed to create user '{username}' exception: {exception}")
            failed_count += 1

    logger.info(f"Import completed: '{success_count}' successful, '{failed_count}' failed")
    return success_count, failed_count


@broker.task(retry_on_error=False)
@inject
async def sync_all_users_from_panel_task(
    redis_repository: FromDishka[RedisRepository],
    remnawave: FromDishka[RemnawaveSDK],
    remnawave_service: FromDishka[RemnawaveService],
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
) -> dict[str, int]:
    key = SyncRunningKey()
    all_remna_users: list[UserResponseDto] = []
    start = 0
    size = 50

    stats = await remnawave.system.get_stats()
    total_users = stats.users.total_users

    for start in range(0, total_users, size):
        response = await remnawave.users.get_all_users(start=start, size=size)
        if not response.users:
            break

        all_remna_users.extend(response.users)
        start += len(response.users)

        if len(response.users) < size:
            break

    bot_users = await user_service.get_all()
    bot_users_map = {user.telegram_id: user for user in bot_users}

    logger.info(f"Total users in panel: '{len(all_remna_users)}'")
    logger.info(f"Total users in bot: '{len(bot_users)}'")

    added_users = 0
    added_subscription = 0
    updated = 0
    errors = 0
    missing_telegram = 0

    try:
        for remna_user in all_remna_users:
            try:
                if not remna_user.telegram_id:
                    missing_telegram += 1
                    continue

                user = bot_users_map.get(remna_user.telegram_id)

                if not user:
                    await remnawave_service.sync_user(remna_user)
                    added_users += 1
                else:
                    current_subscription = await subscription_service.get_current(user.telegram_id)
                    if not current_subscription:
                        await remnawave_service.sync_user(remna_user)
                        added_subscription += 1
                    else:
                        await remnawave_service.sync_user(remna_user)
                        updated += 1

            except Exception as exception:
                logger.exception(
                    f"Error syncing RemnaUser '{remna_user.telegram_id}' exception: {exception}"
                )
                errors += 1

        result = {
            "total_panel_users": len(all_remna_users),
            "total_bot_users": len(bot_users),
            "added_users": added_users,
            "added_subscription": added_subscription,
            "updated": updated,
            "errors": errors,
            "missing_telegram": missing_telegram,
        }

        logger.info(f"Sync users summary: '{result}'")
        return result
    finally:
        await redis_repository.delete(key)


@broker.task(retry_on_error=False)
@inject
async def sync_bot_to_panel_task(
    config: FromDishka[AppConfig],
    remnawave: FromDishka[RemnawaveSDK],
    remnawave_service: FromDishka[RemnawaveService],
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
    plan_service: FromDishka[PlanService],
    notification_service: FromDishka[NotificationService],
) -> dict[str, int]:
    """
    Синхронизирует данные пользователей ИЗ бота В панель Remnawave.
    - Использует первый доступный squad из панели для всех планов
    - Создаёт новых пользователей в панели если их нет
    - Обновляет существующих с приоритетом данных из бота
    - Создаёт/обновляет подписки пользователей в панели
    """
    logger.info("Starting sync from bot to Remnawave panel")
    
    # ========== ШАГ 1: Получение доступных squad'ов из панели ==========
    logger.info("Step 1: Getting available squads from Remnawave panel")
    
    # Получаем все squad из панели
    try:
        panel_squads_response = await remnawave.internal_squads.get_internal_squads()
        if panel_squads_response and panel_squads_response.internal_squads:
            first_squad = panel_squads_response.internal_squads[0]
            logger.info(
                f"Found {len(panel_squads_response.internal_squads)} internal squads in panel. "
                f"Will use first squad: '{first_squad.name}' ({first_squad.uuid})"
            )
            
            # Собираем множество валидных squad UUID для валидации
            valid_squad_uuids = {squad.uuid for squad in panel_squads_response.internal_squads}
            
            # ========== ШАГ 1.5: Синхронизация internal_squads планов ==========
            logger.info("Step 1.5: Syncing plans internal_squads with panel")
            plans_sync_result = await plan_service.sync_plans_squads(
                valid_squad_uuids=valid_squad_uuids,
                default_squad_uuid=first_squad.uuid
            )
            logger.info(
                f"Plans squads sync completed: {plans_sync_result['updated']} updated, "
                f"{plans_sync_result['unchanged']} unchanged"
            )
        else:
            logger.error("No internal squads found in panel - cannot sync users")
            return {
                "total_bot_users": 0,
                "created": 0,
                "updated": 0,
                "skipped": 0,
                "errors": 0,
                "error_users": {},
                "skipped_users": [],
            }
    except Exception as e:
        logger.error(f"Failed to get squads from panel: {e}")
        return {
            "total_bot_users": 0,
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "error_users": {},
            "skipped_users": [],
        }
    
    # ========== ШАГ 2: Синхронизация пользователей ==========
    logger.info("Step 2: Syncing users from bot to Remnawave panel")
    
    # Получаем всех пользователей бота с подписками
    bot_users = await user_service.get_all()
    logger.info(f"Total users in bot: '{len(bot_users)}'")
    
    created = 0
    updated = 0
    errors = 0
    skipped = 0
    
    error_users: dict[str, str] = {}  # {user_info: error_reason}
    skipped_users: list[str] = []
    
    for user in bot_users:
        try:
            # Получаем текущую подписку пользователя
            subscription = await subscription_service.get_current(user.telegram_id)
            
            if not subscription:
                logger.debug(
                    f"⊘ User skipped (no subscription): {user.name} (telegram_id: {user.telegram_id})"
                )
                skipped_users.append(f"{user.name} ({user.telegram_id})")
                skipped += 1
                continue
            
            # Проверяем, есть ли пользователь в панели Remnawave
            try:
                panel_users = await remnawave.users.get_users_by_telegram_id(
                    telegram_id=str(user.telegram_id)
                )
            except Exception as e:
                logger.warning(f"Error getting user from panel: {e}")
                panel_users = []
            
            if panel_users:
                # Пользователь есть в панели - проверяем short_uuid
                panel_user = panel_users[0]
                logger.info(f"User '{user.telegram_id}' found in panel, checking short_uuid...")
                
                # Проверяем, совпадает ли short_uuid
                need_recreate = False
                desired_short_uuid = None
                
                if subscription and subscription.url:
                    try:
                        desired_short_uuid = subscription.url.rstrip('/').split('/')[-1]
                        panel_short_uuid = panel_user.short_uuid
                        
                        logger.info(
                            f"DEBUG: Comparing short_uuid for user {user.telegram_id}: "
                            f"panel='{panel_short_uuid}', backup='{desired_short_uuid}', "
                            f"subscription.url='{subscription.url}'"
                        )
                        
                        if panel_short_uuid != desired_short_uuid:
                            logger.warning(
                                f"⚠️ short_uuid MISMATCH for user {user.telegram_id}: "
                                f"panel={panel_short_uuid}, backup={desired_short_uuid}. "
                                f"Will use REVOKE to update short_uuid."
                            )
                            need_recreate = True
                        else:
                            logger.debug(f"✓ short_uuid matches: {desired_short_uuid}")
                    except Exception as ex:
                        logger.warning(f"Failed to extract short_uuid from URL '{subscription.url}': {ex}")
                        traceback_str = traceback.format_exc()
                        logger.warning(f"Traceback: {traceback_str}")
                
                if need_recreate and desired_short_uuid:
                    # API revoke не поддерживает установку custom short_uuid - он всегда генерирует новый
                    # Поэтому используем DELETE + CREATE с указанием short_uuid
                    try:
                        logger.info(
                            f"🔄 Recreating user {panel_user.uuid} to preserve short_uuid "
                            f"from backup: '{desired_short_uuid}' (current in panel: '{panel_user.short_uuid}')"
                        )
                        
                        # Сохраняем данные пользователя перед удалением
                        old_uuid = panel_user.uuid
                        old_expire_at = panel_user.expire_at
                        old_status = panel_user.status
                        old_traffic_limit_bytes = panel_user.traffic_limit_bytes
                        old_traffic_limit_strategy = panel_user.traffic_limit_strategy
                        old_description = panel_user.description
                        old_tag = panel_user.tag
                        old_hwid_device_limit = panel_user.hwid_device_limit
                        old_active_squads = [squad.uuid for squad in (panel_user.active_internal_squads or [])]
                        
                        # Удаляем пользователя
                        logger.info(f"Deleting user {old_uuid} from panel...")
                        await remnawave.users.delete_user(uuid=old_uuid)
                        logger.info(f"✓ User {old_uuid} deleted successfully")
                        
                        # Создаем пользователя заново с тем же short_uuid из бэкапа
                        create_body = CreateUserRequestDto(
                            username=str(user.telegram_id),
                            telegram_id=user.telegram_id,
                            expire_at=old_expire_at,
                            status=old_status,
                            traffic_limit_bytes=old_traffic_limit_bytes,
                            traffic_limit_strategy=old_traffic_limit_strategy,
                            description=old_description,
                            tag=old_tag,
                            hwid_device_limit=old_hwid_device_limit,
                            active_internal_squads=old_active_squads if old_active_squads else None,
                            short_uuid=desired_short_uuid,  # КРИТИЧЕСКИ ВАЖНО: устанавливаем short_uuid из бэкапа
                        )
                        
                        logger.info(f"Creating new user with short_uuid='{desired_short_uuid}'...")
                        created_user = await remnawave.users.create_user(body=create_body)
                        
                        if created_user and created_user.uuid:
                            # Проверяем, что short_uuid действительно установлен правильно
                            if created_user.short_uuid != desired_short_uuid:
                                logger.error(
                                    f"❌ CRITICAL: After create, short_uuid didn't match! "
                                    f"Expected: '{desired_short_uuid}', Got: '{created_user.short_uuid}'"
                                )
                            else:
                                logger.info(f"✓ Verified: short_uuid correctly set to '{created_user.short_uuid}'")
                            
                            # Обновляем subscription с новыми данными из панели
                            subscription.user_remna_id = created_user.uuid
                            # URL остаётся прежним из бэкапа, так как short_uuid теперь совпадает
                            await subscription_service.update(subscription)
                            
                            updated += 1
                            logger.info(
                                f"✓ User RECREATED with preserved short_uuid: {user.name} "
                                f"(telegram_id: {user.telegram_id}, new_uuid: {created_user.uuid}, "
                                f"short_uuid: {created_user.short_uuid})"
                            )
                        else:
                            error_msg = "create_user returned None or empty response after delete"
                            logger.error(
                                f"✗ Failed to recreate user: {user.name} (telegram_id: {user.telegram_id}). "
                                f"Error: {error_msg}"
                            )
                            error_users[f"{user.name} ({user.telegram_id})"] = error_msg
                            errors += 1
                    except Exception as e:
                        error_msg = f"{type(e).__name__}: {str(e)}"
                        traceback_str = traceback.format_exc()
                        if "Validation failed" in str(e) or "validation" in str(e).lower():
                            logger.debug(
                                f"⊘ User skipped (validation error - likely inactive subscription): "
                                f"{user.name} (telegram_id: {user.telegram_id})"
                            )
                        else:
                            logger.error(
                                f"✗ Failed to recreate user with short_uuid: {user.name} (telegram_id: {user.telegram_id}). "
                                f"Error: {error_msg}\nTraceback:\n{traceback_str}"
                            )
                            error_users[f"{user.name} ({user.telegram_id})"] = error_msg
                            errors += 1
                            
                            # Отправляем ошибку в файл через notification_service
                            await notification_service.error_notify(
                                error_id=user.telegram_id,
                                traceback_str=traceback_str,
                                payload=MessagePayload.not_deleted(
                                    i18n_key="ntf-event-error",
                                    i18n_kwargs={
                                        "user": True,
                                        "user_id": str(user.telegram_id),
                                        "user_name": user.name,
                                        "username": user.username or False,
                                        "error": f"Sync revoke error: {error_msg}",
                                    },
                                    reply_markup=get_user_keyboard(user.telegram_id),
                                ),
                            )
                else:
                    # short_uuid совпадает или нет URL - просто обновляем
                    try:
                        await remnawave_service.updated_user(
                            user=user,
                            uuid=panel_user.uuid,
                            subscription=subscription,
                        )
                        updated += 1
                        logger.info(
                            f"✓ User updated: {user.name} (telegram_id: {user.telegram_id}, "
                            f"panel_uuid: {panel_user.uuid})"
                        )
                    except Exception as e:
                        # Check if error is due to inactive subscription (Validation failed)
                        error_msg = f"{type(e).__name__}: {str(e)}"
                        traceback_str = traceback.format_exc()
                        if "Validation failed" in str(e) or "validation" in str(e).lower():
                            # This is likely an inactive subscription - skip silently without counting
                            logger.debug(
                                f"⊘ User skipped (validation error - likely inactive subscription): "
                                f"{user.name} (telegram_id: {user.telegram_id})"
                            )
                        else:
                            # Real error
                            logger.error(
                                f"✗ Failed to update user: {user.name} (telegram_id: {user.telegram_id}). "
                                f"Error: {error_msg}\nTraceback:\n{traceback_str}"
                            )
                            error_users[f"{user.name} ({user.telegram_id})"] = error_msg
                            errors += 1
                            
                            # Отправляем ошибку в файл через notification_service
                            await notification_service.error_notify(
                                error_id=user.telegram_id,
                                traceback_str=traceback_str,
                                payload=MessagePayload.not_deleted(
                                    i18n_key="ntf-event-error",
                                    i18n_kwargs={
                                        "user": True,
                                        "user_id": str(user.telegram_id),
                                        "user_name": user.name,
                                        "username": user.username or False,
                                        "error": f"Sync update error: {error_msg}",
                                    },
                                    reply_markup=get_user_keyboard(user.telegram_id),
                                ),
                            )
            else:
                # Пользователя нет в панели - СОЗДАЁМ его с принудительной создачей подписки
                logger.info(
                    f"User '{user.name}' (telegram_id: {user.telegram_id}) not found in panel, "
                    f"creating with short_uuid from URL..."
                )
                try:
                    new_user = await remnawave_service.create_user(
                        user=user,
                        subscription=subscription,
                        force=True,
                    )
                    
                    if new_user:
                        # Обновляем remna_id в подписке если он не совпадает
                        if subscription.user_remna_id != new_user.uuid:
                            subscription.user_remna_id = new_user.uuid
                            await subscription_service.update(subscription)
                        
                        created += 1
                        logger.info(
                            f"✓ User created: {user.name} (telegram_id: {user.telegram_id}, "
                            f"panel_uuid: {new_user.uuid}, short_uuid: {new_user.short_uuid})"
                        )
                    else:
                        logger.warning(
                            f"✗ Failed to create user: {user.name} (telegram_id: {user.telegram_id}). "
                            f"create_user returned None"
                        )
                        error_users[f"{user.name} ({user.telegram_id})"] = "create_user returned None"
                        errors += 1
                except Exception as e:
                    # Check if error is due to inactive subscription (Validation failed)
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    traceback_str = traceback.format_exc()
                    if "Validation failed" in str(e) or "validation" in str(e).lower():
                        # This is likely an inactive subscription - skip silently without counting
                        logger.debug(
                            f"⊘ User skipped (validation error - likely inactive subscription): "
                            f"{user.name} (telegram_id: {user.telegram_id})"
                        )
                    else:
                        # Real error
                        logger.error(
                            f"✗ Failed to create user: {user.name} (telegram_id: {user.telegram_id}). "
                            f"Error: {error_msg}\nTraceback:\n{traceback_str}"
                        )
                        error_users[f"{user.name} ({user.telegram_id})"] = error_msg
                        errors += 1
                        
                        # Отправляем ошибку в файл через notification_service
                        await notification_service.error_notify(
                            error_id=user.telegram_id,
                            traceback_str=traceback_str,
                            payload=MessagePayload.not_deleted(
                                i18n_key="ntf-event-error",
                                i18n_kwargs={
                                    "user": True,
                                    "user_id": str(user.telegram_id),
                                    "user_name": user.name,
                                    "username": user.username or False,
                                    "error": f"Sync create error: {error_msg}",
                                },
                                reply_markup=get_user_keyboard(user.telegram_id),
                            ),
                        )
            
        except Exception as exception:
            error_msg = f"{type(exception).__name__}: {str(exception)}"
            traceback_str = traceback.format_exc()
            user_name = user.name if hasattr(user, 'name') else 'Unknown'
            user_telegram_id = user.telegram_id if hasattr(user, 'telegram_id') else 'Unknown'
            logger.exception(
                f"✗ Error syncing user: {user_name} "
                f"(telegram_id: {user_telegram_id}). "
                f"Exception: {error_msg}\nTraceback:\n{traceback_str}"
            )
            error_users[f"{user_name} ({user_telegram_id})"] = error_msg
            errors += 1
            
            # Отправляем ошибку в файл через notification_service
            if hasattr(user, 'telegram_id'):
                await notification_service.error_notify(
                    error_id=user.telegram_id,
                    traceback_str=traceback_str,
                    payload=MessagePayload.not_deleted(
                        i18n_key="ntf-event-error",
                        i18n_kwargs={
                            "user": True,
                            "user_id": str(user.telegram_id),
                            "user_name": user_name,
                            "username": getattr(user, 'username', None) or False,
                            "error": f"Sync error: {error_msg}",
                        },
                        reply_markup=get_user_keyboard(user.telegram_id),
                    ),
                )
    
    result = {
        "total_bot_users": len(bot_users),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "error_users": error_users,
        "skipped_users": skipped_users,
    }
    
    logger.info(f"Sync bot to panel completed: {result}")
    return result

