from typing import Any, Awaitable, Callable, Optional

from aiogram.types import TelegramObject
from aiogram.types import User as AiogramUser
from aiogram_dialog.api.internal import FakeUser
from dishka import AsyncContainer
from loguru import logger

from src.bot.keyboards import get_user_keyboard
from src.core.config import AppConfig
from src.core.constants import CONTAINER_KEY, IS_SUPER_DEV_KEY, USER_KEY
from src.core.enums import MiddlewareEventType, SystemNotificationType
from src.core.utils.message_payload import MessagePayload
from src.infrastructure.database.models.dto import UserDto
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
                    telegram_id=user.telegram_id
                )
                if existing_users:
                    existing_user = existing_users[0]
                    if existing_user.status in ["ACTIVE", "active"]:
                        # Пытаемся найти план по тегу
                        existing_tag = existing_user.subscription_tag
                        try:
                            matching_plan = await plan_service.get_by_tag(existing_tag)
                            # План найден, импортируем подписку
                            await subscription_service.create_imported(
                                user_id=user.telegram_id,
                                plan_id=matching_plan.id,
                                remna_subscription_tag=existing_tag,
                            )
                            logger.info(
                                f"Imported existing subscription for user {user.telegram_id} "
                                f"with tag '{existing_tag}' and plan '{matching_plan.name}'"
                            )
                        except Exception as e:
                            # План не найден, меняем тег на IMPORT
                            logger.warning(
                                f"No matching plan found for tag '{existing_tag}' "
                                f"for user {user.telegram_id}, changing tag to IMPORT"
                            )
                            await remnawave_service.remnawave.users.update_user(
                                telegram_id=user.telegram_id,
                                tag="IMPORT",
                            )
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
