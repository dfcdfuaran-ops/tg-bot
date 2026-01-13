from typing import Optional

from aiogram import Bot
from aiogram.types import CallbackQuery, ErrorEvent
from aiogram_dialog import BgManagerFactory, ShowMode, StartMode
from dishka import FromDishka
from loguru import logger

from src.bot.states import MainMenu
from src.core.utils.formatters import format_user_log as log
from src.infrastructure.database.models.dto import UserDto

# Registered in main router (src/bot/dispatcher.py)


async def on_lost_context(
    event: ErrorEvent,
    user: UserDto,
    bot: FromDishka[Bot],
    bg_manager_factory: FromDishka[BgManagerFactory],
) -> None:
    """
    Обработчик устаревших/потерянных контекстов диалога.
    
    Тихо перезапускает диалог без показа предупреждений пользователю,
    редактируя существующее сообщение если возможно.
    """
    # Логируем как debug, так как это нормальное поведение при рестарте бота
    # или когда пользователь нажимает на старые кнопки
    logger.debug(f"{log(user)} Dialog context expired: {type(event.exception).__name__}")
    
    # Отвечаем на callback query тихо (пустой answer убирает индикатор загрузки)
    callback_query: Optional[CallbackQuery] = event.update.callback_query
    if callback_query:
        try:
            await callback_query.answer()  # Пустой answer - без текста
        except Exception:
            pass  # Игнорируем ошибку если callback уже обработан
    
    # Определяем message_id для редактирования
    target_message_id = None
    if callback_query and callback_query.message:
        target_message_id = callback_query.message.message_id
    
    # Автоматически перезапускаем диалог в главное меню
    try:
        bg_manager = bg_manager_factory.bg(
            bot=bot,
            user_id=user.telegram_id,
            chat_id=user.telegram_id,
        )
        
        # Если есть message_id, пытаемся отредактировать существующее сообщение
        if target_message_id:
            # Пробуем DELETE_AND_SEND - удалит старое и отправит новое
            # Это надежнее чем EDIT, так как EDIT может не работать если изменилась структура
            await bg_manager.start(
                state=MainMenu.MAIN,
                mode=StartMode.RESET_STACK,
                show_mode=ShowMode.DELETE_AND_SEND,
            )
        else:
            # Нет сообщения для редактирования - просто отправляем новое
            await bg_manager.start(
                state=MainMenu.MAIN,
                mode=StartMode.RESET_STACK,
                show_mode=ShowMode.SEND,
            )
        
        logger.debug(f"{log(user)} Dialog silently restarted")
    except Exception as e:
        logger.warning(f"{log(user)} Failed to restart dialog: {e}")
        
        # Fallback: если перезапуск не сработал, пробуем удалить старое сообщение
        if target_message_id:
            try:
                await bot.delete_message(
                    chat_id=user.telegram_id,
                    message_id=target_message_id
                )
            except Exception:
                pass
        
        # Последний fallback: простое сообщение
        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text="Нажмите /start для продолжения."
            )
        except Exception:
            pass  # Если и это не сработало, пользователь сам нажмет /start

