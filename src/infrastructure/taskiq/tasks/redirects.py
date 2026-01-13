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
) -> None:
    # Добавляем небольшую задержку для гарантии сохранения данных в БД
    import asyncio
    await asyncio.sleep(1.5)
    
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
) -> None:
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
