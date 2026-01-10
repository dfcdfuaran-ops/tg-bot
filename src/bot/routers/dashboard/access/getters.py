from typing import Any

from aiogram_dialog import DialogManager
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from src.services.access import AccessService
from src.services.settings import SettingsService


@inject
async def access_getter(
    dialog_manager: DialogManager,
    access_service: FromDishka[AccessService],
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    settings = await settings_service.get()
    modes = await access_service.get_available_modes()
    
    # Сохраняем начальное состояние при первом входе
    if "initial_access_state" not in dialog_manager.dialog_data:
        dialog_manager.dialog_data["initial_access_state"] = {
            "access_mode": settings.access_mode,
            "purchases_allowed": settings.purchases_allowed,
            "registration_allowed": settings.registration_allowed,
        }
    
    # Проверяем есть ли временные изменения
    changes = dialog_manager.dialog_data.get("access_changes", {})
    
    # Используем временные изменения если есть, иначе берем из базы
    current_purchases = changes.get("purchases_allowed", settings.purchases_allowed)
    current_registration = changes.get("registration_allowed", settings.registration_allowed)
    current_mode = changes.get("mode", settings.access_mode)

    return {
        "purchases_allowed": current_purchases,
        "registration_allowed": current_registration,
        "access_mode": current_mode,
        "modes": modes,
    }


@inject
async def conditions_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    settings = await settings_service.get()

    return {
        "rules": settings.rules_required,
        "channel": settings.channel_required,
    }
