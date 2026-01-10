from typing import Any

from aiogram_dialog import DialogManager
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from src.core.enums import SystemNotificationType, UserNotificationType
from src.services.settings import SettingsService


@inject
async def user_types_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    # Получаем список уведомлений из базы
    base_types = await settings_service.list_user_notifications()
    settings = await settings_service.get()
    global_enabled = settings.features.notifications_enabled
    
    # Сохраняем начальное состояние при первом входе
    if "initial_notifications_state" not in dialog_manager.dialog_data:
        dialog_manager.dialog_data["initial_notifications_state"] = {
            item["type"]: item["enabled"] for item in base_types
        }
    
    # Получаем временные изменения
    changes = dialog_manager.dialog_data.get("notifications_changes", {})
    
    # Применяем временные изменения к отображению
    result_types = []
    for item in base_types:
        type_value = item["type"]
        # Используем временное изменение если есть, иначе берем из базы
        enabled = changes.get(type_value, item["enabled"])
        # Если глобально выключено - все отображаются как выключенные
        if not global_enabled:
            enabled = False
        result_types.append({"type": item["type"], "enabled": enabled})
    
    return {"types": result_types}


@inject
async def system_types_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    # Получаем список уведомлений из базы
    base_types = await settings_service.list_system_notifications()
    settings = await settings_service.get()
    global_enabled = settings.features.notifications_enabled
    
    # Сохраняем начальное состояние при первом входе
    if "initial_notifications_state" not in dialog_manager.dialog_data:
        dialog_manager.dialog_data["initial_notifications_state"] = {
            item["type"]: item["enabled"] for item in base_types
        }
    
    # Получаем временные изменения
    changes = dialog_manager.dialog_data.get("notifications_changes", {})
    
    # Применяем временные изменения к отображению
    result_types = []
    for item in base_types:
        type_value = item["type"]
        # Используем временное изменение если есть, иначе берем из базы
        enabled = changes.get(type_value, item["enabled"])
        # Если глобально выключено - все отображаются как выключенные
        if not global_enabled:
            enabled = False
        result_types.append({"type": item["type"], "enabled": enabled})
    
    return {"types": result_types}
