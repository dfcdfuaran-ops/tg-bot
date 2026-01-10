from aiogram.types import CallbackQuery
from aiogram_dialog import DialogManager, StartMode
from aiogram_dialog.widgets.kbd import Button, Select
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from loguru import logger

from src.bot.states import DashboardSettings, RemnashopNotifications, DashboardRemnashop
from src.core.constants import USER_KEY
from src.core.enums import SystemNotificationType, UserNotificationType
from src.core.utils.formatters import format_user_log as log
from src.infrastructure.database.models.dto import UserDto
from src.services.settings import SettingsService


@inject
async def on_user_type_select(
    callback: CallbackQuery,
    widget: Select[UserNotificationType],
    dialog_manager: DialogManager,
    selected_type: UserNotificationType,
    settings_service: FromDishka[SettingsService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Инициализируем временное хранилище изменений
    if "notifications_changes" not in dialog_manager.dialog_data:
        dialog_manager.dialog_data["notifications_changes"] = {}
    
    # Получаем текущее состояние
    settings = await settings_service.get()
    current_value = settings.user_notifications.is_enabled(selected_type)
    
    # Используем upper() для соответствия с getter
    type_key = selected_type.value.upper()
    
    # Проверяем есть ли уже изменение для этого типа
    if type_key in dialog_manager.dialog_data["notifications_changes"]:
        # Используем сохраненное изменение
        current_value = dialog_manager.dialog_data["notifications_changes"][type_key]
    
    # Переключаем значение
    new_value = not current_value
    dialog_manager.dialog_data["notifications_changes"][type_key] = new_value
    
    logger.debug(f"{log(user)} Changed notification type (not applied yet): '{selected_type}' to '{new_value}'")


@inject
async def on_cancel_global_discount_mode(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена изменений в меню 'Режим' - возврат к главному меню."""
    await dialog_manager.switch_to(DashboardSettings.GLOBAL_DISCOUNT)


@inject
async def on_accept_global_discount_mode(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принять изменения в меню 'Режим' - возврат к главному меню."""
    await dialog_manager.switch_to(DashboardSettings.GLOBAL_DISCOUNT)


@inject
async def on_notifications_cancel_submenu(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена изменений в подменю уведомлений - возврат к главному меню уведомлений."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    changes = dialog_manager.dialog_data.get("notifications_changes", {})
    logger.info(f"{log(user)} Cancelling notifications changes (not saved): {changes}")
    
    # Очищаем временные изменения БЕЗ сохранения в БД
    dialog_manager.dialog_data.pop("notifications_changes", None)
    dialog_manager.dialog_data.pop("initial_notifications_state", None)
    
    logger.info(f"{log(user)} Cancelled notifications changes in submenu")
    
    # Возврат в главное меню уведомлений
    await dialog_manager.switch_to(RemnashopNotifications.MAIN)


@inject
async def on_notifications_accept_submenu(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Принятие изменений в подменю - изменения накапливаются, но НЕ сохраняются в БД."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    changes = dialog_manager.dialog_data.get("notifications_changes", {})
    
    logger.info(f"{log(user)} Accepting notifications changes in submenu (not saved to DB yet): {changes}")
    
    # НЕ очищаем notifications_changes - они нужны для сохранения при принятии в главном меню
    # Только очищаем initial_notifications_state для подменю
    
    logger.info(f"{log(user)} Accepted notifications changes in submenu (changes kept for main menu)")
    
    # Возврат в главное меню уведомлений
    await dialog_manager.switch_to(RemnashopNotifications.MAIN)


@inject
async def on_notifications_cancel_main(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Отмена в главном меню уведомлений - откат ВСЕХ изменений и возврат в меню Настройки."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    changes = dialog_manager.dialog_data.get("notifications_changes", {})
    initial_state = dialog_manager.dialog_data.get("initial_notifications_state", {})
    
    # Если были изменения, откатываем их к начальному состоянию
    if changes and initial_state:
        logger.info(f"{log(user)} Rolling back notifications changes: {changes}")
        
        settings = await settings_service.get()
        
        # Откатываем все изменения к начальному состоянию
        for notification_type_str in changes.keys():
            # Получаем начальное значение
            initial_value = initial_state.get(notification_type_str)
            if initial_value is not None:
                field_name = notification_type_str.lower()
                
                # Определяем тип уведомления и откатываем
                try:
                    UserNotificationType(notification_type_str)
                    setattr(settings.user_notifications, field_name, initial_value)
                    logger.info(f"{log(user)} Rolled back user notification '{field_name}' -> {initial_value}")
                except ValueError:
                    try:
                        SystemNotificationType(notification_type_str)
                        setattr(settings.system_notifications, field_name, initial_value)
                        logger.info(f"{log(user)} Rolled back system notification '{field_name}' -> {initial_value}")
                    except ValueError:
                        logger.error(f"Unknown notification type: {notification_type_str}")
        
        # Сохраняем откат в БД
        await settings_service.update(settings)
        logger.info(f"{log(user)} Rolled back notifications changes to database")
    else:
        logger.info(f"{log(user)} No notifications changes to roll back")
    
    # Очищаем временные данные
    dialog_manager.dialog_data.pop("notifications_changes", None)
    dialog_manager.dialog_data.pop("initial_notifications_state", None)
    
    logger.info(f"{log(user)} Cancelled notifications")
    
    # Возврат в меню Настройки
    await dialog_manager.start(DashboardSettings.MAIN, mode=StartMode.NORMAL)


@inject
async def on_notifications_accept_main(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Принять в главном меню уведомлений - сохранение ВСЕХ накопленных изменений."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    changes = dialog_manager.dialog_data.get("notifications_changes", {})
    
    logger.info(f"{log(user)} Accepting ALL notifications changes: {changes}")
    
    if changes:
        settings = await settings_service.get()
        
        # Применяем все накопленные изменения уведомлений
        for notification_type_str, new_value in changes.items():
            field_name = notification_type_str.lower()
            
            # Пытаемся определить тип уведомления
            try:
                # Сначала пробуем как UserNotificationType
                UserNotificationType(notification_type_str)
                setattr(settings.user_notifications, field_name, new_value)
                logger.info(f"{log(user)} Applied user notification '{field_name}' -> {new_value}")
            except ValueError:
                try:
                    # Затем пробуем как SystemNotificationType
                    SystemNotificationType(notification_type_str)
                    setattr(settings.system_notifications, field_name, new_value)
                    logger.info(f"{log(user)} Applied system notification '{field_name}' -> {new_value}")
                except ValueError:
                    logger.error(f"Unknown notification type: {notification_type_str}")
        
        # Сохраняем в БД
        await settings_service.update(settings)
        logger.info(f"{log(user)} Saved ALL notifications changes to database")
    else:
        logger.info(f"{log(user)} No notifications changes to save")
    
    # Очищаем временные данные
    dialog_manager.dialog_data.pop("notifications_changes", None)
    dialog_manager.dialog_data.pop("initial_notifications_state", None)
    
    # Возврат в меню Настройки
    await dialog_manager.start(DashboardSettings.MAIN, mode=StartMode.NORMAL)


@inject
async def on_system_type_select(
    callback: CallbackQuery,
    widget: Select[SystemNotificationType],
    dialog_manager: DialogManager,
    selected_type: SystemNotificationType,
    settings_service: FromDishka[SettingsService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Инициализируем временное хранилище изменений
    if "notifications_changes" not in dialog_manager.dialog_data:
        dialog_manager.dialog_data["notifications_changes"] = {}
    
    # Получаем текущее состояние
    settings = await settings_service.get()
    current_value = settings.system_notifications.is_enabled(selected_type)
    
    # Используем upper() для соответствия с getter
    type_key = selected_type.value.upper()
    
    # Проверяем есть ли уже изменение для этого типа
    if type_key in dialog_manager.dialog_data["notifications_changes"]:
        # Используем сохраненное изменение
        current_value = dialog_manager.dialog_data["notifications_changes"][type_key]
    
    # Переключаем значение
    new_value = not current_value
    dialog_manager.dialog_data["notifications_changes"][type_key] = new_value
    
    logger.debug(f"{log(user)} Changed notification type (not applied yet): '{selected_type}' to '{new_value}'")
