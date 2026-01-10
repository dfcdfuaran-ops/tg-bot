from typing import Any

from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager, ShowMode, StartMode
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Select
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from loguru import logger

from src.bot.states import DashboardPromocodes
from src.core.constants import USER_KEY
from src.core.enums import PromocodeRewardType
from src.core.utils.adapter import DialogDataAdapter
from src.core.utils.formatters import format_user_log as log
from src.core.utils.message_payload import MessagePayload
from src.core.utils.validators import is_double_click, parse_int
from src.infrastructure.database.models.dto import PromocodeDto, UserDto
from src.services.notification import NotificationService
from src.services.plan import PlanService
from src.services.promocode import PromocodeService


# ==================== Навигация ====================


async def on_create_promocode(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Создать новый промокод - переход к конфигуратору с новым DTO."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = PromocodeDto()
    promocode.code = PromocodeDto.generate_code(length=7)
    adapter.save(promocode)
    logger.info(f"🔍 After save, dialog_data keys: {list(dialog_manager.dialog_data.keys())}")
    
    dialog_manager.dialog_data["is_edit"] = False
    logger.info(f"{log(user)} Creating new promocode")
    
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


async def on_list_promocodes(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход к списку промокодов."""
    await dialog_manager.switch_to(state=DashboardPromocodes.LIST)


@inject
async def on_promocode_select(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    promocode_service: FromDishka[PromocodeService],
) -> None:
    """Выбор промокода для просмотра/редактирования из списка."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Получаем ID промокода из item_id
    promocode_id = int(dialog_manager.item_id)
    
    promocode = await promocode_service.get(promocode_id=promocode_id)
    
    if not promocode:
        logger.warning(f"{log(user)} Promocode '{promocode_id}' not found")
        return
    
    adapter = DialogDataAdapter(dialog_manager)
    adapter.save(promocode)
    
    dialog_manager.dialog_data["is_edit"] = True
    logger.info(f"{log(user)} Selected promocode '{promocode.code}' (ID: {promocode.id})")
    
    # Сразу открываем конфигуратор, как просили
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


@inject
async def on_promocode_toggle_active(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    promocode_service: FromDishka[PromocodeService],
) -> None:
    """Переключение активности промокода из списка."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Получаем ID промокода из item_id
    promocode_id = int(dialog_manager.item_id)
    
    promocode = await promocode_service.get(promocode_id=promocode_id)
    
    if not promocode:
        logger.warning(f"{log(user)} Promocode '{promocode_id}' not found")
        return
    
    # Переключаем статус
    promocode.is_active = not promocode.is_active
    result = await promocode_service.update(promocode=promocode)
    
    if result:
        status = "активирован" if promocode.is_active else "деактивирован"
        logger.info(f"{log(user)} Promocode '{promocode.code}' {status}")
    else:
        logger.warning(f"{log(user)} Failed to toggle promocode '{promocode.code}'")


# ==================== Поиск ====================


@inject
async def on_promocode_search(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
    promocode_service: FromDishka[PromocodeService],
) -> None:
    """Поиск промокода по коду."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    if not message.text:
        return
    
    search_query = message.text.strip().upper()
    promocode = await promocode_service.get_by_code(promocode_code=search_query)
    
    if not promocode:
        logger.info(f"{log(user)} Promocode search '{search_query}' not found")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-promocode-not-found"),
        )
        return
    
    adapter = DialogDataAdapter(dialog_manager)
    adapter.save(promocode)
    
    dialog_manager.dialog_data["is_edit"] = True
    logger.info(f"{log(user)} Found promocode '{promocode.code}'")
    
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


# ==================== Удаление ====================


@inject
async def on_promocode_delete(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
    promocode_service: FromDishka[PromocodeService],
) -> None:
    """Удаление промокода с подтверждением двойным кликом."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode or not promocode.id:
        raise ValueError("PromocodeDto not found in dialog data")
    
    if is_double_click(dialog_manager, key="delete_promocode_confirm", cooldown=5):
        result = await promocode_service.delete(promocode_id=promocode.id)
        
        if result:
            logger.info(f"{log(user)} Deleted promocode '{promocode.code}'")
            await dialog_manager.switch_to(state=DashboardPromocodes.LIST)
        else:
            logger.warning(f"{log(user)} Failed to delete promocode '{promocode.code}'")
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(i18n_key="ntf-promocode-delete-error"),
            )


@inject
async def on_promocode_delete_from_list(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
    promocode_service: FromDishka[PromocodeService],
) -> None:
    """Удаление промокода из списка с подтверждением двойным кликом."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Получаем ID промокода из item_id
    promocode_id = int(dialog_manager.item_id)
    
    promocode = await promocode_service.get(promocode_id=promocode_id)
    
    if not promocode:
        logger.warning(f"{log(user)} Promocode '{promocode_id}' not found")
        return
    
    if is_double_click(dialog_manager, key=f"delete_list_{promocode_id}", cooldown=5):
        result = await promocode_service.delete(promocode_id=promocode.id)
        
        if result:
            logger.info(f"{log(user)} Deleted promocode '{promocode.code}' from list")
            # Показываем сообщение об успешном удалении (автоудаление через 5 сек)
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(i18n_key="ntf-promocode-delete-success"),
            )
            await dialog_manager.show()  # Обновляем список
        else:
            logger.warning(f"{log(user)} Failed to delete promocode '{promocode.code}'")
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(i18n_key="ntf-promocode-delete-error"),
            )
        return
    
    await notification_service.notify_user(
        user=user,
        payload=MessagePayload(i18n_key="ntf-double-click-confirm"),
    )
    logger.debug(f"{log(user)} Awaiting confirmation to delete promocode '{promocode.code}'")


# ==================== Переключатели ====================


async def on_active_toggle(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переключение статуса активности промокода."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    promocode.is_active = not promocode.is_active
    adapter.save(promocode)
    
    status = "активирован" if promocode.is_active else "деактивирован"
    logger.info(f"{log(user)} Promocode '{promocode.code}' {status}")


async def on_type_enter(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Вход в меню выбора типа - сохраняем оригинальное значение."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    # Сохраняем текущий тип для возможности отмены
    dialog_manager.dialog_data["original_reward_type"] = promocode.reward_type.value
    
    logger.info(f"{log(user)} Entered type selection menu")
    await dialog_manager.switch_to(state=DashboardPromocodes.TYPE)


async def on_type_select(
    callback: CallbackQuery,
    widget: Select[str],
    dialog_manager: DialogManager,
    selected_type: str,
) -> None:
    """Выбор типа промокода."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    promocode.reward_type = PromocodeRewardType(selected_type)
    
    # Сброс reward если тип изменился
    if promocode.reward_type == PromocodeRewardType.DURATION:
        promocode.reward = 30  # Дни по умолчанию
    elif promocode.reward_type in [PromocodeRewardType.PERSONAL_DISCOUNT, PromocodeRewardType.PURCHASE_DISCOUNT]:
        promocode.reward = 10  # Процент по умолчанию
    
    adapter.save(promocode)
    
    logger.info(f"{log(user)} Set promocode type to '{selected_type}'")
    # Не переходим сразу, остаемся в меню выбора


# ==================== Ввод названия ====================


@inject
async def on_name_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
) -> None:
    """Ввод названия промокода."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    if not message.text:
        return
    
    name = message.text.strip()
    
    # Проверка длины названия
    if len(name) < 1 or len(name) > 50:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-promocode-invalid-name"),
        )
        return
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    promocode.name = name
    adapter.save(promocode)
    
    logger.info(f"{log(user)} Set promocode name to '{name}'")
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


# ==================== Ввод кода ====================


@inject
async def on_code_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
    promocode_service: FromDishka[PromocodeService],
) -> None:
    """Ввод кода промокода."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    if not message.text:
        return
    
    code = message.text.strip().upper()
    
    # Проверка длины кода
    if len(code) < 3 or len(code) > 20:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-promocode-invalid-code"),
        )
        return
    
    # Проверка уникальности
    existing = await promocode_service.get_by_code(promocode_code=code)
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if existing and (not promocode or existing.id != promocode.id):
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-promocode-already-exists"),
        )
        return
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    promocode.code = code
    adapter.save(promocode)
    
    logger.info(f"{log(user)} Set promocode code to '{code}'")
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)



async def on_code_generate(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Генерация случайного кода."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    promocode.code = PromocodeDto.generate_code(length=7)
    adapter.save(promocode)
    
    logger.info(f"{log(user)} Generated new promocode code: '{promocode.code}'")
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


# ==================== Ввод награды ====================


async def on_reward_preset(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор предустановленного значения награды."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    # Получаем значение из button_id
    preset_value = int(widget.widget_id.split("_")[-1])  # reward_0, reward_5, etc.
    
    promocode.reward = preset_value
    adapter.save(promocode)
    
    logger.info(f"{log(user)} Set promocode reward to '{preset_value}' (preset)")
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


@inject
async def on_reward_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
) -> None:
    """Ввод награды (дни/проценты)."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    if not message.text:
        return
    
    value = parse_int(message.text)
    
    if value is None or value <= 0:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-promocode-invalid-reward"),
        )
        return
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    # Для скидок ограничиваем 100%
    if promocode.reward_type in [PromocodeRewardType.PERSONAL_DISCOUNT, PromocodeRewardType.PURCHASE_DISCOUNT]:
        if value > 100:
            value = 100
    
    promocode.reward = value
    adapter.save(promocode)
    
    logger.info(f"{log(user)} Set promocode reward to '{value}'")
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


# ==================== Ввод срока действия ====================


async def on_lifetime_preset(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор предустановленного срока действия."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    # Получаем значение из button_id
    preset_value = widget.widget_id.split("_")[-1]  # lifetime_0, lifetime_1, etc.
    
    # Если выбран "Бесконечно" (lifetime_0), устанавливаем None
    if preset_value == "0":
        promocode.lifetime = None
        logger.info(f"{log(user)} Set promocode lifetime to infinite")
    else:
        promocode.lifetime = int(preset_value)
        logger.info(f"{log(user)} Set promocode lifetime to '{preset_value}' days (preset)")
    
    logger.info(f"🔍 Before save in on_lifetime_preset: code={promocode.code}, lifetime={promocode.lifetime}, reward={promocode.reward}")
    adapter.save(promocode)
    logger.info(f"🔍 After save in on_lifetime_preset, dialog_data keys: {list(dialog_manager.dialog_data.keys())}")
    logger.info(f"🔍 After save, promocodedto in dialog_data: {'promocodedto' in dialog_manager.dialog_data}")
    
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


@inject
async def on_lifetime_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
) -> None:
    """Ввод срока действия в днях (0 = неограничено)."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    if not message.text:
        return
    
    value = parse_int(message.text)
    
    if value is None or value < 0:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-promocode-invalid-lifetime"),
        )
        return
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    # 0 = неограничено (None в DTO)
    promocode.lifetime = None if value == 0 else value
    adapter.save(promocode)
    
    logger.info(f"{log(user)} Set promocode lifetime to '{promocode.lifetime}'")
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


# ==================== Ввод количества ====================

async def on_quantity_preset(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор предустановленного количества активаций."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    # Получаем значение из button_id
    preset_value = int(widget.widget_id.split("_")[-1])  # quantity_0, quantity_1, etc.
    
    # Если выбран "бесконечно" (quantity_0), устанавливаем None
    if preset_value == 0:
        promocode.max_activations = None
        logger.info(f"{log(user)} Set promocode max_activations to infinite")
    else:
        promocode.max_activations = preset_value
        logger.info(f"{log(user)} Set promocode max_activations to '{preset_value}' (preset)")
    
    adapter.save(promocode)
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)

@inject
async def on_quantity_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
) -> None:
    """Ввод максимального количества активаций (0 = неограничено)."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    if not message.text:
        return
    
    value = parse_int(message.text)
    
    if value is None or value < 0:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-promocode-invalid-quantity"),
        )
        return
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    # 0 = неограничено (None в DTO)
    promocode.max_activations = None if value == 0 else value
    adapter.save(promocode)
    
    logger.info(f"{log(user)} Set promocode max_activations to '{promocode.max_activations}'")
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


# ==================== Отмена ввода ====================


async def on_input_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена ввода в любом меню - возврат в конфигуратор без сохранения."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Cancelled input, returning to configurator")
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


async def on_type_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена выбора типа промокода - восстановление и возврат."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    # Восстанавливаем оригинальное значение
    original_type = dialog_manager.dialog_data.get("original_reward_type")
    if original_type:
        promocode.reward_type = PromocodeRewardType(original_type)
        adapter.save(promocode)
    
    # Очищаем временное хранилище
    dialog_manager.dialog_data.pop("original_reward_type", None)
    
    logger.info(f"{log(user)} Cancelled type selection")
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


async def on_type_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принятие выбора типа промокода."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Очищаем временное хранилище
    dialog_manager.dialog_data.pop("original_reward_type", None)
    
    logger.info(f"{log(user)} Accepted type selection")
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


async def on_type_enter(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Вход в меню выбора типа - сохраняем оригинальное значение."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    # Сохраняем текущий тип для возможности отмены
    dialog_manager.dialog_data["original_reward_type"] = promocode.reward_type.value
    
    logger.info(f"{log(user)} Entered type selection menu")
    await dialog_manager.switch_to(state=DashboardPromocodes.TYPE)


# ==================== Сохранение ====================


@inject
async def on_confirm_save(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
    promocode_service: FromDishka[PromocodeService],
) -> None:
    """Сохранение промокода."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    is_edit = dialog_manager.dialog_data.get("is_edit", False)
    
    try:
        if is_edit and promocode.id:
            # Обновление существующего
            result = await promocode_service.update(promocode=promocode)
            if result:
                logger.info(f"{log(user)} Updated promocode '{promocode.code}'")
                await notification_service.notify_user(
                    user=user,
                    payload=MessagePayload(i18n_key="ntf-promocode-updated"),
                )
            else:
                raise ValueError("Failed to update promocode")
        else:
            # Создание нового
            result = await promocode_service.create(promocode=promocode)
            if result:
                logger.info(f"{log(user)} Created promocode '{promocode.code}'")
                await notification_service.notify_user(
                    user=user,
                    payload=MessagePayload(i18n_key="ntf-promocode-created"),
                )
            else:
                raise ValueError("Failed to create promocode")
        
        # После сохранения возвращаемся к списку промокодов
        dialog_manager.dialog_data.pop("promocode", None)
        dialog_manager.dialog_data.pop("is_edit", None)
        await dialog_manager.switch_to(state=DashboardPromocodes.LIST)
        
    except Exception as e:
        logger.error(f"{log(user)} Failed to save promocode: {e}")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-promocode-save-error"),
        )


async def on_back_to_view(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Возврат к просмотру промокода."""
    await dialog_manager.switch_to(state=DashboardPromocodes.VIEW)


async def on_edit_promocode(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход к редактированию промокода."""
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


@inject
async def on_access_enter(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Вход в меню выбора тарифов - сохраняем оригинальное значение."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    # Сохраняем текущее значение для возможности отмены
    original_value = promocode.allowed_plan_ids.copy() if promocode.allowed_plan_ids else []
    dialog_manager.dialog_data["original_allowed_plan_ids"] = original_value
    
    logger.info(f"{log(user)} Entered plan access menu, saved original value: {original_value}")
    
    await dialog_manager.switch_to(state=DashboardPromocodes.ALLOWED)


async def on_access_select(
    callback: CallbackQuery,
    widget: Select[int],
    dialog_manager: DialogManager,
    selected_plan_id: int,
) -> None:
    """Переключатель для выбора тарифного плана доступного для промокода."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    # Инициализируем список если его нет
    if not promocode.allowed_plan_ids:
        promocode.allowed_plan_ids = []
    
    # Переключаем план в списке доступных
    if selected_plan_id in promocode.allowed_plan_ids:
        promocode.allowed_plan_ids.remove(selected_plan_id)
        logger.debug(f"{log(user)} Disabled plan {selected_plan_id} for promocode")
    else:
        promocode.allowed_plan_ids.append(selected_plan_id)
        logger.debug(f"{log(user)} Enabled plan {selected_plan_id} for promocode")
    
    adapter.save(promocode)


@inject
async def on_access_select_all(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    plan_service: FromDishka[PlanService],
) -> None:
    """Toggle: выбрать все / снять выделение со всех тарифных планов для промокода."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    # Получаем все активные планы
    all_plans = await plan_service.get_all()
    active_plan_ids = [plan.id for plan in all_plans if plan.is_active and plan.id is not None]
    
    # Toggle логика: если все уже выбраны - снимаем выделение, иначе выбираем все
    current_ids = set(promocode.allowed_plan_ids) if promocode.allowed_plan_ids else set()
    all_ids_set = set(active_plan_ids)
    
    if current_ids == all_ids_set:
        # Все уже выбраны - снимаем выделение
        promocode.allowed_plan_ids = []
        logger.info(f"{log(user)} Deselected all plans for promocode")
    else:
        # Выбираем все
        promocode.allowed_plan_ids = active_plan_ids
        logger.info(f"{log(user)} Selected all plans for promocode: {active_plan_ids}")
    
    adapter.save(promocode)


@inject
async def on_access_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена выбора тарифов - восстановление предыдущего значения и возврат."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    # Восстанавливаем оригинальное значение
    original_value = dialog_manager.dialog_data.get("original_allowed_plan_ids", [])
    promocode.allowed_plan_ids = original_value
    adapter.save(promocode)
    
    # Очищаем временное хранилище
    dialog_manager.dialog_data.pop("original_allowed_plan_ids", None)
    
    logger.info(f"{log(user)} Cancelled plan access selection, restored to: {original_value}")
    
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


@inject
async def on_access_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принятие выбора тарифов и возврат в конфигуратор."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    adapter = DialogDataAdapter(dialog_manager)
    promocode = adapter.load(PromocodeDto)
    
    if not promocode:
        raise ValueError("PromocodeDto not found in dialog data")
    
    # Очищаем временное хранилище
    dialog_manager.dialog_data.pop("original_allowed_plan_ids", None)
    
    logger.info(f"{log(user)} Accepted plan access selection: {promocode.allowed_plan_ids}")
    
    # Изменения уже сохранены в dialog_data через on_access_select
    # Просто возвращаемся в конфигуратор
    await dialog_manager.switch_to(state=DashboardPromocodes.CONFIGURATOR)


async def on_configurator_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена создания/редактирования промокода."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    is_edit = dialog_manager.dialog_data.get("is_edit", False)
    
    logger.info(f"{log(user)} Cancelled promocode {'editing' if is_edit else 'creation'}")
    
    # Очищаем данные промокода из dialog_data
    dialog_manager.dialog_data.pop("promocode", None)
    dialog_manager.dialog_data.pop("is_edit", None)
    
    if is_edit:
        # При редактировании возвращаемся к списку
        await dialog_manager.switch_to(state=DashboardPromocodes.LIST)
    else:
        # При создании нового возвращаемся в главное меню промокодов
        await dialog_manager.switch_to(state=DashboardPromocodes.MAIN)


