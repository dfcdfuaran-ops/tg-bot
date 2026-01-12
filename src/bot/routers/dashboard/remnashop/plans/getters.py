from decimal import Decimal
from typing import Any, Optional

from aiogram_dialog import DialogManager
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from remnapy import RemnawaveSDK
from remnapy.enums.users import TrafficLimitStrategy

from src.core.enums import Currency, PlanAvailability, PlanType
from src.core.utils.adapter import DialogDataAdapter
from src.infrastructure.database.models.dto import PlanDto, PlanDurationDto, PlanPriceDto
from src.services.plan import PlanService


@inject
async def plans_getter(
    dialog_manager: DialogManager,
    plan_service: FromDishka[PlanService],
    **kwargs: Any,
) -> dict[str, Any]:
    plans: list[PlanDto] = await plan_service.get_all()
    formatted_plans = [
        {
            "id": plan.id,
            "name": plan.name,
            "is_active": plan.is_active,
        }
        for plan in plans
    ]

    return {
        "plans": formatted_plans,
    }


@inject
async def configurator_getter(
    dialog_manager: DialogManager,
    remnawave: FromDishka[RemnawaveSDK],
    **kwargs: Any,
) -> dict[str, Any]:
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)
    is_new_plan = plan is None

    # Получаем информацию о сквадах заранее для установки по умолчанию
    internal_dict = {}
    external_dict = {}
    first_internal_squad = None
    
    try:
        internal_response = await remnawave.internal_squads.get_internal_squads()
        internal_dict = {s.uuid: s.name for s in internal_response.internal_squads}
        if internal_response.internal_squads:
            first_internal_squad = internal_response.internal_squads[0].uuid
        
        external_response = await remnawave.external_squads.get_external_squads()
        external_dict = {s.uuid: s.name for s in external_response.external_squads}
    except Exception:
        pass

    if plan is None:
        # Создаем пустой план без предзаполненных значений
        plan = PlanDto(
            internal_squads=[],
            external_squad=None,
            durations=[],
        )
        adapter.save(plan)

    # Get squads display names
    internal_squads_names = "Не назначен"
    external_squad_name = "Не назначен"

    # Используем pending_internal_squads если есть, иначе plan.internal_squads
    pending_internal = dialog_manager.dialog_data.get("pending_internal_squads")
    current_internal_squads = pending_internal if pending_internal is not None else plan.internal_squads
    
    if current_internal_squads:
        # Убираем дубликаты используя dict.fromkeys() для сохранения порядка
        unique_squads = list(dict.fromkeys(current_internal_squads))
        squads_list = [internal_dict.get(squad, str(squad)) for squad in unique_squads if squad in internal_dict]
        if squads_list:
            internal_squads_names = ", ".join(squads_list)
    
    # Используем pending_external_squad если есть
    pending_external = dialog_manager.dialog_data.get("pending_external_squad")
    current_external_squad = pending_external if pending_external is not None else plan.external_squad
    
    if current_external_squad:
        for squad_uuid in current_external_squad:
            if squad_uuid in external_dict:
                external_squad_name = external_dict[squad_uuid]
                break

    # Используем pending значения если они есть, иначе текущие значения плана
    plan_name = dialog_manager.dialog_data.get("pending_plan_name", plan.name)
    plan_description = dialog_manager.dialog_data.get("pending_plan_description", plan.description)
    plan_type = dialog_manager.dialog_data.get("pending_plan_type", plan.type)
    plan_availability = dialog_manager.dialog_data.get("pending_plan_availability", plan.availability)
    plan_tag = dialog_manager.dialog_data.get("pending_tag", plan.tag)

    helpers = {
        "is_edit": dialog_manager.dialog_data.get("is_edit", False),
        "is_unlimited_traffic": plan.is_unlimited_traffic,
        "is_unlimited_devices": plan.is_unlimited_devices,
        "plan_type": plan_type,
        "availability_type": plan_availability,
        "tag": plan_tag or "NOTAG",
        "internal_squads": internal_squads_names,
        "external_squad": external_squad_name,
    }

    data = plan.model_dump()
    # Обновляем данные с учетом pending значений
    data["name"] = plan_name
    data["description"] = plan_description
    data["type"] = plan_type
    data["availability"] = plan_availability
    data["tag"] = plan_tag
    data.update(helpers)
    return data


async def name_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    # Используем pending_plan_name если был введен, иначе текущее имя плана
    name = dialog_manager.dialog_data.get("pending_plan_name")
    if name is None:
        name = plan.name or False
    
    return {"name": name}


async def description_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    # Используем pending_plan_description если было введено, иначе текущее описание
    description = dialog_manager.dialog_data.get("pending_plan_description")
    if description is None:
        description = plan.description or False
    
    return {"description": description}


async def tag_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    # Используем pending_tag если был введен, иначе текущий тег плана
    tag = dialog_manager.dialog_data.get("pending_tag")
    if tag is None:
        tag = plan.tag or "NOTAG"
    
    return {"tag": tag}


async def type_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    # Проверяем pending или текущее значение
    pending_type = dialog_manager.dialog_data.get("pending_plan_type")
    current_type = PlanType(pending_type) if pending_type else plan.type

    types = [
        {
            "type": t,
            "selected": t == current_type,
        }
        for t in PlanType
    ]

    return {"types": types}


async def availability_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    # Проверяем pending или текущее значение
    pending_avail = dialog_manager.dialog_data.get("pending_plan_availability")
    current_avail = PlanAvailability(pending_avail) if pending_avail else plan.availability

    availability = [
        {
            "avail": a,
            "selected": a == current_avail,
        }
        for a in PlanAvailability
    ]

    return {"availability": availability}


async def traffic_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    strategys = [
        {
            "strategy": strategy,
            "selected": strategy.name == plan.traffic_limit_strategy,
        }
        for strategy in TrafficLimitStrategy
    ]

    return {"strategys": strategys}


async def durations_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    durations = [duration.model_dump() for duration in plan.durations]

    return {
        "deletable": len(durations) > 1,
        "durations": durations,
    }


def get_prices_for_duration(
    durations: list[PlanDurationDto],
    target_days: int,
) -> Optional[list[PlanPriceDto]]:
    for duration in durations:
        if duration.days == target_days:
            return duration.prices
    return []


async def prices_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    selected_duration = dialog_manager.dialog_data["selected_duration"]
    prices = get_prices_for_duration(plan.durations, selected_duration)
    
    # Показываем только RUB - остальные будут конвертироваться автоматически
    rub_price = next((p for p in prices if p.currency == Currency.RUB), None) if prices else None
    prices_data = [rub_price.model_dump()] if rub_price else []

    return {
        "duration": selected_duration,
        "prices": prices_data,
    }


async def price_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    selected_duration = dialog_manager.dialog_data.get("selected_duration")
    selected_currency = dialog_manager.dialog_data.get("selected_currency")
    return {
        "duration": selected_duration,
        "currency": selected_currency,
    }


async def allowed_users_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    return {"allowed_users": plan.allowed_user_ids if plan.allowed_user_ids else []}


@inject
async def squads_getter(
    dialog_manager: DialogManager,
    remnawave: FromDishka[RemnawaveSDK],
    **kwargs: Any,
) -> dict[str, Any]:
    from loguru import logger
    from src.core.constants import USER_KEY
    from src.core.utils.formatters import format_user_log as log
    
    user = dialog_manager.middleware_data.get(USER_KEY)
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    # Save original state if not already saved
    if "saved_internal_squads" not in dialog_manager.dialog_data:
        dialog_manager.dialog_data["saved_internal_squads"] = list(plan.internal_squads) if plan.internal_squads else []
        logger.debug(f"{log(user)} Saved original internal squads: {plan.internal_squads}")
    
    if "saved_external_squad" not in dialog_manager.dialog_data:
        dialog_manager.dialog_data["saved_external_squad"] = list(plan.external_squad) if plan.external_squad else None
        logger.debug(f"{log(user)} Saved original external squad: {plan.external_squad}")

    internal_response = await remnawave.internal_squads.get_internal_squads()
    # Use string keys for compatibility with serialized pending values
    internal_dict = {str(s.uuid): s.name for s in internal_response.internal_squads}
    
    # Используем pending_internal_squads если есть, иначе plan.internal_squads
    pending_internal = dialog_manager.dialog_data.get("pending_internal_squads")
    current_internal_squads = pending_internal if pending_internal is not None else plan.internal_squads
    
    logger.debug(
        f"{log(user)} squads_getter: plan.internal_squads={plan.internal_squads}, "
        f"pending_internal={pending_internal}, current={current_internal_squads}"
    )
    
    internal_squads_names = "Не назначен"
    if current_internal_squads:
        unique_squads = list(dict.fromkeys(current_internal_squads))
        # Convert all to strings for comparison
        squads_list = []
        for squad in unique_squads:
            squad_str = str(squad)
            if squad_str in internal_dict:
                squads_list.append(internal_dict[squad_str])
        
        if squads_list:
            internal_squads_names = ", ".join(squads_list)
        else:
            logger.warning(f"{log(user)} Internal squads exist but not found in remnawave: {unique_squads}")

    external_response = await remnawave.external_squads.get_external_squads()
    # Use string keys for compatibility with serialized pending values
    external_dict = {str(s.uuid): s.name for s in external_response.external_squads}
    
    # Используем pending_external_squad если есть (проверяем наличие ключа, а не значение)
    if "pending_external_squad" in dialog_manager.dialog_data:
        current_external_squad = dialog_manager.dialog_data["pending_external_squad"]
    else:
        current_external_squad = plan.external_squad
    
    logger.debug(
        f"{log(user)} squads_getter: plan.external_squad={plan.external_squad}, "
        f"pending_external_squad key exists={'pending_external_squad' in dialog_manager.dialog_data}, "
        f"current={current_external_squad}"
    )
    
    external_squad_name = "Не назначен"
    if current_external_squad:
        for squad_uuid in current_external_squad:
            # Convert to string for comparison
            squad_str = str(squad_uuid)
            if squad_str in external_dict:
                external_squad_name = external_dict[squad_str]
                break
        if external_squad_name == "Не назначен":
            logger.warning(f"{log(user)} External squad exists but not found in remnawave: {current_external_squad}")

    logger.debug(f"{log(user)} squads_getter result: internal={internal_squads_names}, external={external_squad_name}")

    return {
        "internal_squads": internal_squads_names,
        "external_squad": external_squad_name,
    }


@inject
async def internal_squads_getter(
    dialog_manager: DialogManager,
    remnawave: FromDishka[RemnawaveSDK],
    **kwargs: Any,
) -> dict[str, Any]:
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    result = await remnawave.internal_squads.get_internal_squads()
    existing_squad_uuids = {squad.uuid for squad in result.internal_squads}

    # Clean invalid squads from plan (like old version - intersection approach)
    if plan.internal_squads:
        plan_squad_uuids_set = set(plan.internal_squads)
        valid_squad_uuids_set = plan_squad_uuids_set.intersection(existing_squad_uuids)
        
        # Save cleaned list if it changed
        cleaned_list = list(valid_squad_uuids_set)
        if sorted(plan.internal_squads) != sorted(cleaned_list):
            plan.internal_squads = cleaned_list
            adapter.save(plan)
    else:
        # Initialize if None
        plan.internal_squads = []
    
    # Use plan's current squads (changes are saved immediately in handler)
    current_squads = plan.internal_squads if plan.internal_squads else []

    squads = [
        {
            "index": idx,
            "uuid": squad.uuid,
            "name": squad.name,
            "selected": 1 if squad.uuid in current_squads else 0,
        }
        for idx, squad in enumerate(result.internal_squads)
    ]

    # Save squads to dialog_data for handler to use
    dialog_manager.dialog_data["squads"] = squads

    return {
        "squads": squads,
    }


@inject
async def external_squads_getter(
    dialog_manager: DialogManager,
    remnawave: FromDishka[RemnawaveSDK],
    **kwargs: Any,
) -> dict[str, Any]:
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    result = await remnawave.external_squads.get_external_squads()
    existing_squad_uuids = {squad.uuid for squad in result.external_squads}

    # Check if stored external_squad UUIDs still exist
    if plan.external_squad:
        plan.external_squad = [uuid for uuid in plan.external_squad if uuid in existing_squad_uuids] or None

    adapter.save(plan)

    # Get pending squad or use current
    # Check if pending_external_squad key exists in dialog_data (even if value is None)
    if "pending_external_squad" in dialog_manager.dialog_data:
        current_squad = dialog_manager.dialog_data["pending_external_squad"]
    else:
        current_squad = plan.external_squad
    
    squads = [
        {
            "uuid": squad.uuid,
            "name": squad.name,
            "selected": True if current_squad and squad.uuid in current_squad else False,
        }
        for squad in result.external_squads
    ]

    return {
        "squads": squads,
    }
