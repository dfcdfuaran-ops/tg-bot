from typing import Any

from aiogram_dialog import DialogManager
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from src.__version__ import __version__
from src.core.config import AppConfig
from src.core.enums import UserRole
from src.infrastructure.database.models.dto import UserDto
from src.services.settings import SettingsService
from src.services.user import UserService


@inject
async def remnashop_getter(
    dialog_manager: DialogManager,
    config: AppConfig,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    features = await settings_service.get_feature_settings()
    return {
        "version": __version__,
        "extra_devices_enabled": 1 if features.extra_devices.enabled else 0,
    }


@inject
async def admins_getter(
    dialog_manager: DialogManager,
    config: AppConfig,
    user_service: FromDishka[UserService],
    **kwargs: Any,
) -> dict[str, Any]:
    devs: list[UserDto] = await user_service.get_by_role(role=UserRole.DEV)
    admins: list[UserDto] = await user_service.get_by_role(role=UserRole.ADMIN)
    all_users = devs + admins

    users_dicts = [
        {
            "user_id": user.telegram_id,
            "user_name": user.name,
            "deletable": user.telegram_id != config.bot.dev_id,
        }
        for user in all_users
    ]

    return {"admins": users_dicts}


@inject
async def extra_devices_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна настроек доп. устройств."""
    features = await settings_service.get_feature_settings()
    
    # Если есть pending изменение типа оплаты, используем его
    pending_payment_type = dialog_manager.dialog_data.get("pending_payment_type")
    is_one_time = pending_payment_type if pending_payment_type is not None else features.extra_devices.is_one_time
    
    return {
        "extra_devices_price": features.extra_devices.price_per_device,
        "is_one_time": 1 if is_one_time else 0,
        "is_monthly": 0 if is_one_time else 1,
    }



@inject
async def extra_devices_price_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна изменения стоимости доп. устройств."""
    features = await settings_service.get_feature_settings()
    
    # Если есть pending изменение цены, показываем его
    pending_price = dialog_manager.dialog_data.get("pending_price")
    current_price = pending_price if pending_price is not None else features.extra_devices.price_per_device
    
    return {
        "current_price": current_price,
        "selected_price": current_price,  # Используется для выделения выбранной кнопки
    }


