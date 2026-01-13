from decimal import Decimal
from typing import Optional
from uuid import UUID

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager, ShowMode, StartMode, SubManager
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Select
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from loguru import logger
from remnapy import RemnawaveSDK
from remnapy.enums.users import TrafficLimitStrategy

from src.bot.states import RemnashopPlans
from src.core.config import AppConfig
from src.core.constants import TAG_REGEX, USER_KEY
from src.core.enums import Currency, PlanAvailability, PlanType, SubscriptionStatus
from src.core.utils.adapter import DialogDataAdapter
from src.core.utils.formatters import format_user_log as log
from src.core.utils.message_payload import MessagePayload
from src.core.utils.validators import is_double_click, parse_int
from src.infrastructure.database.models.dto import PlanDto, PlanDurationDto, PlanPriceDto, UserDto
from src.infrastructure.taskiq.tasks.redirects import redirect_to_main_menu_task
from src.services.notification import NotificationService
from src.services.plan import PlanService
from src.services.pricing import PricingService
from src.services.remnawave import RemnawaveService
from src.services.subscription import SubscriptionService
from src.services.user import UserService


async def on_plan_create(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход к созданию нового плана с очисткой всех данных."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Started creating new plan")
    
    # Очищаем все служебные флаги и данные плана
    dialog_manager.dialog_data.pop("is_edit", None)
    dialog_manager.dialog_data.pop("original_plan", None)
    dialog_manager.dialog_data.pop("pending_plan_name", None)
    dialog_manager.dialog_data.pop("pending_plan_description", None)
    dialog_manager.dialog_data.pop("pending_plan_type", None)
    dialog_manager.dialog_data.pop("pending_internal_squads", None)
    dialog_manager.dialog_data.pop("pending_external_squad", None)
    # Очищаем сохранённый план (ключ от DialogDataAdapter)
    dialog_manager.dialog_data.pop("plandto", None)
    
    await dialog_manager.switch_to(state=RemnashopPlans.CONFIGURATOR)


@inject
async def on_plan_select(
    callback: CallbackQuery,
    widget: Button,
    sub_manager: SubManager,
    plan_service: FromDishka[PlanService],
) -> None:
    user: UserDto = sub_manager.middleware_data[USER_KEY]
    plan: Optional[PlanDto] = await plan_service.get(plan_id=int(sub_manager.item_id))

    if not plan:
        raise ValueError(f"Attempted to select non-existent plan '{sub_manager.item_id}'")

    logger.info(f"{log(user)} Selected plan ID '{plan.id}'")

    adapter = DialogDataAdapter(sub_manager.manager)
    adapter.save(plan)
    
    # Сохраняем оригинальную копию плана для возможности отмены изменений
    import copy
    sub_manager.manager.dialog_data["original_plan"] = copy.deepcopy(plan.model_dump())

    sub_manager.manager.dialog_data["is_edit"] = True
    await sub_manager.switch_to(state=RemnashopPlans.CONFIGURATOR)


@inject
async def on_plan_move(
    callback: CallbackQuery,
    widget: Button,
    sub_manager: SubManager,
    plan_service: FromDishka[PlanService],
) -> None:
    await sub_manager.load_data()
    user: UserDto = sub_manager.middleware_data[USER_KEY]
    plan_id = int(sub_manager.item_id)

    moved = await plan_service.move_plan_up(plan_id)
    if moved:
        logger.info(f"{log(user)} Moved plan '{plan_id}' up successfully")
    else:
        logger.warning(f"{log(user)} Failed to move plan '{plan_id}' up")


@inject
async def on_plan_delete(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: SubManager,
    notification_service: FromDishka[NotificationService],
    plan_service: FromDishka[PlanService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]

    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    if is_double_click(dialog_manager, key=f"delete_confirm_{plan.id}", cooldown=10):
        await plan_service.delete(plan.id)  # type: ignore[arg-type]
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-deleted-success"),
        )
        logger.info(f"{log(user)} Deleted plan ID '{plan.id}'")
        await dialog_manager.start(state=RemnashopPlans.MAIN, mode=StartMode.RESET_STACK)
        return

    await notification_service.notify_user(
        user=user,
        payload=MessagePayload(i18n_key="ntf-double-click-confirm"),
    )
    logger.debug(f"{log(user)} Clicked delete for plan ID '{plan.id}' (awaiting confirmation)")


@inject
async def on_name_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
    plan_service: FromDishka[PlanService],
) -> None:
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.debug(f"{log(user)} Attempted to set plan name")

    if message.text is None:
        logger.warning(f"{log(user)} Provided empty plan name input")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-invalid-name"),
        )
        return

    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    # Проверка на дубликат только если это новое имя (не для нового плана или если имя изменилось)
    existing_plan = await plan_service.get_by_name(plan_name=message.text)
    if existing_plan and (not plan.id or existing_plan.id != plan.id):
        logger.warning(f"{log(user)} Tried to set duplicate plan name '{message.text}'")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-invalid-name"),
        )
        return

    # Сохраняем имя в pending
    dialog_manager.dialog_data["pending_plan_name"] = message.text

    logger.info(f"{log(user)} Successfully set pending name to '{message.text}'")
    await dialog_manager.switch_to(state=RemnashopPlans.CONFIGURATOR)


@inject
async def on_description_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
) -> None:
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.debug(f"{log(user)} Attempted to set plan description")

    if message.text is None:
        logger.warning(f"{log(user)} Provided empty plan description input")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-invalid-description"),
        )
        return

    # Сохраняем описание в pending
    dialog_manager.dialog_data["pending_plan_description"] = message.text

    logger.info(f"{log(user)} Successfully set pending description")
    await dialog_manager.switch_to(state=RemnashopPlans.CONFIGURATOR)


async def on_description_delete(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    plan.description = None
    adapter.save(plan)
    logger.info(f"{log(user)} Successfully removed plan description")


@inject
async def on_tag_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
) -> None:
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.debug(f"{log(user)} Attempted to set plan tag")

    if message.text is None:
        logger.warning(f"{log(user)} Provided empty plan tag input")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-invalid-tag"),
        )
        return

    tag = message.text.strip()

    if not TAG_REGEX.fullmatch(tag):
        logger.warning(f"{log(user)} Invalid plan tag input: '{tag}'")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-invalid-tag"),
        )
        return

    # Сохраняем тег в pending, а не сразу в план
    dialog_manager.dialog_data["pending_tag"] = tag
    
    logger.info(f"{log(user)} Successfully set pending tag to '{tag}'")


async def on_cancel_tag(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена введенного тега - возврат в конфигуратор без сохранения."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Очищаем временный тег и возвращаемся в конфигуратор
    dialog_manager.dialog_data.pop("pending_tag", None)
    await dialog_manager.switch_to(RemnashopPlans.CONFIGURATOR)
    logger.info(f"{log(user)} Cancelled tag input")


async def on_accept_tag(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Применение введенного тега - возвращаемся в конфигуратор, pending_tag уже сохранен."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Тег уже сохранен в pending_tag через on_tag_input
    # Он будет применен при финальном "Принять" в on_confirm_plan
    pending_tag = dialog_manager.dialog_data.get("pending_tag")
    
    await dialog_manager.switch_to(RemnashopPlans.CONFIGURATOR)
    logger.info(f"{log(user)} Accepted pending tag '{pending_tag}'")


async def on_tag_delete(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    plan.tag = None
    adapter.save(plan)
    logger.info(f"{log(user)} Successfully removed plan tag")


async def on_type_select(
    callback: CallbackQuery,
    widget: Select[PlanType],
    dialog_manager: DialogManager,
    selected_type: PlanType,
) -> None:
    """Сохраняет выбранный тип в pending для отложенного применения."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.debug(f"{log(user)} Selected plan type '{selected_type}' (pending)")
    dialog_manager.dialog_data["pending_plan_type"] = selected_type.value


async def on_accept_type(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Применяет pending тип и возвращается к конфигуратору."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    pending_type_value = dialog_manager.dialog_data.pop("pending_plan_type", None)

    if pending_type_value is None:
        await dialog_manager.switch_to(state=RemnashopPlans.CONFIGURATOR)
        return

    selected_type = PlanType(pending_type_value)
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    if selected_type == PlanType.DEVICES and plan.device_limit == -1:
        plan.device_limit = 1
    elif selected_type == PlanType.TRAFFIC and plan.traffic_limit == -1:
        plan.traffic_limit = 100
    elif selected_type == PlanType.BOTH:
        if plan.traffic_limit == -1:
            plan.traffic_limit = 100
        if plan.device_limit == -1:
            plan.device_limit = 1

    plan.type = selected_type
    adapter.save(plan)

    logger.info(f"{log(user)} Successfully updated plan type to '{plan.type.name}'")
    await dialog_manager.switch_to(state=RemnashopPlans.CONFIGURATOR)


async def on_cancel_type(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отменяет выбор типа и возвращается к конфигуратору."""
    dialog_manager.dialog_data.pop("pending_plan_type", None)
    await dialog_manager.switch_to(state=RemnashopPlans.CONFIGURATOR)


async def on_availability_select(
    callback: CallbackQuery,
    widget: Select[PlanAvailability],
    dialog_manager: DialogManager,
    selected_availability: PlanAvailability,
) -> None:
    """Сохраняет выбранную доступность в pending для отложенного применения."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.debug(f"{log(user)} Selected plan availability '{selected_availability}' (pending)")
    dialog_manager.dialog_data["pending_plan_availability"] = selected_availability.value


async def on_accept_availability(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Применяет pending доступность и возвращается к конфигуратору."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    pending_avail_value = dialog_manager.dialog_data.pop("pending_plan_availability", None)

    if pending_avail_value is None:
        await dialog_manager.switch_to(state=RemnashopPlans.CONFIGURATOR)
        return

    selected_availability = PlanAvailability(pending_avail_value)
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    plan.availability = selected_availability
    adapter.save(plan)

    logger.info(f"{log(user)} Successfully updated plan availability to '{plan.availability}'")
    await dialog_manager.switch_to(state=RemnashopPlans.CONFIGURATOR)


async def on_cancel_availability(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отменяет выбор доступности и возвращается к конфигуратору."""
    dialog_manager.dialog_data.pop("pending_plan_availability", None)
    await dialog_manager.switch_to(state=RemnashopPlans.CONFIGURATOR)
    await dialog_manager.switch_to(state=RemnashopPlans.CONFIGURATOR)


async def on_active_toggle(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    logger.debug(f"{log(user)} Attempted to toggle plan active status")

    plan.is_active = not plan.is_active
    adapter.save(plan)
    logger.info(f"{log(user)} Successfully toggled plan active status to '{plan.is_active}'")


@inject
async def on_traffic_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
) -> None:
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.debug(f"{log(user)} Attempted to set plan traffic limit")

    if message.text is None or not (message.text.isdigit() and int(message.text) > 0):
        logger.warning(f"{log(user)} Invalid traffic limit input: '{message.text}'")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-invalid-number"),
        )
        return

    number = int(message.text)
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    plan.traffic_limit = number
    adapter.save(plan)

    logger.info(f"{log(user)} Successfully set plan traffic limit to '{plan.traffic_limit}'")
    await dialog_manager.switch_to(state=RemnashopPlans.CONFIGURATOR)


async def on_strategy_select(
    callback: CallbackQuery,
    widget: Select[TrafficLimitStrategy],
    dialog_manager: DialogManager,
    selected_strategy: TrafficLimitStrategy,
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    logger.debug(f"{log(user)} Selected plan traffic strategy '{selected_strategy}'")

    plan.traffic_limit_strategy = selected_strategy
    adapter.save(plan)

    logger.info(f"{log(user)} Successfully updated plan traffic strategy to '{plan.availability}'")


@inject
async def on_devices_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
) -> None:
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.debug(f"{log(user)} Attempted to set plan device limit")

    if message.text is None or not (message.text.isdigit() and int(message.text) > 0):
        logger.warning(f"{log(user)} Invalid device limit input: '{message.text}'")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-invalid-number"),
        )
        return

    number = int(message.text)
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    plan.device_limit = number
    adapter.save(plan)

    logger.info(f"{log(user)} Successfully set plan device limit to '{plan.device_limit}'")
    await dialog_manager.switch_to(state=RemnashopPlans.CONFIGURATOR)


async def on_duration_select(
    callback: CallbackQuery,
    widget: Button,
    sub_manager: SubManager,
) -> None:
    user: UserDto = sub_manager.middleware_data[USER_KEY]
    sub_manager.dialog_data["selected_duration"] = int(sub_manager.item_id)
    logger.debug(f"{log(user)} Selected duration '{sub_manager.item_id}' days")
    await sub_manager.switch_to(state=RemnashopPlans.PRICES)


@inject
async def on_duration_remove(
    callback: CallbackQuery,
    widget: Button,
    sub_manager: SubManager,
    notification_service: FromDishka[NotificationService],
) -> None:
    await sub_manager.load_data()
    user: UserDto = sub_manager.middleware_data[USER_KEY]
    logger.debug(f"{log(user)} Attempted to remove duration")

    adapter = DialogDataAdapter(sub_manager.manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    if len(plan.durations) <= 1:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-duration-last"),
        )
        return

    duration_to_remove = int(sub_manager.item_id)
    new_durations = [d for d in plan.durations if d.days != duration_to_remove]
    plan.durations = new_durations
    adapter.save(plan)
    logger.info(f"{log(user)} Successfully removed duration '{duration_to_remove}' days from plan")


@inject
async def on_duration_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
) -> None:
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.debug(f"{log(user)} Attempted to add new plan duration")

    number = parse_int(message.text)

    if number is None or not (number > 0 or number == -1):
        logger.warning(f"{log(user)} Provided invalid duration input: '{message.text}'")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-invalid-number"),
        )
        return

    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    if plan.get_duration(number):
        logger.warning(f"{log(user)} Provided already existing duration")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-duration-already-exists"),
        )
        return

    plan.durations.append(
        PlanDurationDto(
            days=number,
            prices=[
                PlanPriceDto(
                    currency=currency,
                    price=100,
                )
                for currency in Currency
            ],
        )
    )
    adapter.save(plan)

    logger.info(f"{log(user)} New duration '{number}' days added to plan")
    await dialog_manager.switch_to(state=RemnashopPlans.DURATIONS)


async def on_currency_select(
    callback: CallbackQuery,
    widget: Select[Currency],
    dialog_manager: DialogManager,
    selected_currency: Currency,
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Selected currency '{selected_currency}'")
    dialog_manager.dialog_data["selected_currency"] = selected_currency.value
    await dialog_manager.switch_to(state=RemnashopPlans.PRICE)


@inject
async def on_price_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
    pricing_service: FromDishka[PricingService],
) -> None:
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.debug(f"{log(user)} Attempted to set plan price")

    if message.text is None:
        logger.warning(f"{log(user)} Provided empty price input")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-invalid-number"),
        )
        return

    selected_duration = dialog_manager.dialog_data.get("selected_duration")
    selected_currency = dialog_manager.dialog_data.get("selected_currency")

    if not selected_duration or not selected_currency:
        raise ValueError("Missing duration or currency selection for price input")

    try:
        new_price = pricing_service.parse_price(message.text, selected_currency)
    except ValueError:
        logger.warning(f"{log(user)} Provided invalid price input: '{message.text}'")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-invalid-number"),
        )
        return

    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    for duration in plan.durations:
        if duration.days == selected_duration:
            for price in duration.prices:
                if price.currency == selected_currency:
                    price.price = new_price
                    logger.info(
                        f"{log(user)} Updated price for duration '{duration.days}' "
                        f"and currency '{selected_currency}' to '{new_price}'"
                    )
                    break
            break

    adapter.save(plan)
    await dialog_manager.switch_to(state=RemnashopPlans.PRICES)


@inject
async def on_allowed_user_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    notification_service: FromDishka[NotificationService],
) -> None:
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.debug(f"{log(user)} Attempted to set allowed id for plan")

    if message.text is None or not message.text.isdigit():
        logger.warning(f"{log(user)} Provided non-numeric user ID")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-invalid-user-id"),
        )
        return

    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    allowed_user_id = int(message.text)

    if allowed_user_id in plan.allowed_user_ids:
        logger.warning(f"{log(user)} User '{allowed_user_id}' is already allowed for plan")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-user-already-allowed"),
        )
        return

    plan.allowed_user_ids.append(allowed_user_id)
    adapter.save(plan)


@inject
async def on_allowed_user_remove(
    callback: CallbackQuery,
    widget: Button,
    sub_manager: SubManager,
) -> None:
    user: UserDto = sub_manager.middleware_data[USER_KEY]
    logger.debug(f"{log(user)} Attempted to remove allowed user from plan")
    await sub_manager.load_data()
    user_id = int(sub_manager.item_id)

    adapter = DialogDataAdapter(sub_manager.manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    logger.info(f"{log(user)} Removed allowed user ID '{user_id}' from plan")
    plan.allowed_user_ids.remove(user_id)
    adapter.save(plan)


@inject
async def on_squads(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    remnawave: FromDishka[RemnawaveSDK],
    notification_service: FromDishka[NotificationService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)
    
    if plan:
        logger.debug(
            f"{log(user)} Opening squads menu: current internal={plan.internal_squads}, "
            f"external={plan.external_squad}"
        )
    
    result = await remnawave.internal_squads.get_internal_squads()

    if not result.internal_squads:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-squads-empty"),
        )
        return

    await dialog_manager.switch_to(state=RemnashopPlans.SQUADS)


@inject
async def on_internal_squads_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Open internal squads menu - save initial state for cancellation"""
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)
    
    # Save initial state for potential cancellation
    if plan and plan.internal_squads is not None:
        dialog_manager.dialog_data["internal_squads_backup"] = list(plan.internal_squads)
    else:
        dialog_manager.dialog_data["internal_squads_backup"] = []
    
    await dialog_manager.switch_to(state=RemnashopPlans.INTERNAL_SQUADS)


@inject
async def on_external_squads_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    # Data is already in dialog memory from earlier steps
    await dialog_manager.switch_to(state=RemnashopPlans.EXTERNAL_SQUADS)


@inject
async def on_internal_squad_select(
    callback: CallbackQuery,
    widget: Button,
    sub_manager: SubManager,
) -> None:
    """Toggle internal squad selection - like src_0.4.1 but with multi-select support"""
    await sub_manager.load_data()
    item_id = sub_manager.item_id
    user: UserDto = sub_manager.middleware_data[USER_KEY]

    # Get squads list from dialog data (set by getter)
    squads = sub_manager.dialog_data.get("squads", [])
    
    # Find squad UUID by item_id (which is the index)
    try:
        squad_index = int(item_id)
        if 0 <= squad_index < len(squads):
            selected_squad = UUID(squads[squad_index]["uuid"])
        else:
            logger.error(f"{log(user)} Invalid squad index: {squad_index}")
            return
    except (ValueError, KeyError, IndexError) as e:
        logger.error(f"{log(user)} Error parsing squad selection: {e}")
        return

    # Get plan and modify it directly (like src_0.4.1)
    adapter = DialogDataAdapter(sub_manager)
    plan = adapter.load(PlanDto)
    
    if not plan:
        raise ValueError("PlanDto not found in dialog data")
    
    # Initialize internal_squads if None
    if plan.internal_squads is None:
        plan.internal_squads = []

    # Toggle squad selection (remove if present, add if not present)
    if selected_squad in plan.internal_squads:
        plan.internal_squads.remove(selected_squad)
        logger.info(f"{log(user)} Removed internal squad {selected_squad}")
    else:
        plan.internal_squads.append(selected_squad)
        logger.info(f"{log(user)} Added internal squad {selected_squad}")
    
    # Save changes immediately
    adapter.save(plan)
    
    # Refresh dialog to show updated button states
    await sub_manager.show()


@inject
async def on_accept_internal_squads(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Accept internal squads selection - changes already saved, just switch back"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    logger.info(
        f"{log(user)} Accepted internal squads: {plan.internal_squads}"
    )

    # Clear temporary dialog data
    if "internal_squads_backup" in dialog_manager.dialog_data:
        del dialog_manager.dialog_data["internal_squads_backup"]
    if "squads" in dialog_manager.dialog_data:
        del dialog_manager.dialog_data["squads"]

    await dialog_manager.switch_to(RemnashopPlans.SQUADS)


@inject
async def on_cancel_internal_squads(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Discard internal squads selection - restore from backup"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    # Restore from backup if available
    backup_squads = dialog_manager.dialog_data.get("internal_squads_backup")
    if backup_squads is not None:
        plan.internal_squads = backup_squads
        adapter.save(plan)
        logger.info(
            f"{log(user)} Cancelled internal squads selection, restored from backup"
        )

    # Clear temporary dialog data
    if "internal_squads_backup" in dialog_manager.dialog_data:
        del dialog_manager.dialog_data["internal_squads_backup"]
    if "squads" in dialog_manager.dialog_data:
        del dialog_manager.dialog_data["squads"]

    await dialog_manager.switch_to(RemnashopPlans.SQUADS)


@inject
@inject
async def on_external_squad_select(
    callback: CallbackQuery,
    widget: Select,
    dialog_manager: DialogManager,
    selected_squad: str | UUID,
) -> None:
    """Toggle external squad selection - select or deselect"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    # Convert to UUID if it's a string
    if isinstance(selected_squad, str):
        try:
            selected_squad = UUID(selected_squad)
        except ValueError:
            logger.error(f"{log(user)} Invalid UUID format: {selected_squad}")
            return

    # Toggle squad selection - like src_0.4.1
    if plan.external_squad and selected_squad in plan.external_squad:
        # Deselect - set to None
        plan.external_squad = None
        logger.info(f"{log(user)} Unset external squad '{selected_squad}'")
    else:
        # Select - set as list with single item
        plan.external_squad = [selected_squad]
        logger.info(f"{log(user)} Set external squad '{selected_squad}'")

    # Save changes immediately
    adapter.save(plan)
    
    # Refresh dialog to show updated button states
    await dialog_manager.switch_to(RemnashopPlans.EXTERNAL_SQUADS)


@inject
async def on_accept_external_squad(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Accept external squad changes and go back to squads selection"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    logger.info(f"{log(user)} Accepted external squad: {plan.external_squad}")

    await dialog_manager.switch_to(RemnashopPlans.SQUADS)


@inject
async def on_cancel_external_squad(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Discard external squad changes"""
    await dialog_manager.switch_to(RemnashopPlans.SQUADS)


@inject
async def on_cancel_squads(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Restore original squad selections and discard all pending changes"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]

    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    # Restore original state from saved values
    saved_internal_squads = dialog_manager.dialog_data.pop("saved_internal_squads", None)
    saved_external_squad = dialog_manager.dialog_data.pop("saved_external_squad", None)

    if saved_internal_squads is not None:
        plan.internal_squads = list(saved_internal_squads)
        logger.info(f"{log(user)} Restored internal squads on cancel: {saved_internal_squads}")

    if saved_external_squad is not None:
        plan.external_squad = saved_external_squad
        logger.info(f"{log(user)} Restored external squad on cancel: {saved_external_squad}")

    adapter.save(plan)

    # Clear all pending selections and modified flags
    dialog_manager.dialog_data.pop("pending_internal_squads", None)
    dialog_manager.dialog_data.pop("pending_external_squad", None)
    dialog_manager.dialog_data.pop("internal_squads_modified", None)
    dialog_manager.dialog_data.pop("external_squad_modified", None)

    await dialog_manager.switch_to(RemnashopPlans.CONFIGURATOR)


@inject
async def on_accept_squads(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Accept all pending squad selections and apply them to plan"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)
    
    if not plan:
        raise ValueError("PlanDto not found in dialog data")
    
    logger.debug(f"{log(user)} Before applying: internal={plan.internal_squads}, external={plan.external_squad}")
    
    # Check if internal squads were modified (user visited internal squads menu)
    internal_modified = dialog_manager.dialog_data.get("internal_squads_modified", False)
    pending_internal = dialog_manager.dialog_data.get("pending_internal_squads")
    
    if internal_modified and pending_internal is not None:
        plan.internal_squads = list(pending_internal)
        logger.info(f"{log(user)} Applied pending internal squads: {plan.internal_squads}")
    elif pending_internal is not None:
        logger.debug(f"{log(user)} Pending internal squads exist but not modified, keeping plan value")
    else:
        logger.debug(f"{log(user)} No pending internal squads")
    
    # Check if external squad was modified (user visited external squads menu)
    external_modified = dialog_manager.dialog_data.get("external_squad_modified", False)
    
    logger.debug(
        f"{log(user)} on_accept_squads: external_modified={external_modified}, "
        f"pending_external_squad key exists={'pending_external_squad' in dialog_manager.dialog_data}"
    )
    
    if external_modified:
        # Check if pending_external_squad key exists in dialog_data (even if value is None)
        if "pending_external_squad" in dialog_manager.dialog_data:
            pending_external = dialog_manager.dialog_data["pending_external_squad"]
            plan.external_squad = list(pending_external) if pending_external else None
            logger.info(f"{log(user)} Applied pending external squad: {plan.external_squad}")
        else:
            logger.warning(f"{log(user)} External squad modified but no pending value found")
    else:
        logger.debug(f"{log(user)} No pending external squad changes")
    
    adapter.save(plan)
    logger.debug(f"{log(user)} After applying: internal={plan.internal_squads}, external={plan.external_squad}")
    
    # Clear all state
    dialog_manager.dialog_data.pop("saved_internal_squads", None)
    dialog_manager.dialog_data.pop("saved_external_squad", None)
    dialog_manager.dialog_data.pop("pending_internal_squads", None)
    dialog_manager.dialog_data.pop("pending_external_squad", None)
    dialog_manager.dialog_data.pop("internal_squads_modified", None)
    dialog_manager.dialog_data.pop("external_squad_modified", None)
    
    await dialog_manager.switch_to(RemnashopPlans.CONFIGURATOR)


@inject
async def on_cancel_configurator(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена всех изменений в конфигураторе и очистка всех данных плана."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    adapter = DialogDataAdapter(dialog_manager)
    
    # Если был оригинальный план (редактирование), восстанавливаем его
    original_plan_data = dialog_manager.dialog_data.get("original_plan")
    if original_plan_data:
        original_plan = PlanDto.model_validate(original_plan_data)
        adapter.save(original_plan)
        logger.debug(f"{log(user)} Restored original plan state")
    else:
        # Если это было создание нового плана, удаляем все данные плана
        dialog_manager.dialog_data.pop("plandto", None)
        logger.debug(f"{log(user)} Cleared new plan data")
    
    # Очищаем все pending значения и сохраненные копии
    dialog_manager.dialog_data.pop("pending_plan_name", None)
    dialog_manager.dialog_data.pop("pending_plan_description", None)
    dialog_manager.dialog_data.pop("pending_plan_type", None)
    dialog_manager.dialog_data.pop("pending_plan_availability", None)
    dialog_manager.dialog_data.pop("pending_tag", None)
    dialog_manager.dialog_data.pop("pending_internal_squads", None)
    dialog_manager.dialog_data.pop("pending_external_squad", None)
    dialog_manager.dialog_data.pop("saved_internal_squads", None)
    dialog_manager.dialog_data.pop("saved_external_squad", None)
    dialog_manager.dialog_data.pop("original_plan", None)
    dialog_manager.dialog_data.pop("is_edit", None)
    
    await dialog_manager.switch_to(RemnashopPlans.MAIN)
    logger.info(f"{log(user)} Cancelled all plan changes and cleared data")


@inject
async def on_confirm_plan(  # noqa: C901
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    config: FromDishka[AppConfig],
    notification_service: FromDishka[NotificationService],
    plan_service: FromDishka[PlanService],
    subscription_service: FromDishka[SubscriptionService],
    remnawave_service: FromDishka[RemnawaveService],
    user_service: FromDishka[UserService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]

    logger.debug(f"{log(user)} Attempted to confirm plan")

    adapter = DialogDataAdapter(dialog_manager)
    plan_dto = adapter.load(PlanDto)

    if not plan_dto:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-save-error"),
        )
        raise ValueError("PlanDto not found in dialog data")

    # Применяем все pending значения перед сохранением
    if "pending_plan_name" in dialog_manager.dialog_data:
        plan_dto.name = dialog_manager.dialog_data.pop("pending_plan_name")
    
    if "pending_plan_description" in dialog_manager.dialog_data:
        plan_dto.description = dialog_manager.dialog_data.pop("pending_plan_description")
    
    if "pending_plan_type" in dialog_manager.dialog_data:
        plan_dto.type = dialog_manager.dialog_data.pop("pending_plan_type")
    
    if "pending_plan_availability" in dialog_manager.dialog_data:
        plan_dto.availability = dialog_manager.dialog_data.pop("pending_plan_availability")
    
    if "pending_tag" in dialog_manager.dialog_data:
        plan_dto.tag = dialog_manager.dialog_data.pop("pending_tag")
    
    if "pending_internal_squads" in dialog_manager.dialog_data:
        plan_dto.internal_squads = dialog_manager.dialog_data.pop("pending_internal_squads")
    
    if "pending_external_squad" in dialog_manager.dialog_data:
        plan_dto.external_squad = dialog_manager.dialog_data.pop("pending_external_squad")
    
    adapter.save(plan_dto)

    if not plan_dto.internal_squads:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-internal-squads-empty"),
        )
        return

    if plan_dto.type == PlanType.DEVICES:
        plan_dto.traffic_limit = -1
    elif plan_dto.type == PlanType.TRAFFIC:
        plan_dto.device_limit = -1
    elif plan_dto.type == PlanType.BOTH:
        pass
    else:  # PlanType.UNLIMITED
        plan_dto.traffic_limit = -1
        plan_dto.device_limit = -1

    if plan_dto.availability != PlanAvailability.ALLOWED:
        plan_dto.allowed_user_ids = []

    # Проверка для пробных планов (TRIAL и INVITED)
    if plan_dto.availability in (PlanAvailability.TRIAL, PlanAvailability.INVITED):
        # Для пробных планов проверяем, что цена равна 0
        for duration in plan_dto.durations:
            for price in duration.prices:
                price.price = Decimal("0")
        
        # Проверяем, нет ли уже плана с такой же доступностью
        existing_plans = await plan_service.get_all()
        existing_trial_or_invited_plan = next(
            (p for p in existing_plans 
             if p.is_active and p.availability == plan_dto.availability 
             and (not plan_dto.id or p.id != plan_dto.id)),
            None
        )
        
        if existing_trial_or_invited_plan:
            plan_type_name = "пробного" if plan_dto.availability == PlanAvailability.TRIAL else "реферального пробного"
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(
                    i18n_key="ntf-plan-trial-already-exists",
                    i18n_kwargs={"plan_type": plan_type_name}
                ),
            )
            return

        # Проверяем, что у пробного плана только одна длительность
        if len(plan_dto.durations) > 1:
            plan_type_name = "пробного" if plan_dto.availability == PlanAvailability.TRIAL else "реферального пробного"
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(
                    i18n_key="ntf-plan-trial-once-duration",
                    i18n_kwargs={"plan_type": plan_type_name}
                ),
            )
            return

    if plan_dto.id:
        # Загружаем оригинальный план из базы для сравнения сквадов
        original_plan = await plan_service.get(plan_dto.id)
        original_internal_squads = original_plan.internal_squads if original_plan else None
        original_external_squad = original_plan.external_squad if original_plan else None
        
        logger.info(f"{log(user)} Updating existing plan with ID '{plan_dto.id}'")
        await plan_service.update(plan_dto)
        logger.info(f"{log(user)} Plan '{plan_dto.name}' updated successfully")
        
        # Проверяем изменились ли сквады
        squads_changed = False
        if original_plan:
            # Сравниваем внутренние сквады
            new_internal = set(plan_dto.internal_squads or [])
            old_internal = set(original_internal_squads or [])
            if new_internal != old_internal:
                squads_changed = True
                logger.info(
                    f"{log(user)} Internal squads changed: {list(old_internal)} -> {list(new_internal)}"
                )
            
            # Сравниваем внешние сквады
            new_external = set(plan_dto.external_squad or [])
            old_external = set(original_external_squad or [])
            if new_external != old_external:
                squads_changed = True
                logger.info(
                    f"{log(user)} External squad changed: {list(old_external)} -> {list(new_external)}"
                )
        
        # Синхронизируем всех пользователей с этим планом в Remnawave
        # (обновляем их параметры в панели согласно новым настройкам плана)
        logger.info(f"{log(user)} Synchronizing all users with plan '{plan_dto.name}' to Remnawave")
        all_subscriptions = await subscription_service.get_all()
        synced_count = 0
        failed_count = 0
        
        for subscription in all_subscriptions:
                # Синхронизируем только АКТИВНЫЕ подписки с этим планом
                if (subscription.plan and subscription.plan.id == plan_dto.id 
                    and subscription.status == SubscriptionStatus.ACTIVE):
                    try:
                        # Получаем пользователя если его нет в подписке
                        target_user = subscription.user
                        if not target_user:
                            target_user = await user_service.get(telegram_id=subscription.user_telegram_id)
                        
                        if not target_user:
                            logger.warning(
                                f"{log(user)} User not found for subscription '{subscription.id}', skipping sync"
                            )
                            continue
                        
                        # Обновляем snapshot плана в подписке с новыми параметрами
                        subscription.plan.internal_squads = list(plan_dto.internal_squads) if plan_dto.internal_squads else []
                        if plan_dto.external_squad:
                            subscription.plan.external_squad = list(plan_dto.external_squad)
                        subscription.plan.traffic_limit = plan_dto.traffic_limit
                        subscription.plan.device_limit = plan_dto.device_limit
                        subscription.plan.tag = plan_dto.tag
                        subscription.plan.traffic_limit_strategy = plan_dto.traffic_limit_strategy
                        
                        # Обновляем параметры на уровне подписки (используются в remnawave_service.updated_user)
                        subscription.internal_squads = list(plan_dto.internal_squads) if plan_dto.internal_squads else []
                        if plan_dto.external_squad:
                            subscription.external_squad = list(plan_dto.external_squad)
                        subscription.traffic_limit = plan_dto.traffic_limit
                        subscription.device_limit = plan_dto.device_limit
                        subscription.tag = plan_dto.tag
                        subscription.traffic_limit_strategy = plan_dto.traffic_limit_strategy
                        
                        logger.debug(
                            f"{log(user)} Before update - subscription external_squad: {subscription.external_squad}, "
                            f"plan external_squad: {plan_dto.external_squad}"
                        )
                        
                        # Сохраняем обновлённую подписку в БД
                        await subscription_service.update(subscription)
                        
                        # Синхронизируем с Remnawave
                        if subscription.user_remna_id:
                            await remnawave_service.updated_user(
                                user=target_user,
                                uuid=subscription.user_remna_id,
                                subscription=subscription,
                                reset_traffic=False,  # Не сбрасываем трафик при изменении плана
                            )
                            synced_count += 1
                            logger.debug(
                                f"{log(user)} Synced user '{target_user.telegram_id}' "
                                f"with plan '{plan_dto.name}' to Remnawave"
                            )
                        else:
                            logger.warning(
                                f"{log(user)} Subscription '{subscription.id}' has no user_remna_id, skipping Remnawave sync"
                            )
                            failed_count += 1
                    except Exception as e:
                        failed_count += 1
                        logger.error(
                            f"{log(user)} Failed to sync subscription '{subscription.id}': {e}",
                            exc_info=True
                        )
        
        logger.info(
            f"{log(user)} Remnawave synchronization completed: {synced_count} synced, {failed_count} failed"
        )
        
        # Notify all users with this plan to update their interface
        all_subscriptions = await subscription_service.get_all()
        users_to_notify = set()
        
        for subscription in all_subscriptions:
            if subscription.plan and subscription.plan.id == plan_dto.id:
                telegram_id = subscription.user.telegram_id if subscription.user else None
                # Exclude test bot from automatic updates
                if telegram_id and telegram_id != config.bot.dev_id:
                    users_to_notify.add(telegram_id)
        
        # Send update notification to all affected users
        for telegram_id in users_to_notify:
            await redirect_to_main_menu_task.kiq(telegram_id)
            logger.debug(
                f"{log(user)} Sent interface update notification to user '{telegram_id}' "
                f"after plan '{plan_dto.name}' modification"
            )
        
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-updated-success"),
        )
    else:
        existing_plan: Optional[PlanDto] = await plan_service.get_by_name(plan_name=plan_dto.name)
        if existing_plan:
            logger.warning(f"{log(user)} Plan with name '{plan_dto.name}' already exists. Aborting")
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(i18n_key="ntf-plan-name-already-exists"),
            )
            return

        logger.info(f"{log(user)} Creating new plan with name '{plan_dto.name}'")
        plan = await plan_service.create(plan_dto)
        logger.info(f"{log(user)} Plan '{plan.name}' created successfully")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-plan-created-success"),
        )

    # Очищаем оригинальную копию плана после успешного сохранения
    dialog_manager.dialog_data.pop("original_plan", None)
    
    await dialog_manager.switch_to(RemnashopPlans.MAIN)
