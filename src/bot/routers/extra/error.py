from typing import Optional

from aiogram import Bot
from aiogram.types import CallbackQuery, ErrorEvent
from aiogram_dialog import BgManagerFactory, ShowMode, StartMode
from dishka import FromDishka
from loguru import logger

from src.bot.states import MainMenu
from src.core.utils.formatters import format_user_log as log
from src.core.utils.message_payload import MessagePayload
from src.infrastructure.database.models.dto import UserDto
from src.services.notification import NotificationService

# Registered in main router (src/bot/dispatcher.py)


async def on_lost_context(
    event: ErrorEvent,
    user: UserDto,
    notification_service: FromDishka[NotificationService],
    bot: FromDishka[Bot],
    bg_manager_factory: FromDishka[BgManagerFactory],
) -> None:
    logger.error(f"{log(user)} Lost context: {event.exception}")
    
    # Отвечаем на callback query, если он есть, чтобы убрать индикатор загрузки
    callback_query: Optional[CallbackQuery] = event.update.callback_query
    if callback_query:
        try:
            await callback_query.answer("⚠️ Диалог устарел. Перезапуск...")
        except Exception as e:
            logger.warning(f"{log(user)} Failed to answer callback query: {e}")
    
    # Определяем message_id для редактирования или удаления
    target_message_id = None
    if callback_query and callback_query.message:
        target_message_id = callback_query.message.message_id
        
        # Удаляем несколько предыдущих сообщений (кроме того, которое будем редактировать)
        for i in range(1, 5):  # Удаляем 4 предыдущих сообщения
            try:
                await bot.delete_message(
                    chat_id=user.telegram_id,
                    message_id=target_message_id - i
                )
            except Exception:
                pass  # Игнорируем ошибки (сообщение может быть уже удалено)
    
    # Автоматически перезапускаем диалог в главное меню
    try:
        bg_manager = bg_manager_factory.bg(
            bot=bot,
            user_id=user.telegram_id,
            chat_id=user.telegram_id,
        )
        
        # Если есть message_id, пытаемся отредактировать существующее сообщение
        # Иначе отправляем новое
        show_mode = ShowMode.EDIT if target_message_id else ShowMode.SEND
        
        await bg_manager.start(
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
            show_mode=show_mode,
        )
        logger.info(f"{log(user)} Dialog restarted after lost context (show_mode={show_mode})")
    except Exception as e:
        logger.error(f"{log(user)} Failed to restart dialog after lost context: {e}")
        
        # Если не удалось отредактировать, пробуем удалить старое сообщение и отправить новое
        if target_message_id:
            try:
                await bot.delete_message(
                    chat_id=user.telegram_id,
                    message_id=target_message_id
                )
                logger.debug(f"{log(user)} Deleted old message before fallback")
            except Exception:
                pass
        
        # Fallback: отправляем простое текстовое сообщение с просьбой нажать /start
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text="⚠️ Произошла ошибка. Пожалуйста, нажмите /start для перезапуска."
            )
        except Exception as fallback_error:
            logger.error(f"{log(user)} Fallback failed: {fallback_error}")

