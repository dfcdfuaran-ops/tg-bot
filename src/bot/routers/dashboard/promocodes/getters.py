from typing import Any

from aiogram_dialog import DialogManager
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from fluentogram import TranslatorRunner
from loguru import logger

from src.core.enums import PromocodeRewardType
from src.core.utils.adapter import DialogDataAdapter
from src.core.utils.formatters import i18n_format_days, i18n_format_limit, i18n_format_traffic_limit
from src.infrastructure.database.models.dto import PromocodeDto
from src.services.promocode import PromocodeService
from src.services.plan import PlanService


# Типы промокодов для отображения пользователю
DISPLAY_TYPES = [
    PromocodeRewardType.PURCHASE_DISCOUNT,  # Одноразовая скидка
    PromocodeRewardType.PERSONAL_DISCOUNT,  # Постоянная скидка
    PromocodeRewardType.DURATION,           # Дни к подписке
]


class PromocodeListItem:
    """Вспомогательный класс для отображения промокодов в списке."""
    
    def __init__(self, promocode: PromocodeDto):
        self.id = promocode.id
        self.code = promocode.code
        self.name = promocode.name
        self.is_active = promocode.is_active
        self.reward_type = promocode.reward_type
        self.activations_count = len(promocode.activations)
        self.max_activations = promocode.max_activations
        
    @property
    def display_text(self) -> str:
        if self.max_activations is None:
            usage = f"{self.activations_count}/∞"
        else:
            usage = f"{self.activations_count}/{self.max_activations}"
        
        # Показываем название, если есть, иначе код
        display_name = self.name if self.name else self.code
        return f"{display_name} ({usage})"
    
    @property
    def status_emoji(self) -> str:
        """Возвращает эмодзи статуса: 🟢 если активен, 🔴 если отключен."""
        return "🟢" if self.is_active else "🔴"


@inject
async def list_getter(
    dialog_manager: DialogManager,
    promocode_service: FromDishka[PromocodeService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для списка промокодов."""
    promocodes = await promocode_service.get_all()
    
    items = [PromocodeListItem(p) for p in promocodes]
    
    return {
        "promocodes": items,
        "count": len(items),
    }


async def view_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Геттер для просмотра промокода."""
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if promocode is None:
        raise ValueError("PromocodeDto not found in dialog data")
    
    data = promocode.model_dump()
    
    # Форматирование награды
    if promocode.reward:
        if promocode.reward_type == PromocodeRewardType.DURATION:
            reward = i18n_format_days(promocode.reward)
            data.update({"reward": reward})
        elif promocode.reward_type == PromocodeRewardType.TRAFFIC:
            reward = i18n_format_traffic_limit(promocode.reward)
            data.update({"reward": reward})
    
    helpers = {
        "promocode_type": promocode.reward_type,
        "max_activations": i18n_format_limit(promocode.max_activations),
        "lifetime": i18n_format_days(promocode.lifetime),
        "activations_count": len(promocode.activations),
        "is_edit": dialog_manager.dialog_data.get("is_edit", False),
    }
    
    data.update(helpers)
    
    return data


async def configurator_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Геттер для конфигуратора промокода."""
    logger.info(f"🔍 configurator_getter called, dialog_data keys: {list(dialog_manager.dialog_data.keys())}")
    logger.info(f"🔍 configurator_getter: 'promocodedto' in dialog_data = {'promocodedto' in dialog_manager.dialog_data}")
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    logger.info(f"🔍 After adapter.load(), promocode is None: {promocode is None}")
    
    if promocode is None:
        logger.warning(f"🔍 DEBUG: promocode is None in configurator_getter, creating new one")
        promocode = PromocodeDto()
        promocode.code = PromocodeDto.generate_code(length=7)
        adapter.save(promocode)
    else:
        logger.info(f"🔍 DEBUG: promocode loaded successfully, code={promocode.code}, lifetime={promocode.lifetime}, reward={promocode.reward}")

    data = promocode.model_dump()

    if promocode.reward:
        if promocode.reward_type == PromocodeRewardType.DURATION:
            reward = i18n_format_days(promocode.reward)
            data.update({"reward": reward})
        elif promocode.reward_type == PromocodeRewardType.TRAFFIC:
            reward = i18n_format_traffic_limit(promocode.reward)
            data.update({"reward": reward})

    helpers = {
        "promocode_type": promocode.reward_type.value if promocode.reward_type else None,
        "max_activations": i18n_format_limit(promocode.max_activations),
        "lifetime": i18n_format_days(promocode.lifetime),
        "is_edit": dialog_manager.dialog_data.get("is_edit", False),
    }

    if promocode.plan:
        plan = {
            "plan_name": promocode.plan.name,
            "plan_type": promocode.plan.type,
            "plan_traffic_limit": promocode.plan.traffic_limit,
            "plan_device_limit": promocode.plan.device_limit,
            "plan_duration": promocode.plan.duration,
        }
        data.update(plan)

    data.update(helpers)

    return data


@inject
async def type_getter(
    dialog_manager: DialogManager,
    i18n: FromDishka[TranslatorRunner],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для выбора типа промокода."""
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    types = [
        {
            "type": reward_type,
            "name": i18n.get("promocode-type-name", type=reward_type.value),
            "selected": 1 if reward_type == promocode.reward_type else 0,
        }
        for reward_type in DISPLAY_TYPES
    ]
    
    return {"types": types}


@inject
async def access_getter(
    dialog_manager: DialogManager,
    plan_service: FromDishka[PlanService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для выбора доступных тарифных планов для промокода."""
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    try:
        # Получаем все тарифные планы
        all_plans = await plan_service.get_all()
        
        # Фильтруем только активные
        plans = [plan for plan in all_plans if plan.is_active]
        
        # Получаем ID планов которые уже выбраны для этого промокода
        allowed_plan_ids = promocode.allowed_plan_ids if promocode.allowed_plan_ids else []
        active_plan_ids = [plan.id for plan in plans if plan.id is not None]
        
        # Проверяем, все ли планы выбраны
        all_selected = set(allowed_plan_ids) == set(active_plan_ids) and len(active_plan_ids) > 0
        
        plans_list = [
            {
                "plan_id": plan.id,
                "plan_name": plan.name,
                "selected": 1 if plan.id in allowed_plan_ids else 0,
            }
            for plan in plans
        ]
        
        return {
            "plans": plans_list,
            "all_selected": 1 if all_selected else 0,
        }
    except Exception as e:
        logger.error(f"Error in access_getter: {e}")
        return {"plans": [], "all_selected": 0}

