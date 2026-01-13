from typing import Any

from aiogram_dialog import DialogManager
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from src.core.enums import (
    ReferralAccrualStrategy,
    ReferralLevel,
    ReferralRewardStrategy,
    ReferralRewardType,
)
from src.infrastructure.database.models.dto import UserDto
from src.services.settings import SettingsService


def _ensure_initialized(dialog_manager: DialogManager, settings) -> dict:
    """
    Гарантировать инициализацию данных при первом входе.
    Паттерн как в Переводах - загружаем начальные и текущие значения.
    """
    if "current_referral" not in dialog_manager.dialog_data:
        # Загружаем из settings
        reward_config = settings.reward.config
        first_level_reward = reward_config.get(ReferralLevel.FIRST, 0)
        second_level_reward = reward_config.get(ReferralLevel.SECOND, 0)
        
        initial = {
            "level": settings.level.value,
            "reward_type": settings.reward.type.value,
            "accrual_strategy": settings.accrual_strategy.value,
            "reward_strategy": settings.reward.strategy.value,
            "reward_level_1": first_level_reward,
            "reward_level_2": second_level_reward,
            "editing_level": 1,  # По умолчанию редактируем первый уровень
        }
        
        dialog_manager.dialog_data["initial_referral"] = initial.copy()
        dialog_manager.dialog_data["current_referral"] = initial.copy()
    
    return dialog_manager.dialog_data["current_referral"]


@inject
async def referral_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для главного меню реферальной системы."""
    settings = await settings_service.get_referral_settings()
    current = _ensure_initialized(dialog_manager, settings)
    
    # Используем текущие значения из dialog_data, с защитой от None
    level_val = current.get("level") or settings.level.value
    reward_type_val = current.get("reward_type") or settings.reward.type.value
    accrual_strategy_val = current.get("accrual_strategy") or settings.accrual_strategy.value
    reward_strategy_val = current.get("reward_strategy") or settings.reward.strategy.value
    
    level = ReferralLevel(level_val)
    reward_type = ReferralRewardType(reward_type_val)
    accrual_strategy = ReferralAccrualStrategy(accrual_strategy_val)
    reward_strategy = ReferralRewardStrategy(reward_strategy_val)
    
    # Текстовое отображение уровней
    level_text = "Один" if level.value == 1 else "Два"
    
    # Получаем награды для обоих уровней
    reward_level_1 = int(current.get("reward_level_1") or 0)
    reward_level_2 = int(current.get("reward_level_2") or 0)
    
    # Функция для форматирования награды
    def format_reward(value: int) -> str:
        if value == 0:
            return "Без награды"
        elif reward_strategy == ReferralRewardStrategy.PERCENT:
            return f"{value}%"
        else:
            # Для фиксированной награды
            if reward_type == ReferralRewardType.MONEY:
                return f"{value} ₽"
            else:  # EXTRA_DAYS
                return f"{value} дн."
    
    # Форматируем отображение награды в зависимости от количества уровней
    if level.value == 1:
        reward_display = format_reward(reward_level_1)
    else:  # 2 уровня
        reward_display = f"1 ур: {format_reward(reward_level_1)} • 2 ур: {format_reward(reward_level_2)}"

    return {
        "is_enable": settings.enable,
        "referral_level": level.value,
        "level_text": level_text,
        "reward_type": reward_type,
        "accrual_strategy_type": accrual_strategy,
        "reward_strategy_type": reward_strategy,
        "reward_display": reward_display,
    }


@inject
async def level_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна выбора уровня."""
    settings = await settings_service.get_referral_settings()
    current = _ensure_initialized(dialog_manager, settings)
    
    # Текущий или временно выбранный уровень
    current_level = int(current.get("level") or settings.level.value)
    
    return {
        "current_level": current_level,
        # Возвращаем числа, как в Переводах
        "level_one_selected": 1 if current_level == 1 else 0,
        "level_two_selected": 1 if current_level == 2 else 0,
    }


@inject
async def reward_type_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна выбора типа награды."""
    settings = await settings_service.get_referral_settings()
    current = _ensure_initialized(dialog_manager, settings)
    
    current_type = current.get("reward_type", settings.reward.type.value)
    
    return {
        "current_type": current_type,
        # Возвращаем числа, как в Переводах
        "type_money_selected": 1 if current_type == ReferralRewardType.MONEY.value else 0,
        "type_days_selected": 1 if current_type == ReferralRewardType.EXTRA_DAYS.value else 0,
    }


@inject
async def accrual_strategy_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна выбора условия начисления."""
    settings = await settings_service.get_referral_settings()
    current = _ensure_initialized(dialog_manager, settings)
    
    current_strategy = current.get("accrual_strategy", settings.accrual_strategy.value)
    
    return {
        "current_strategy": current_strategy,
        # Возвращаем числа, как в Переводах
        "accrual_first_selected": 1 if current_strategy == ReferralAccrualStrategy.ON_FIRST_PAYMENT.value else 0,
        "accrual_each_selected": 1 if current_strategy == ReferralAccrualStrategy.ON_EACH_PAYMENT.value else 0,
    }


@inject
async def reward_strategy_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна выбора формы начисления."""
    settings = await settings_service.get_referral_settings()
    current = _ensure_initialized(dialog_manager, settings)
    
    current_strategy = current.get("reward_strategy", settings.reward.strategy.value)
    
    return {
        "current_strategy": current_strategy,
        # Возвращаем числа, как в Переводах
        "strategy_fixed_selected": 1 if current_strategy == ReferralRewardStrategy.AMOUNT.value else 0,
        "strategy_percent_selected": 1 if current_strategy == ReferralRewardStrategy.PERCENT.value else 0,
    }


@inject
async def reward_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна выбора награды."""
    settings = await settings_service.get_referral_settings()
    current = _ensure_initialized(dialog_manager, settings)
    
    # Получаем текущую или временную стратегию
    reward_strategy = ReferralRewardStrategy(current.get("reward_strategy") or settings.reward.strategy.value)
    reward_type = ReferralRewardType(current.get("reward_type") or settings.reward.type.value)
    current_level = int(current.get("level") or settings.level.value)
    editing_level = int(current.get("editing_level") or 1)
    
    # Получаем награды для обоих уровней
    reward_level_1 = int(current.get("reward_level_1") or 0)
    reward_level_2 = int(current.get("reward_level_2") or 0)
    
    # Текущая редактируемая награда
    current_reward = reward_level_1 if editing_level == 1 else reward_level_2
    
    is_percent = reward_strategy == ReferralRewardStrategy.PERCENT
    is_fixed = reward_strategy == ReferralRewardStrategy.AMOUNT
    
    # Суффикс для фиксированных кнопок
    if reward_type == ReferralRewardType.MONEY:
        reward_suffix = "₽"
    else:
        reward_suffix = ""  # Для EXTRA_DAYS суффикса нет

    # Формируем строки для отображения наград
    def format_reward(value: int) -> str:
        if value == 0:
            return "Без награды"
        elif is_percent:
            return f"{value}% от суммы платежа"
        else:
            if reward_type == ReferralRewardType.MONEY:
                return f"{value} ₽"
            else:
                return f"{value} дн."
    
    # Создаем строку с наградами
    if current_level == 1:
        reward_string = f"1 уровень: {format_reward(reward_level_1)}"
        show_level_switch = False
    else:  # 2 уровня
        reward_string = f"1 уровень: {format_reward(reward_level_1)}\n2 уровень: {format_reward(reward_level_2)}"
        show_level_switch = True

    # Генерируем selected для кнопок - возвращаем числа
    result = {
        "reward": reward_string,
        "reward_type": reward_type,
        "reward_strategy_type": reward_strategy,
        "is_percent": is_percent,
        "is_fixed": is_fixed,
        "is_extra_days": 1 if (is_fixed and reward_type == ReferralRewardType.EXTRA_DAYS) else 0,
        "is_money_fixed": 1 if (is_fixed and reward_type == ReferralRewardType.MONEY) else 0,
        "reward_suffix": reward_suffix,
        "current_reward": current_reward,
        "show_level_switch": show_level_switch,
        "editing_level_one": 1 if editing_level == 1 else 0,
        "editing_level_two": 1 if editing_level == 2 else 0,
        # Кнопка "Без награды"
        "reward_0_selected": 1 if current_reward == 0 else 0,
    }
    
    # Для процентных кнопок (5-50%)
    for val in [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]:
        result[f"reward_{val}_selected"] = 1 if current_reward == val else 0
    
    # Для фиксированных кнопок - разные значения для денег и дней
    if reward_type == ReferralRewardType.MONEY:
        # Для денег: 10, 20, 30, 50, 100, 150, 200, 250, 300, 500
        for val in [10, 20, 30, 50, 100, 150, 200, 250, 300, 500]:
            result[f"reward_{val}_selected"] = 1 if current_reward == val else 0
    else:
        # Для дней: 1-15
        for val in range(1, 16):
            result[f"reward_{val}_selected"] = 1 if current_reward == val else 0
    
    return result


@inject
async def invite_message_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для настройки сообщения приглашения."""
    settings = await settings_service.get_referral_settings()
    
    current_message = settings.invite_message
    # Скрываем {space} префикс из отображения (но он остается в сохраняемом сообщении)
    if current_message.startswith("{space}"):
        display_message = current_message[7:]  # Убираем "{space}" (7 символов)
    else:
        display_message = current_message
    
    return {
        "current_message": display_message,
    }


@inject
async def invite_preview_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    user: UserDto,
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для предпросмотра сообщения приглашения."""
    settings = await settings_service.get_referral_settings()
    
    invite_message_template = settings.invite_message
    # Форматируем сообщение с примерными значениями
    preview_message = invite_message_template.format(
        name="VPN",
        url=f"https://t.me/bot?start={user.referral_code}",
        space="\n",
    )
    # Скрываем {space} префикс из отображения
    if invite_message_template.startswith("{space}"):
        display_message = invite_message_template[7:]  # Убираем "{space}" (7 символов)
    else:
        display_message = invite_message_template
    
    return {
        "current_message": display_message,
        "preview_message": preview_message,
    }
