from datetime import timedelta
from typing import Optional, Union
from uuid import UUID

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager, ShowMode, StartMode, SubManager
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Select
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from fluentogram import TranslatorRunner
from loguru import logger
from remnapy import RemnawaveSDK
from remnapy.exceptions import NotFoundError

from src.bot.keyboards import get_contact_support_keyboard
from src.bot.states import DashboardUser
from src.core.config import AppConfig
from src.core.constants import USER_KEY
from src.core.enums import SubscriptionStatus, UserRole
from src.core.utils.formatters import format_user_log as log
from src.core.utils.message_payload import MessagePayload
from src.core.utils.time import datetime_now
from src.core.utils.validators import is_double_click, parse_int
from src.infrastructure.database.models.dto import UserDto
from src.infrastructure.database.models.dto.plan import PlanSnapshotDto
from src.infrastructure.database.models.dto.subscription import (
    RemnaSubscriptionDto,
    SubscriptionDto,
)
from src.infrastructure.taskiq.tasks.redirects import redirect_to_main_menu_task
from src.services.notification import NotificationService
from src.services.plan import PlanService
from src.services.referral import ReferralService
from src.services.remnawave import RemnawaveService
from src.services.subscription import SubscriptionService
from src.services.transaction import TransactionService
from src.services.user import UserService


async def start_user_window(
    manager: Union[DialogManager, SubManager],
    target_telegram_id: int,
    source_state: Optional[str] = None,
) -> None:
    await manager.start(
        state=DashboardUser.MAIN,
        data={
            "target_telegram_id": target_telegram_id,
            "source_state": source_state,
        },
        mode=StartMode.RESET_STACK,
    )


async def on_back_to_source(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Return to the source state from which user window was opened."""
    from src.bot.states import DashboardUsers
    
    start_data = dialog_manager.start_data or {}
    source_state = start_data.get("source_state")
    
    # Map source state strings to actual states
    state_map = {
        "recent_registered": DashboardUsers.RECENT_REGISTERED,
        "recent_activity": DashboardUsers.RECENT_ACTIVITY,
        "search_results": DashboardUsers.SEARCH_RESULTS,
        "blacklist": DashboardUsers.BLACKLIST,
        "search": DashboardUsers.SEARCH,
    }
    
    target_state = state_map.get(source_state, DashboardUsers.MAIN)
    await dialog_manager.start(state=target_state, mode=StartMode.RESET_STACK)


@inject
async def on_block_toggle(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    blocked = not target_user.is_blocked
    await user_service.set_block(user=target_user, blocked=blocked)
    await redirect_to_main_menu_task.kiq(target_user.telegram_id)
    logger.info(f"{log(user)} {'Blocked' if blocked else 'Unblocked'} {log(target_user)}")


@inject
async def on_role_select(
    callback: CallbackQuery,
    widget: Select[UserRole],
    dialog_manager: DialogManager,
    selected_role: UserRole,
) -> None:
    """Сохраняем выбранную роль в dialog_data для отложенного применения."""
    dialog_manager.dialog_data["pending_role"] = selected_role
    await callback.answer()


@inject
async def on_cancel_role_change(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отменить изменение роли и вернуться назад."""
    dialog_manager.dialog_data.pop("pending_role", None)
    await dialog_manager.switch_to(state=DashboardUser.MAIN)


@inject
async def on_accept_role_change(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
) -> None:
    """Принять изменение роли и вернуться назад."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    pending_role = dialog_manager.dialog_data.pop("pending_role", None)
    
    if pending_role is not None:
        target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
        target_user = await user_service.get(telegram_id=target_telegram_id)

        if not target_user:
            raise ValueError(f"User '{target_telegram_id}' not found")

        # Преобразуем строку в UserRole если это необходимо
        if isinstance(pending_role, str):
            pending_role = UserRole(pending_role)

        await user_service.set_role(user=target_user, role=pending_role)
        await redirect_to_main_menu_task.kiq(target_user.telegram_id)
        logger.info(f"{log(user)} Changed role to '{pending_role.name}' for {log(target_user)}")
    
    await dialog_manager.switch_to(state=DashboardUser.MAIN)


@inject
async def on_current_subscription(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    await dialog_manager.switch_to(state=DashboardUser.SUBSCRIPTION)


@inject
async def on_active_toggle(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    subscription_service: FromDishka[SubscriptionService],
    remnawave: FromDishka[RemnawaveSDK],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    subscription = await subscription_service.get_current(target_telegram_id)

    if not subscription:
        raise ValueError(f"Current subscription for user '{target_telegram_id}' not found")

    new_status = (
        SubscriptionStatus.DISABLED if subscription.is_active else SubscriptionStatus.ACTIVE
    )

    remnawave_toggle_status = (
        remnawave.users.disable_user if subscription.is_active else remnawave.users.enable_user
    )

    await remnawave_toggle_status(subscription.user_remna_id)
    subscription.status = new_status
    await subscription_service.update(subscription)
    logger.info(
        f"{log(user)} Toggled subscription status to '{new_status}' for '{target_telegram_id}'"
    )


@inject
async def on_subscription_delete(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
    remnawave_service: FromDishka[RemnawaveService],
    notification_service: FromDishka[NotificationService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    subscription = await subscription_service.get_current(target_telegram_id)

    if not subscription:
        raise ValueError(f"Current subscription for user '{target_telegram_id}' not found")

    if is_double_click(dialog_manager, key="subscription_delete_confirm", cooldown=10):
        subscription.status = SubscriptionStatus.DELETED
        await subscription_service.update(subscription)
        await user_service.delete_current_subscription(target_telegram_id)
        await remnawave_service.delete_user(target_user)
        logger.info(f"{log(user)} Deleted subscription for user '{target_telegram_id}'")
        await dialog_manager.switch_to(state=DashboardUser.MAIN)
        return

    await notification_service.notify_user(
        user=user,
        payload=MessagePayload(i18n_key="ntf-double-click-confirm"),
    )
    logger.debug(
        f"{log(user)} Waiting for confirmation to delete "
        f"subscription for user '{target_telegram_id}'"
    )


@inject
async def on_devices(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    remnawave_service: FromDishka[RemnawaveService],
    notification_service: FromDishka[NotificationService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    devices = await remnawave_service.get_devices_user(target_user)

    if not devices:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-user-devices-empty"),
        )
        return

    await dialog_manager.switch_to(state=DashboardUser.DEVICES_LIST)


@inject
async def on_device_delete(
    callback: CallbackQuery,
    widget: Button,
    sub_manager: SubManager,
    user_service: FromDishka[UserService],
    remnawave_service: FromDishka[RemnawaveService],
) -> None:
    await sub_manager.load_data()
    selected_short_hwid = sub_manager.item_id
    hwid_map = sub_manager.dialog_data.get("hwid_map")

    if not hwid_map:
        raise ValueError(f"Selected '{selected_short_hwid}' HWID, but 'hwid_map' is missing")

    full_hwid = next((d["hwid"] for d in hwid_map if d["short_hwid"] == selected_short_hwid), None)

    if not full_hwid:
        raise ValueError(f"Full HWID not found for '{selected_short_hwid}'")

    user: UserDto = sub_manager.middleware_data[USER_KEY]
    target_telegram_id = sub_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    devices = await remnawave_service.delete_device(user=target_user, hwid=full_hwid)
    logger.info(f"{log(user)} Deleted device '{full_hwid}' for user '{target_telegram_id}'")

    if devices:
        return

    await sub_manager.switch_to(state=DashboardUser.SUBSCRIPTION)


@inject
async def on_reset_traffic(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    subscription_service: FromDishka[SubscriptionService],
    remnawave: FromDishka[RemnawaveSDK],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    subscription = await subscription_service.get_current(target_telegram_id)

    if not subscription:
        raise ValueError(f"Current subscription for user '{target_telegram_id}' not found")

    await remnawave.users.reset_user_traffic(subscription.user_remna_id)
    logger.info(f"{log(user)} Reset trafic for user '{target_telegram_id}'")


@inject
async def on_discount_select(
    callback: CallbackQuery,
    widget: Select[int],
    dialog_manager: DialogManager,
    selected_discount: int,
    user_service: FromDishka[UserService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Selected discount '{selected_discount}'")
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    target_user.personal_discount = selected_discount
    await user_service.update(user=target_user)
    logger.info(f"{log(user)} Changed discount to '{selected_discount}' for '{target_telegram_id}'")
    await dialog_manager.switch_to(state=DashboardUser.MAIN)


@inject
async def on_discount_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    notification_service: FromDishka[NotificationService],
) -> None:
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    if message.text is None or not (message.text.isdigit() and 0 <= int(message.text) <= 100):
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-user-invalid-number"),
        )
        return

    number = int(message.text)
    target_user.personal_discount = number
    await user_service.update(user=target_user)
    logger.info(f"{log(user)} Changed discount to '{number}' for '{target_telegram_id}'")
    await dialog_manager.switch_to(state=DashboardUser.MAIN)


@inject
async def on_points_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    notification_service: FromDishka[NotificationService],
) -> None:
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    number = parse_int(message.text)

    if number is None:
        logger.warning(f"{log(user)} Invalid points input: '{message.text}'")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-user-invalid-number"),
        )
        return

    new_balance = target_user.balance + number

    if new_balance < 0:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(
                i18n_key="ntf-user-invalid-balance",
                i18n_kwargs={"operation": "ADD" if number > 0 else "SUB"},
            ),
        )
        return

    target_user.balance = new_balance
    await user_service.update(user=target_user)

    logger.info(
        f"{log(user)} {'Added' if number > 0 else 'Subtracted'} "
        f"'{abs(number)}' to balance for '{target_telegram_id}'"
    )


@inject
async def on_points_select(
    callback: CallbackQuery,
    widget: Select[int],
    dialog_manager: DialogManager,
    selected_points: int,
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
    notification_service: FromDishka[NotificationService],
    remnawave_service: FromDishka[RemnawaveService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Selected points '{selected_points}'")
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    new_balance = target_user.balance + selected_points

    if new_balance < 0:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(
                i18n_key="ntf-user-invalid-balance",
                i18n_kwargs={"operation": "ADD" if selected_points > 0 else "SUB"},
            ),
        )
        return

    target_user.balance = new_balance
    await user_service.update(target_user)

    logger.info(
        f"{log(user)} {'Added' if selected_points > 0 else 'Subtracted'} "
        f"'{abs(selected_points)}' to balance for '{target_telegram_id}'"
    )


@inject
async def on_referral_points_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    referral_service: FromDishka[ReferralService],
    notification_service: FromDishka[NotificationService],
    user_service: FromDishka[UserService],
) -> None:
    from src.core.enums import ReferralRewardType
    
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    number = parse_int(message.text)

    if number is None:
        logger.warning(f"{log(user)} Invalid referral points input: '{message.text}'")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-user-invalid-number"),
        )
        return

    if number == 0:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-user-invalid-number"),
        )
        return

    # For positive values - create direct reward
    # For negative values - subtract from referral balance only
    if number > 0:
        # Create referral reward directly
        await referral_service.create_direct_reward(
            user_telegram_id=target_telegram_id,
            amount=number,
            reward_type=ReferralRewardType.MONEY,
        )
        logger.info(
            f"{log(user)} Added '{number}' to referral balance for '{target_telegram_id}'"
        )
    else:
        # Get current referral balance
        referral_balance = await referral_service.get_pending_rewards_amount(
            target_telegram_id,
            ReferralRewardType.MONEY,
        )
        
        # Check if referral balance is sufficient
        amount_to_subtract = abs(number)
        new_referral_balance = referral_balance - amount_to_subtract
        
        if new_referral_balance < 0:
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(
                    i18n_key="ntf-user-invalid-balance",
                    i18n_kwargs={"operation": "SUB"},
                ),
            )
            return
        
        # Subtract from referral balance by marking rewards as issued
        await referral_service.mark_rewards_as_issued(
            target_telegram_id,
            amount_to_subtract,
            ReferralRewardType.MONEY,
        )
        
        logger.info(
            f"{log(user)} Subtracted '{abs(number)}' from referral balance for '{target_telegram_id}'"
        )


@inject
async def on_referral_points_select(
    callback: CallbackQuery,
    widget: Select[int],
    dialog_manager: DialogManager,
    selected_points: int,
    referral_service: FromDishka[ReferralService],
    notification_service: FromDishka[NotificationService],
    user_service: FromDishka[UserService],
) -> None:
    from src.core.enums import ReferralRewardType
    
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Selected referral points '{selected_points}'")
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    if selected_points == 0:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-user-invalid-number"),
        )
        return

    # For positive values - create direct reward
    # For negative values - subtract from referral balance only
    if selected_points > 0:
        # Create referral reward directly
        await referral_service.create_direct_reward(
            user_telegram_id=target_telegram_id,
            amount=selected_points,
            reward_type=ReferralRewardType.MONEY,
        )
        logger.info(
            f"{log(user)} Added '{selected_points}' to referral balance for '{target_telegram_id}'"
        )
    else:
        # Get current referral balance
        referral_balance = await referral_service.get_pending_rewards_amount(
            target_telegram_id,
            ReferralRewardType.MONEY,
        )
        
        # Check if referral balance is sufficient
        amount_to_subtract = abs(selected_points)
        new_referral_balance = referral_balance - amount_to_subtract
        
        if new_referral_balance < 0:
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(
                    i18n_key="ntf-user-invalid-balance",
                    i18n_kwargs={"operation": "SUB"},
                ),
            )
            return
        
        # Subtract from referral balance by marking rewards as issued
        await referral_service.mark_rewards_as_issued(
            target_telegram_id,
            amount_to_subtract,
            ReferralRewardType.MONEY,
        )
        
        logger.info(
            f"{log(user)} Subtracted '{abs(selected_points)}' from referral balance for '{target_telegram_id}'"
        )


@inject
async def on_traffic_limit_select(
    callback: CallbackQuery,
    widget: Select[int],
    dialog_manager: DialogManager,
    selected_traffic: int,
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
    remnawave_service: FromDishka[RemnawaveService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Selected traffic '{selected_traffic}'")
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    subscription = await subscription_service.get_current(target_telegram_id)

    if not subscription:
        raise ValueError(f"Current subscription for user '{target_telegram_id}' not found")

    subscription.traffic_limit = selected_traffic
    await subscription_service.update(subscription)

    await remnawave_service.updated_user(
        user=target_user,
        uuid=subscription.user_remna_id,
        subscription=subscription,
    )

    logger.info(
        f"{log(user)} Changed traffic limit to '{selected_traffic}' for '{target_telegram_id}'"
    )
    await dialog_manager.switch_to(state=DashboardUser.SUBSCRIPTION)


@inject
async def on_traffic_limit_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
    notification_service: FromDishka[NotificationService],
    remnawave_service: FromDishka[RemnawaveService],
) -> None:
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    subscription = await subscription_service.get_current(target_telegram_id)

    if not subscription:
        raise ValueError(f"Current subscription for user '{target_telegram_id}' not found")

    if message.text is None or not (message.text.isdigit() and int(message.text) > 0):
        logger.warning(f"{log(user)} Invalid traffic limit input: '{message.text}'")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-user-invalid-number"),
        )
        return

    number = int(message.text)
    subscription.traffic_limit = number
    await subscription_service.update(subscription)

    await remnawave_service.updated_user(
        user=target_user,
        uuid=subscription.user_remna_id,
        subscription=subscription,
    )

    logger.info(f"{log(user)} Changed traffic limit to '{number}' for '{target_telegram_id}'")
    await dialog_manager.switch_to(state=DashboardUser.SUBSCRIPTION)


@inject
async def on_device_limit_select(
    callback: CallbackQuery,
    widget: Select[int],
    dialog_manager: DialogManager,
    selected_device: int,
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
    remnawave_service: FromDishka[RemnawaveService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Selected device limit '{selected_device}'")
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    subscription = await subscription_service.get_current(target_telegram_id)

    if not subscription:
        raise ValueError(f"Current subscription for user '{target_telegram_id}' not found")

    subscription.device_limit = selected_device
    await subscription_service.update(subscription)

    await remnawave_service.updated_user(
        user=target_user,
        uuid=subscription.user_remna_id,
        subscription=subscription,
    )

    logger.info(
        f"{log(user)} Changed device limit to '{selected_device}' for '{target_telegram_id}'"
    )
    await dialog_manager.switch_to(state=DashboardUser.SUBSCRIPTION)


@inject
async def on_device_limit_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
    notification_service: FromDishka[NotificationService],
    remnawave_service: FromDishka[RemnawaveService],
) -> None:
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    subscription = await subscription_service.get_current(target_telegram_id)

    if not subscription:
        raise ValueError(f"Current subscription for user '{target_telegram_id}' not found")

    if message.text is None or not (message.text.isdigit() and int(message.text) > 0):
        logger.warning(f"{log(user)} Invalid device limit input: '{message.text}'")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-user-invalid-number"),
        )
        return

    number = int(message.text)
    subscription.device_limit = number
    await subscription_service.update(subscription)

    await remnawave_service.updated_user(
        user=target_user,
        uuid=subscription.user_remna_id,
        subscription=subscription,
    )

    logger.info(f"{log(user)} Changed device limit to '{number}' for '{target_telegram_id}'")
    await dialog_manager.switch_to(state=DashboardUser.SUBSCRIPTION)


@inject
async def on_internal_squad_select(
    callback: CallbackQuery,
    widget: Select[UUID],
    dialog_manager: DialogManager,
    selected_squad: UUID,
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
    remnawave_service: FromDishka[RemnawaveService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    subscription = await subscription_service.get_current(target_telegram_id)

    if not subscription:
        raise ValueError(f"Current subscription for user '{target_telegram_id}' not found")

    if selected_squad in subscription.internal_squads:
        updated_internal_squads = [s for s in subscription.internal_squads if s != selected_squad]
        logger.info(f"{log(user)} Unset internal squad '{selected_squad}'")
    else:
        updated_internal_squads = [*subscription.internal_squads, selected_squad]
        logger.info(f"{log(user)} Set internal squad '{selected_squad}'")

    subscription.internal_squads = updated_internal_squads
    await subscription_service.update(subscription)
    await remnawave_service.updated_user(
        user=target_user,
        uuid=subscription.user_remna_id,
        subscription=subscription,
    )


@inject
async def on_external_squad_select(
    callback: CallbackQuery,
    widget: Select[UUID],
    dialog_manager: DialogManager,
    selected_squad: UUID,
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
    remnawave_service: FromDishka[RemnawaveService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    subscription = await subscription_service.get_current(target_telegram_id)

    if not subscription:
        raise ValueError(f"Current subscription for user '{target_telegram_id}' not found")

    current_external_squad = subscription.external_squad[0] if subscription.external_squad else None
    if selected_squad == current_external_squad:
        subscription.external_squad = None
        logger.info(f"{log(user)} Unset external squad '{selected_squad}'")
    else:
        subscription.external_squad = [selected_squad]
        logger.info(f"{log(user)} Set external squad '{selected_squad}'")

    await subscription_service.update(subscription)
    await remnawave_service.updated_user(
        user=target_user,
        uuid=subscription.user_remna_id,
        subscription=subscription,
    )


@inject
async def on_transactions(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    transaction_service: FromDishka[TransactionService],
    notification_service: FromDishka[NotificationService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    transactions = await transaction_service.get_by_user(target_telegram_id)

    if not transactions:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-user-transactions-empty"),
        )
        return

    await dialog_manager.switch_to(state=DashboardUser.TRANSACTIONS_LIST)


async def on_transaction_select(
    callback: CallbackQuery,
    widget: Select[UUID],
    dialog_manager: DialogManager,
    selected_transaction: UUID,
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Selected transaction '{selected_transaction}'")
    dialog_manager.dialog_data["selected_transaction"] = selected_transaction
    await dialog_manager.switch_to(state=DashboardUser.TRANSACTION)


@inject
async def on_give_access(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    plan_service: FromDishka[PlanService],
    notification_service: FromDishka[NotificationService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    plans = await plan_service.get_allowed_plans()

    if not plans:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-user-allowed-plans-empty"),
        )
        return

    await dialog_manager.switch_to(state=DashboardUser.GIVE_ACCESS)


@inject
async def on_plan_select(
    callback: CallbackQuery,
    widget: Select[int],
    dialog_manager: DialogManager,
    selected_plan_id: int,
    plan_service: FromDishka[PlanService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Selected plan '{selected_plan_id}'")
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    plan = await plan_service.get(selected_plan_id)

    if not plan:
        raise ValueError(f"Plan '{selected_plan_id}' not found")

    if target_telegram_id not in plan.allowed_user_ids:
        plan.allowed_user_ids.append(target_telegram_id)
    else:
        plan.allowed_user_ids.remove(target_telegram_id)

    await plan_service.update(plan)
    logger.info(
        f"{log(user)} Given access to plan '{selected_plan_id}' for user '{target_telegram_id}'"
    )


@inject
async def on_duration_select(
    callback: CallbackQuery,
    widget: Select[int],
    dialog_manager: DialogManager,
    selected_duration: int,
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
    notification_service: FromDishka[NotificationService],
    remnawave_service: FromDishka[RemnawaveService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Selected duration '{selected_duration}'")
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    subscription = await subscription_service.get_current(target_telegram_id)

    if not subscription:
        raise ValueError(f"Current subscription for user '{target_telegram_id}' not found")

    new_expire = subscription.expire_at + timedelta(days=selected_duration)

    if new_expire < datetime_now():
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(
                i18n_key="ntf-user-invalid-expire-time",
                i18n_kwargs={"operation": "ADD" if selected_duration > 0 else "SUB"},
            ),
        )
        return

    subscription.expire_at = new_expire
    await subscription_service.update(subscription)
    await remnawave_service.updated_user(
        user=target_user,
        uuid=subscription.user_remna_id,
        subscription=subscription,
    )
    logger.info(
        f"{log(user)} {'Added' if selected_duration > 0 else 'Subtracted'} "
        f"'{abs(selected_duration)}' days to subscription for '{target_telegram_id}'"
    )


@inject
async def on_duration_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
    notification_service: FromDishka[NotificationService],
    remnawave_service: FromDishka[RemnawaveService],
) -> None:
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    subscription = await subscription_service.get_current(target_telegram_id)

    if not subscription:
        raise ValueError(f"Current subscription for user '{target_telegram_id}' not found")

    number = parse_int(message.text)

    if number is None:
        logger.warning(f"{log(user)} Invalid duration input: '{message.text}'")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-user-invalid-number"),
        )
        return

    new_expire = subscription.expire_at + timedelta(days=number)

    if new_expire < datetime_now():
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(
                i18n_key="ntf-user-invalid-expire-time",
                i18n_kwargs={"operation": "ADD" if number > 0 else "SUB"},
            ),
        )
        return

    subscription.expire_at = new_expire
    await subscription_service.update(subscription)
    await remnawave_service.updated_user(
        user=target_user,
        uuid=subscription.user_remna_id,
        subscription=subscription,
    )
    logger.info(
        f"{log(user)} {'Added' if number > 0 else 'Subtracted'} "
        f"'{abs(number)}' days to subscription for '{target_telegram_id}'"
    )


@inject
async def on_send(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    config: FromDishka[AppConfig],
    i18n: FromDishka[TranslatorRunner],
    user_service: FromDishka[UserService],
    notification_service: FromDishka[NotificationService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    payload = dialog_manager.dialog_data.get("payload")

    if not payload:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-broadcast-empty-content"),
        )
        return

    if is_double_click(dialog_manager, key="message_confirm", cooldown=5):
        text = i18n.get("contact-support-help")
        support_username = config.bot.support_username.get_secret_value()
        payload["reply_markup"] = get_contact_support_keyboard(support_username, text)

        message = await notification_service.notify_user(
            user=target_user,
            payload=MessagePayload(**payload),
        )
        await dialog_manager.switch_to(state=DashboardUser.MAIN)

        if message:
            i18n_key = "ntf-user-message-success"
        else:
            i18n_key = "ntf-user-message-not-sent"

        await notification_service.notify_user(user=user, payload=MessagePayload(i18n_key=i18n_key))
        return

    await notification_service.notify_user(
        user=user,
        payload=MessagePayload(i18n_key="ntf-double-click-confirm"),
    )
    logger.debug(f"{log(user)} Awaiting confirmation for message send")


@inject
async def on_sync(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    remnawave: FromDishka[RemnawaveSDK],
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
    notification_service: FromDishka[NotificationService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    bot_subscription = await subscription_service.get_current(target_telegram_id)
    remna_subscription: Optional[RemnaSubscriptionDto] = None

    try:
        result = await remnawave.users.get_users_by_telegram_id(telegram_id=str(target_telegram_id))
    except NotFoundError:
        result = None

    if not result and not bot_subscription:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-user-sync-missing-data"),
        )
        return

    if result:
        remna_subscription = RemnaSubscriptionDto.from_remna_user(result[0])

    if SubscriptionService.subscriptions_match(bot_subscription, remna_subscription):
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-user-sync-already"),
        )
        return

    await dialog_manager.switch_to(state=DashboardUser.SYNC)


@inject
async def on_sync_from_remnawave(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    remnawave: FromDishka[RemnawaveSDK],
    remnawave_service: FromDishka[RemnawaveService],
    subscription_service: FromDishka[SubscriptionService],
    user_service: FromDishka[UserService],
    notification_service: FromDishka[NotificationService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    subscription = await subscription_service.get_current(target_telegram_id)

    try:
        result = await remnawave.users.get_users_by_telegram_id(telegram_id=str(target_telegram_id))
    except NotFoundError:
        result = None

    if not result:
        if subscription:
            subscription.status = SubscriptionStatus.DELETED
            await subscription_service.update(subscription)

        await user_service.delete_current_subscription(user.telegram_id)
    else:
        await remnawave_service.sync_user(result[0], creating=False)

    await notification_service.notify_user(
        user=user,
        payload=MessagePayload(i18n_key="ntf-user-sync-success"),
    )
    await dialog_manager.switch_to(state=DashboardUser.MAIN)


@inject
async def on_sync_from_remnashop(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    subscription_service: FromDishka[SubscriptionService],
    remnawave_service: FromDishka[RemnawaveService],
    user_service: FromDishka[UserService],
    notification_service: FromDishka[NotificationService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    subscription = await subscription_service.get_current(target_telegram_id)

    if not subscription:
        await remnawave_service.delete_user(target_user)
    else:
        remna_user = await remnawave_service.get_user(subscription.user_remna_id)
        if remna_user:
            await remnawave_service.updated_user(
                user=target_user,
                uuid=subscription.user_remna_id,
                subscription=subscription,
            )

        else:
            created_user = await remnawave_service.create_user(
                user=target_user,
                subscription=subscription,
                force=True,
            )
            await remnawave_service.sync_user(created_user, creating=False)

    await notification_service.notify_user(
        user=user,
        payload=MessagePayload(i18n_key="ntf-user-sync-success"),
    )
    await dialog_manager.switch_to(state=DashboardUser.MAIN)


@inject
async def on_give_subscription(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    plan_service: FromDishka[PlanService],
    notification_service: FromDishka[NotificationService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    plans = await plan_service.get_available_plans(target_user)

    if not plans:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-user-plans-empty"),
        )
        return

    await dialog_manager.switch_to(state=DashboardUser.GIVE_SUBSCRIPTION)


@inject
async def on_subscription_select(
    callback: CallbackQuery,
    widget: Select[int],
    dialog_manager: DialogManager,
    selected_plan_id: int,
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Selected plan '{selected_plan_id}'")
    dialog_manager.dialog_data["selected_plan_id"] = selected_plan_id
    await dialog_manager.switch_to(state=DashboardUser.SUBSCRIPTION_DURATION)


@inject
async def on_subscription_duration_select(
    callback: CallbackQuery,
    widget: Select[int],
    dialog_manager: DialogManager,
    selected_duration: int,
    user_service: FromDishka[UserService],
    plan_service: FromDishka[PlanService],
    subscription_service: FromDishka[SubscriptionService],
    remnawave_service: FromDishka[RemnawaveService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Selected duration '{selected_duration}'")
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    selected_plan_id = dialog_manager.dialog_data["selected_plan_id"]
    plan = await plan_service.get(selected_plan_id)

    if not plan:
        raise ValueError(f"Plan '{selected_plan_id}' not found")

    plan_snapshot = PlanSnapshotDto.from_plan(plan, selected_duration)
    subscription = await subscription_service.get_current(target_telegram_id)

    # Deactivate the old subscription before creating a new one
    if subscription:
        subscription.status = SubscriptionStatus.DISABLED
        await subscription_service.update(subscription)
        logger.info(f"Disabled old subscription '{subscription.id}' before creating new one")
        remna_user = await remnawave_service.updated_user(
            user=target_user,
            uuid=subscription.user_remna_id,
            plan=plan_snapshot,
            reset_traffic=True,
        )
    else:
        remna_user = await remnawave_service.create_user(user=target_user, plan=plan_snapshot, force=True)

    # Проверяем, является ли план пробным (по названию)
    is_trial_plan = plan.name and ("пробн" in plan.name.lower() or "trial" in plan.name.lower())
    
    new_subscription = SubscriptionDto(
        user_remna_id=remna_user.uuid,
        status=SubscriptionStatus.ACTIVE,
        is_trial=is_trial_plan,  # Устанавливаем флаг для пробных подписок
        traffic_limit=plan.traffic_limit,
        device_limit=plan.device_limit,
        traffic_limit_strategy=plan.traffic_limit_strategy,
        tag=plan.tag,
        internal_squads=plan.internal_squads,
        external_squad=plan.external_squad,
        expire_at=remna_user.expire_at,
        url=remna_user.subscription_url,
        plan=plan_snapshot,
    )
    await subscription_service.create(target_user, new_subscription)
    
    # Очищаем кеш пользователя чтобы он увидел актуальные данные
    await user_service.clear_user_cache(target_telegram_id)

    logger.info(f"{log(user)} Set plan '{selected_plan_id}' for user '{target_telegram_id}'")
    
    # Прямой редирект вместо taskiq для мгновенного обновления
    from src.bot.states import MainMenu
    try:
        await dialog_manager.bg(user_id=target_telegram_id, chat_id=target_telegram_id).start(
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
            show_mode=ShowMode.DELETE_AND_SEND,
        )
    except Exception as e:
        logger.warning(f"Failed direct redirect for user {target_telegram_id}: {e}")
        await redirect_to_main_menu_task.kiq(target_user.telegram_id)
    
    await dialog_manager.switch_to(state=DashboardUser.MAIN)


@inject
async def on_subscription_duration_keep_current(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    plan_service: FromDishka[PlanService],
    subscription_service: FromDishka[SubscriptionService],
    remnawave_service: FromDishka[RemnawaveService],
) -> None:
    """Изменить подписку с сохранением текущей длительности (точное время)."""
    from datetime import datetime, timezone
    
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    target_telegram_id = dialog_manager.dialog_data["target_telegram_id"]
    target_user = await user_service.get(telegram_id=target_telegram_id)

    if not target_user:
        raise ValueError(f"User '{target_telegram_id}' not found")

    selected_plan_id = dialog_manager.dialog_data["selected_plan_id"]
    plan = await plan_service.get(selected_plan_id)

    if not plan:
        raise ValueError(f"Plan '{selected_plan_id}' not found")

    subscription = await subscription_service.get_current(target_telegram_id)
    
    if not subscription or not subscription.expire_at:
        # Если нет текущей подписки, используем минимальную длительность
        min_duration = min(plan.durations, key=lambda d: d.days) if plan.durations else None
        if not min_duration:
            raise ValueError(f"Plan '{selected_plan_id}' has no durations")
        selected_duration = min_duration.days
        original_expire_at = None
        logger.info(f"{log(user)} No current subscription, using minimum duration '{selected_duration}' days")
    else:
        # Сохраняем точное время истечения текущей подписки
        original_expire_at = subscription.expire_at
        # Для plan_snapshot используем приблизительное количество дней
        now = datetime.now(timezone.utc)
        remaining = subscription.expire_at - now
        selected_duration = max(1, remaining.days + 1)  # +1 чтобы не потерять часы/минуты
        logger.info(f"{log(user)} Keeping exact expire_at: {original_expire_at}")

    plan_snapshot = PlanSnapshotDto.from_plan(plan, selected_duration)

    # Деактивируем старую подписку перед созданием новой
    if subscription:
        subscription.status = SubscriptionStatus.DISABLED
        await subscription_service.update(subscription)
        logger.info(f"Disabled old subscription '{subscription.id}' before creating new one")
        
        # Используем subscription с точным expire_at для обновления в Remnawave
        temp_subscription = SubscriptionDto(
            id=subscription.id,
            user_remna_id=subscription.user_remna_id,
            status=SubscriptionStatus.ACTIVE,
            is_trial=subscription.is_trial,
            traffic_limit=plan.traffic_limit,
            device_limit=plan.device_limit,
            traffic_limit_strategy=plan.traffic_limit_strategy,
            tag=plan.tag,
            internal_squads=plan.internal_squads,
            external_squad=plan.external_squad,
            expire_at=original_expire_at,  # Точное время истечения
            url=subscription.url,
            plan=plan_snapshot,
        )
        remna_user = await remnawave_service.updated_user(
            user=target_user,
            uuid=subscription.user_remna_id,
            subscription=temp_subscription,  # Передаём subscription вместо plan
            reset_traffic=True,
        )
    else:
        remna_user = await remnawave_service.create_user(user=target_user, plan=plan_snapshot, force=True)
        original_expire_at = remna_user.expire_at

    # Проверяем, является ли план пробным (по названию)
    is_trial_plan = plan.name and ("пробн" in plan.name.lower() or "trial" in plan.name.lower())
    
    new_subscription = SubscriptionDto(
        user_remna_id=remna_user.uuid,
        status=SubscriptionStatus.ACTIVE,
        is_trial=is_trial_plan,
        traffic_limit=plan.traffic_limit,
        device_limit=plan.device_limit,
        traffic_limit_strategy=plan.traffic_limit_strategy,
        tag=plan.tag,
        internal_squads=plan.internal_squads,
        external_squad=plan.external_squad,
        expire_at=original_expire_at if original_expire_at else remna_user.expire_at,  # Сохраняем точное время
        url=remna_user.subscription_url,
        plan=plan_snapshot,
    )
    await subscription_service.create(target_user, new_subscription)
    
    # Очищаем кеш пользователя чтобы он увидел актуальные данные
    await user_service.clear_user_cache(target_telegram_id)

    logger.info(f"{log(user)} Changed plan to '{selected_plan_id}' for user '{target_telegram_id}' keeping exact duration")
    
    # Прямой редирект вместо taskiq для мгновенного обновления
    from src.bot.states import MainMenu
    try:
        await dialog_manager.bg(user_id=target_telegram_id, chat_id=target_telegram_id).start(
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
            show_mode=ShowMode.DELETE_AND_SEND,
        )
    except Exception as e:
        logger.warning(f"Failed direct redirect for user {target_telegram_id}: {e}")
        await redirect_to_main_menu_task.kiq(target_user.telegram_id)
    
    await dialog_manager.switch_to(state=DashboardUser.MAIN)
