from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from aiogram.types import TelegramObject
from aiogram.types import User as AiogramUser
from aiogram_dialog.api.internal import FakeUser
from dishka import AsyncContainer
from loguru import logger
from remnapy.models.users import UpdateUserRequestDto

from src.bot.keyboards import get_user_keyboard
from src.core.config import AppConfig
from src.core.constants import CONTAINER_KEY, IS_SUPER_DEV_KEY, USER_KEY
from src.core.enums import MiddlewareEventType, PlanType, SystemNotificationType
from src.core.utils.formatters import format_bytes_to_gb
from src.core.utils.message_payload import MessagePayload
from src.infrastructure.database.models.dto import (
    PlanSnapshotDto,
    SubscriptionDto,
    UserDto,
)
from src.services.notification import NotificationService
from src.services.plan import PlanService
from src.services.referral import ReferralService
from src.services.remnawave import RemnawaveService
from src.services.subscription import SubscriptionService
from src.services.user import UserService

from .base import EventTypedMiddleware


class UserMiddleware(EventTypedMiddleware):
    __event_types__ = [
        MiddlewareEventType.MESSAGE,
        MiddlewareEventType.CALLBACK_QUERY,
        MiddlewareEventType.ERROR,
        MiddlewareEventType.AIOGD_UPDATE,
        MiddlewareEventType.MY_CHAT_MEMBER,
        MiddlewareEventType.PRE_CHECKOUT_QUERY,
    ]

    async def middleware_logic(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        aiogram_user: Optional[AiogramUser] = self._get_aiogram_user(event)

        if aiogram_user is None or aiogram_user.is_bot:
            logger.warning("Terminating middleware: event from bot or missing user")
            return

        container: AsyncContainer = data[CONTAINER_KEY]
        notification_service: NotificationService = await container.get(NotificationService)
        config: AppConfig = await container.get(AppConfig)
        user_service: UserService = await container.get(UserService)
        referral_service: ReferralService = await container.get(ReferralService)
        remnawave_service: RemnawaveService = await container.get(RemnawaveService)
        plan_service: PlanService = await container.get(PlanService)
        subscription_service: SubscriptionService = await container.get(SubscriptionService)

        user: Optional[UserDto] = await user_service.get(telegram_id=aiogram_user.id)


        if user is None:
            user = await user_service.create(aiogram_user)

            # Проверяем существующую подписку в Remnawave
            try:
                existing_users = await remnawave_service.remnawave.users.get_users_by_telegram_id(
                    telegram_id=str(user.telegram_id)
                )
                if existing_users:
                    existing_user = existing_users[0]
                    existing_tag = existing_user.tag
                    logger.debug(
                        f"Found existing Remnawave user {user.telegram_id} "
                        f"with tag='{existing_tag}', status='{existing_user.status}'"
                    )
                    if existing_user.status in ["ACTIVE", "active"]:
                        # Пытаемся найти план по тегу
                        if existing_tag:
                            matching_plan = await plan_service.get_by_tag(existing_tag)
                            if matching_plan:
                                # Вычисляем duration из expire_at
                                if existing_user.expire_at:
                                    now = datetime.now(timezone.utc)
                                    time_left = existing_user.expire_at - now
                                    duration_days = max(1, time_left.days)  # Минимум 1 день
                                else:
                                    duration_days = -1  # Безлимит если нет expire_at
                                
                                # План найден, импортируем подписку
                                plan_snapshot = PlanSnapshotDto(
                                    id=matching_plan.id,
                                    name=matching_plan.name,
                                    tag=matching_plan.tag,
                                    type=matching_plan.type,
                                    traffic_limit=matching_plan.traffic_limit,
                                    device_limit=matching_plan.device_limit,
                                    duration=duration_days,
                                    traffic_limit_strategy=matching_plan.traffic_limit_strategy,
                                    internal_squads=matching_plan.internal_squads,
                                    external_squad=matching_plan.external_squad,
                                )
                                
                                imported_subscription = SubscriptionDto(
                                    user_remna_id=existing_user.uuid,
                                    status=existing_user.status,
                                    is_trial=False,
                                    traffic_limit=format_bytes_to_gb(existing_user.traffic_limit_bytes) if existing_user.traffic_limit_bytes else matching_plan.traffic_limit,
                                    device_limit=existing_user.hwid_device_limit or matching_plan.device_limit,
                                    traffic_limit_strategy=existing_user.traffic_limit_strategy or matching_plan.traffic_limit_strategy,
                                    tag=matching_plan.tag,
                                    internal_squads=matching_plan.internal_squads,
                                    external_squad=matching_plan.external_squad,
                                    expire_at=existing_user.expire_at,
                                    url=existing_user.subscription_url,
                                    plan=plan_snapshot,
                                )
                                
                                await subscription_service.create(user, imported_subscription)
                                
                                # Обновляем device_limit в Remnawave в соответствии с планом бота
                                await remnawave_service.remnawave.users.update_user(
                                    UpdateUserRequestDto(
                                        uuid=existing_user.uuid,
                                        hwid_device_limit=matching_plan.device_limit,
                                    )
                                )
                                
                                # Инвалидируем кеш пользователя чтобы загрузить актуальные данные с подпиской
                                await user_service.clear_user_cache(user.telegram_id)
                                user = await user_service.get(telegram_id=user.telegram_id)
                                data[USER_KEY] = user  # Обновляем объект user в контексте
                                
                                logger.info(
                                    f"Imported existing subscription for user {user.telegram_id} "
                                    f"with tag '{matching_plan.tag}' and plan '{matching_plan.name}', "
                                    f"updated device_limit to {matching_plan.device_limit}"
                                )
                            else:
                                # План не найден, создаём подписку с тегом IMPORT_OLDTAG
                                # и сохраняем параметры пользователя (device_limit, expire_at) из Remnawave
                                # Используем underscore вместо скобок для совместимости с валидацией Remnawave (pattern: ^[A-Z0-9_]+$)
                                
                                # Проверяем, не начинается ли тег уже с IMPORT_
                                # Если да - оставляем как есть, не меняем в Remnawave
                                if existing_tag.startswith("IMPORT_"):
                                    # Тег уже в формате IMPORT_xxx - используем его как есть
                                    import_tag_remnawave = existing_tag  # Оставляем существующий тег
                                    # Извлекаем оригинальный тег для отображения
                                    original_tag = existing_tag[7:]  # Убираем "IMPORT_" префикс
                                    import_tag_display = f"IMPORT({original_tag})"  # Для отображения в боте
                                    should_update_remnawave_tag = False
                                else:
                                    # Обычный тег - конвертируем в IMPORT_xxx
                                    import_tag_remnawave = f"IMPORT_{existing_tag}"  # Тег для Remnawave API
                                    import_tag_display = f"IMPORT({existing_tag})"  # Тег для отображения в боте
                                    should_update_remnawave_tag = True
                                
                                import_name = "Импорт"  # Название для отображения в профиле
                                
                                logger.warning(
                                    f"No matching plan found for tag '{existing_tag}' "
                                    f"for user {user.telegram_id}. Creating subscription with tag '{import_tag_display}'"
                                )
                                
                                # Вычисляем duration из expire_at пользователя
                                if existing_user.expire_at:
                                    now = datetime.now(timezone.utc)
                                    time_left = existing_user.expire_at - now
                                    duration_days = max(1, time_left.days)  # Минимум 1 день
                                else:
                                    duration_days = -1  # Безлимит если нет expire_at
                                
                                # Используем device_limit пользователя из Remnawave, по умолчанию 3
                                user_device_limit = existing_user.hwid_device_limit or 3
                                
                                # Определяем traffic_limit из данных Remnawave
                                traffic_limit_gb = format_bytes_to_gb(existing_user.traffic_limit_bytes) if existing_user.traffic_limit_bytes else -1
                                
                                # Определяем тип плана на основе данных
                                if traffic_limit_gb and traffic_limit_gb > 0 and user_device_limit and user_device_limit > 0:
                                    plan_type = PlanType.BOTH
                                elif traffic_limit_gb and traffic_limit_gb > 0:
                                    plan_type = PlanType.TRAFFIC
                                elif user_device_limit and user_device_limit > 0:
                                    plan_type = PlanType.DEVICES
                                else:
                                    plan_type = PlanType.UNLIMITED
                                
                                plan_snapshot = PlanSnapshotDto(
                                    id=0,  # Виртуальный ID для импортированного плана
                                    name=import_name,
                                    tag=import_tag_display,  # В боте храним с скобками для читаемости
                                    type=plan_type,
                                    traffic_limit=traffic_limit_gb,
                                    device_limit=user_device_limit,
                                    duration=duration_days,
                                    traffic_limit_strategy=existing_user.traffic_limit_strategy or "NO_RESET",
                                    internal_squads=[],
                                    external_squad=None,
                                )
                                
                                imported_subscription = SubscriptionDto(
                                    user_remna_id=existing_user.uuid,
                                    status=existing_user.status,
                                    is_trial=False,
                                    traffic_limit=traffic_limit_gb,
                                    device_limit=user_device_limit,
                                    traffic_limit_strategy=existing_user.traffic_limit_strategy or "NO_RESET",
                                    tag=import_tag_display,  # В боте храним с скобками
                                    internal_squads=[],
                                    external_squad=None,
                                    expire_at=existing_user.expire_at,
                                    url=existing_user.subscription_url,
                                    plan=plan_snapshot,
                                )
                                
                                await subscription_service.create(user, imported_subscription)
                                
                                # Меняем тег в панели Remnawave на IMPORT_OLDTAG только если нужно
                                if should_update_remnawave_tag:
                                    await remnawave_service.remnawave.users.update_user(
                                        UpdateUserRequestDto(
                                            uuid=existing_user.uuid,
                                            tag=import_tag_remnawave,  # Используем формат с underscore для API
                                            hwid_device_limit=user_device_limit,
                                        )
                                    )
                                else:
                                    # Тег уже IMPORT_xxx, обновляем только device_limit если нужно
                                    await remnawave_service.remnawave.users.update_user(
                                        UpdateUserRequestDto(
                                            uuid=existing_user.uuid,
                                            hwid_device_limit=user_device_limit,
                                        )
                                    )
                                
                                # Инвалидируем кеш пользователя чтобы загрузить актуальные данные с подпиской
                                await user_service.clear_user_cache(user.telegram_id)
                                user = await user_service.get(telegram_id=user.telegram_id)
                                data[USER_KEY] = user  # Обновляем объект user в контексте
                                
                                if should_update_remnawave_tag:
                                    logger.info(
                                        f"Created '{import_tag_display}' subscription for user {user.telegram_id}, "
                                        f"preserved device_limit={user_device_limit}, duration={duration_days} days, "
                                        f"Remnawave tag changed to '{import_tag_remnawave}'"
                                    )
                                else:
                                    logger.info(
                                        f"Created '{import_tag_display}' subscription for user {user.telegram_id}, "
                                        f"preserved device_limit={user_device_limit}, duration={duration_days} days, "
                                        f"Remnawave tag kept as '{import_tag_remnawave}'"
                                    )
                        else:
                            logger.debug(f"User {user.telegram_id} has no tag in Remnawave")
                    else:
                        logger.debug(f"User {user.telegram_id} is not active in Remnawave (status={existing_user.status})")
                else:
                    logger.debug(f"User {user.telegram_id} not found in Remnawave")
            except Exception as e:
                logger.error(f"Error checking existing Remnawave subscription: {e}")

            referrer = await referral_service.get_referrer_by_event(event, user.telegram_id)

            base_i18n_kwargs = {
                "user_id": str(user.telegram_id),
                "user_name": user.name,
                "username": user.username or False,
            }

            if referrer:
                referrer_i18n_kwargs = {
                    "has_referrer": True,
                    "referrer_user_id": str(referrer.telegram_id),
                    "referrer_user_name": referrer.name,
                    "referrer_username": referrer.username or False,
                }
            else:
                referrer_i18n_kwargs = {"has_referrer": False}

            await notification_service.system_notify(
                payload=MessagePayload.not_deleted(
                    i18n_key="ntf-event-new-user",
                    i18n_kwargs={**base_i18n_kwargs, **referrer_i18n_kwargs},
                    reply_markup=get_user_keyboard(user.telegram_id),
                ),
                ntf_type=SystemNotificationType.USER_REGISTERED,
            )

            if await referral_service.is_referral_event(event, user.telegram_id):
                referral_code = await referral_service.get_ref_code_by_event(event)
                logger.info(f"Registered with referral code: '{referral_code}'")

                await referral_service.handle_referral(user, referral_code)

                logger.info(
                    f"Referral processed for user '{user.telegram_id}'. "
                    f"is_invited_user will be resolved via relations."
                )

        elif not isinstance(aiogram_user, FakeUser):
            await user_service.compare_and_update(user, aiogram_user)

        await user_service.update_recent_activity(telegram_id=user.telegram_id)

        data[USER_KEY] = user
        data[IS_SUPER_DEV_KEY] = user.telegram_id == config.bot.dev_id

        return await handler(event, data)
