from aiogram.types import CallbackQuery
from aiogram_dialog import DialogManager, StartMode
from aiogram_dialog.widgets.kbd import Button
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from loguru import logger

from src.bot.states import DashboardRemnashop
from src.core.constants import USER_KEY
from src.core.utils.formatters import format_user_log as log
from src.infrastructure.database.models.dto import UserDto
from src.services.settings import SettingsService


@inject
async def on_toggle_community(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Toggle кнопки сообщества."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    new_value = await settings_service.toggle_feature("community_enabled")
    logger.info(f"{log(user)} Toggled community_enabled -> {new_value}")


@inject
async def on_toggle_tos(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Toggle кнопки соглашения."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    new_value = await settings_service.toggle_feature("tos_enabled")
    logger.info(f"{log(user)} Toggled tos_enabled -> {new_value}")


@inject
async def on_toggle_balance(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Toggle функционала баланса."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    new_value = await settings_service.toggle_feature("balance_enabled")
    logger.info(f"{log(user)} Toggled balance_enabled -> {new_value}")


@inject
async def on_toggle_extra_devices(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Toggle функционала доп. устройств."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    new_value = await settings_service.toggle_extra_devices()
    logger.info(f"{log(user)} Toggled extra_devices_enabled -> {new_value}")


@inject
async def on_toggle_transfers(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Toggle функционала переводов баланса."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    new_value = await settings_service.toggle_transfers()
    logger.info(f"{log(user)} Toggled transfers_enabled -> {new_value}")


@inject
async def on_cancel_features(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Отмена - восстановить начальные значения и вернуться назад."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    initial = dialog_manager.dialog_data.get("initial_features", {})
    
    if initial:
        # Восстанавливаем начальные значения
        current = await settings_service.get_feature_settings()
        
        if current.community_enabled != initial.get("community_enabled", current.community_enabled):
            await settings_service.toggle_feature("community_enabled")
        if current.tos_enabled != initial.get("tos_enabled", current.tos_enabled):
            await settings_service.toggle_feature("tos_enabled")
        if current.balance_enabled != initial.get("balance_enabled", current.balance_enabled):
            await settings_service.toggle_feature("balance_enabled")
        if current.extra_devices.enabled != initial.get("extra_devices_enabled", current.extra_devices.enabled):
            await settings_service.toggle_extra_devices()
        if current.transfers.enabled != initial.get("transfers_enabled", current.transfers.enabled):
            await settings_service.toggle_transfers()
        
        logger.info(f"{log(user)} Cancelled feature changes, restored initial values")
    
    # Возвращаемся на меню "Панель управления" -> "Телеграм"
    await dialog_manager.start(DashboardRemnashop.MAIN, mode=StartMode.RESET_STACK)


@inject
async def on_accept_features(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принять изменения и вернуться назад."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Accepted feature changes")
    # Возвращаемся на меню "Панель управления" -> "Телеграм"
    await dialog_manager.start(DashboardRemnashop.MAIN, mode=StartMode.RESET_STACK)

