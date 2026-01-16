from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram_dialog import BgManagerFactory, ShowMode, StartMode
from dishka.integrations.taskiq import FromDishka, inject
from fluentogram import TranslatorHub
from loguru import logger

import asyncio

from src.bot.states import MainMenu, Subscription
from src.core.enums import PurchaseType
from src.infrastructure.database.models.dto import UserDto
from src.infrastructure.taskiq.broker import broker
from src.services.user import UserService


@broker.task
@inject
async def redirect_to_main_menu_task(
    telegram_id: int,
    bot: FromDishka[Bot],
    bg_manager_factory: FromDishka[BgManagerFactory],
) -> None:
    bg_manager = bg_manager_factory.bg(
        bot=bot,
        user_id=telegram_id,
        chat_id=telegram_id,
    )
    try:
        await bg_manager.start(
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
            show_mode=ShowMode.DELETE_AND_SEND,
        )
    except TelegramBadRequest as e:
        if "chat not found" in str(e).lower():
            logger.debug(f"Chat not found for user {telegram_id}. User may have blocked the bot.")
        else:
            raise


@broker.task
@inject
async def redirect_to_successed_trial_task(
    user: UserDto,
    bot: FromDishka[Bot],
    bg_manager_factory: FromDishka[BgManagerFactory],
    user_service: FromDishka[UserService],
) -> None:
    import asyncio
    
    # Умная полирующая задержка - проверяем наличие подписки в БД
    # вместо просто ждали фиксированное время
    max_retries = 10
    retry_interval = 0.2  # 200ms между попытками
    subscription_found = False
    
    for attempt in range(max_retries):
        try:
            # Пытаемся получить свежего пользователя с подпиской
            fresh_user = await user_service.get(user.telegram_id)
            if fresh_user and fresh_user.current_subscription:
                logger.debug(
                    f"Subscription found for user {user.telegram_id} on attempt {attempt + 1}"
                )
                subscription_found = True
                break
        except Exception as e:
            logger.debug(f"Attempt {attempt + 1} to fetch subscription failed: {e}")
        
        # Ждём перед следующей попыткой
        if attempt < max_retries - 1:
            await asyncio.sleep(retry_interval)
    
    if not subscription_found:
        logger.warning(
            f"Subscription not found for user {user.telegram_id} after {max_retries} retries. "
            f"Proceeding anyway..."
        )
    
    bg_manager = bg_manager_factory.bg(
        bot=bot,
        user_id=user.telegram_id,
        chat_id=user.telegram_id,
    )
    try:
        await bg_manager.start(
            state=Subscription.TRIAL,
            mode=StartMode.RESET_STACK,
            show_mode=ShowMode.DELETE_AND_SEND,
        )
    except TelegramBadRequest as e:
        if "chat not found" in str(e).lower():
            logger.debug(f"Chat not found for user {user.telegram_id}. User may have blocked the bot.")
        else:
            raise


@broker.task
@inject
async def redirect_to_successed_payment_task(
    user: UserDto,
    purchase_type: PurchaseType,
    bot: FromDishka[Bot],
    bg_manager_factory: FromDishka[BgManagerFactory],
    user_service: FromDishka[UserService],
) -> None:
    import asyncio
    
    # Очищаем кэш пользователя перед редиректом
    await user_service.clear_user_cache(user.telegram_id)
    
    # Умный полинг - ждём пока подписка обновится в БД
    # (для продления нужно убедиться что expire_at обновлён)
    max_retries = 10
    retry_interval = 0.2  # 200ms между попытками
    data_ready = False
    
    for attempt in range(max_retries):
        try:
            # Пытаемся получить свежего пользователя
            fresh_user = await user_service.get(user.telegram_id)
            if fresh_user and fresh_user.current_subscription:
                # Для продления проверяем что expire_at отличается от старого
                # или просто есть подписка
                logger.debug(
                    f"Fresh subscription data found for user {user.telegram_id} on attempt {attempt + 1}"
                )
                data_ready = True
                break
        except Exception as e:
            logger.debug(f"Attempt {attempt + 1} to fetch subscription failed: {e}")
        
        # Ждём перед следующей попыткой
        if attempt < max_retries - 1:
            await asyncio.sleep(retry_interval)
    
    if not data_ready:
        logger.warning(
            f"Fresh subscription data not confirmed for user {user.telegram_id} after {max_retries} retries. "
            f"Proceeding anyway..."
        )
    
    bg_manager = bg_manager_factory.bg(
        bot=bot,
        user_id=user.telegram_id,
        chat_id=user.telegram_id,
    )
    try:
        await bg_manager.start(
            state=Subscription.SUCCESS,
            data={"purchase_type": purchase_type},
            mode=StartMode.RESET_STACK,
            show_mode=ShowMode.DELETE_AND_SEND,
        )
    except TelegramBadRequest as e:
        if "chat not found" in str(e).lower():
            logger.debug(f"Chat not found for user {user.telegram_id}. User may have blocked the bot.")
        else:
            raise


@broker.task
@inject
async def redirect_to_failed_subscription_task(
    user: UserDto,
    bot: FromDishka[Bot],
    bg_manager_factory: FromDishka[BgManagerFactory],
) -> None:
    bg_manager = bg_manager_factory.bg(
        bot=bot,
        user_id=user.telegram_id,
        chat_id=user.telegram_id,
    )
    try:
        await bg_manager.start(
            state=Subscription.FAILED,
            mode=StartMode.RESET_STACK,
            show_mode=ShowMode.DELETE_AND_SEND,
        )
    except TelegramBadRequest as e:
        if "chat not found" in str(e).lower():
            logger.debug(f"Chat not found for user {user.telegram_id}. User may have blocked the bot.")
        else:
            raise


@broker.task
@inject
async def redirect_to_balance_success_task(
    user: UserDto,
    amount: int,
    currency_symbol: str,
    bot: FromDishka[Bot],
    bg_manager_factory: FromDishka[BgManagerFactory],
) -> None:
    """Redirect user to balance success screen after topup."""
    bg_manager = bg_manager_factory.bg(
        bot=bot,
        user_id=user.telegram_id,
        chat_id=user.telegram_id,
    )
    try:
        await bg_manager.start(
            state=MainMenu.BALANCE_SUCCESS,
            data={"amount": amount, "currency": currency_symbol},
            mode=StartMode.RESET_STACK,
            show_mode=ShowMode.DELETE_AND_SEND,
        )
    except TelegramBadRequest as e:
        if "chat not found" in str(e).lower():
            logger.debug(f"Chat not found for user {user.telegram_id}. User may have blocked the bot.")
        else:
            raise


@broker.task
@inject
async def redirect_to_extra_devices_success_task(
    user: UserDto,
    device_count: int,
    bot: FromDishka[Bot],
    bg_manager_factory: FromDishka[BgManagerFactory],
) -> None:
    """Redirect user to extra devices success screen after purchase."""
    bg_manager = bg_manager_factory.bg(
        bot=bot,
        user_id=user.telegram_id,
        chat_id=user.telegram_id,
    )
    try:
        await bg_manager.start(
            state=Subscription.ADD_DEVICE_SUCCESS,
            data={"device_count": device_count},
            mode=StartMode.RESET_STACK,
            show_mode=ShowMode.DELETE_AND_SEND,
        )
    except TelegramBadRequest as e:
        if "chat not found" in str(e).lower():
            logger.debug(f"Chat not found for user {user.telegram_id}. User may have blocked the bot.")
        else:
            raise


@broker.task
@inject
async def send_balance_topup_notification_task(
    telegram_id: int,
    amount: int,
    currency_symbol: str,
    bot: FromDishka[Bot],
    translator_hub: FromDishka[TranslatorHub],
) -> None:
    """Send balance topup success notification with close button."""
    try:
        # Wait for main menu to be rendered first (worker takes time to start)
        await asyncio.sleep(7)
        
        translator = translator_hub.get_translator_by_locale(locale="ru")
        
        # Format notification message
        message_text = translator.get(
            "ntf-balance-topup-success",
            amount=amount,
            currency=currency_symbol,
        )
        
        # Create inline keyboard with "Done" button
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Готово", callback_data="delete_message")]
            ]
        )
        
        await bot.send_message(
            chat_id=telegram_id,
            text=message_text,
            reply_markup=keyboard,
        )
        
        logger.info(f"Sent balance topup notification to user {telegram_id}")
        
    except TelegramBadRequest as e:
        if "chat not found" in str(e).lower():
            logger.debug(f"Chat not found for user {telegram_id}. User may have blocked the bot.")
        else:
            logger.error(f"Failed to send balance topup notification to {telegram_id}: {e}")
            raise
    except Exception as e:
        logger.error(f"Unexpected error sending balance topup notification to {telegram_id}: {e}")
