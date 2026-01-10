from typing import Any

from aiogram_dialog import DialogManager
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from src.services.settings import SettingsService


@inject
async def features_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна настроек функционала."""
    features = await settings_service.get_feature_settings()
    
    # Сохраняем начальные значения при первом входе
    if "initial_features" not in dialog_manager.dialog_data:
        dialog_manager.dialog_data["initial_features"] = {
            "community_enabled": features.community_enabled,
            "tos_enabled": features.tos_enabled,
            "balance_enabled": features.balance_enabled,
            "extra_devices_enabled": features.extra_devices.enabled,
            "extra_devices_price": features.extra_devices.price_per_device,
            "transfers_enabled": features.transfers.enabled,
        }
    
    return {
        "community_enabled": 1 if features.community_enabled else 0,
        "tos_enabled": 1 if features.tos_enabled else 0,
        "balance_enabled": 1 if features.balance_enabled else 0,
        "extra_devices_enabled": 1 if features.extra_devices.enabled else 0,
        "transfers_enabled": 1 if features.transfers.enabled else 0,
    }
