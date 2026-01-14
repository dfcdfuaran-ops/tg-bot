import asyncio
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager, ShowMode, StartMode
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from loguru import logger

from src.bot.states import Dashboard, DashboardSettings, MainMenu
from src.core.config import AppConfig
from src.core.constants import USER_KEY
from src.core.enums import AccessMode, ReferralRewardType
from src.core.utils.formatters import format_user_log as log
from src.infrastructure.database.models.dto import UserDto
from src.services.settings import SettingsService
from src.services.access import AccessService
from src.services.user import UserService
from src.services.referral import ReferralService


@inject
async def on_transfers_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Переход в настройки переводов."""
    # Загружаем текущие настройки при входе
    settings = await settings_service.get()
    transfer_settings = settings.features.transfers
    
    # Сохраняем начальные и текущие значения
    dialog_manager.dialog_data["initial_transfers"] = {
        "enabled": transfer_settings.enabled,
        "commission_type": transfer_settings.commission_type,
        "commission_value": transfer_settings.commission_value,
        "min_amount": transfer_settings.min_amount,
        "max_amount": transfer_settings.max_amount,
    }
    
    dialog_manager.dialog_data["current_transfers"] = {
        "enabled": transfer_settings.enabled,
        "commission_type": transfer_settings.commission_type,
        "commission_value": transfer_settings.commission_value,
        "min_amount": transfer_settings.min_amount,
        "max_amount": transfer_settings.max_amount,
    }
    
    await dialog_manager.switch_to(DashboardSettings.TRANSFERS)


@inject
async def on_toggle_transfers_enabled(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Toggle включения/выключения переводов."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_transfers", {})
    current["enabled"] = not current.get("enabled", True)
    dialog_manager.dialog_data["current_transfers"] = current
    logger.info(f"{log(user)} Toggle transfers enabled (not saved yet)")


@inject
async def on_select_commission_type(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Изменение типа комиссии (радиокнопка)."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    # widget_id может быть "commission_type_percent" или "commission_type_fixed"
    commission_type = "percent" if "percent" in widget.widget_id else "fixed"
    
    current = dialog_manager.dialog_data.get("current_transfers", {})
    current["commission_type"] = commission_type
    current["commission_value"] = 0  # Устанавливаем 0 при переключении типа
    dialog_manager.dialog_data["current_transfers"] = current
    
    logger.info(f"{log(user)} Changed transfer commission type to '{commission_type}'")



@inject
async def on_set_commission_type(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Установка типа комиссии."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    commission_type = widget.widget_id  # "percent" or "fixed"
    
    current = dialog_manager.dialog_data.get("current_transfers", {})
    current["commission_type"] = commission_type
    current["commission_value"] = 0  # Устанавливаем 0 при переключении типа
    dialog_manager.dialog_data["current_transfers"] = current
    
    logger.info(f"{log(user)} Set transfer commission type to '{commission_type}' (not saved yet)")
    await dialog_manager.switch_to(DashboardSettings.TRANSFERS)


@inject
async def on_select_commission_value(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход к вводу значения комиссии."""
    await dialog_manager.switch_to(DashboardSettings.TRANSFERS_COMMISSION_VALUE)


@inject
async def on_commission_value_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    """Обработка ввода значения комиссии."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_transfers", {})
    
    try:
        value = float(message.text.strip().replace(",", "."))
        
        commission_type = current.get("commission_type", "percent")
        
        if commission_type == "percent":
            if not (0 <= value <= 100):
                await message.answer("⚠️ Для процентной комиссии введите число от 0 до 100!")
                return
        else:  # fixed
            if value < 0:
                await message.answer("⚠️ Для фиксированной комиссии введите число больше или равное 0!")
                return
        
        current["commission_value"] = value
        dialog_manager.dialog_data["current_transfers"] = current
        
        logger.info(f"{log(user)} Set transfer commission value to '{value}' (not saved yet)")
        try:
            await message.delete()
        except Exception:
            pass
        await dialog_manager.switch_to(DashboardSettings.TRANSFERS)
        
    except ValueError:
        await message.answer("⚠️ Введите корректное число!")


@inject
async def on_select_min_amount(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход к вводу минимальной суммы."""
    await dialog_manager.switch_to(DashboardSettings.TRANSFERS_MIN_AMOUNT)


@inject
async def on_min_amount_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    """Обработка ввода минимальной суммы."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_transfers", {})
    
    try:
        value = float(message.text.strip().replace(",", "."))
        if value < 0:
            await message.answer("⚠️ Введите положительное число!")
            return
        
        # Проверяем что минимум не больше максимума
        max_amount = current.get("max_amount", 100000)
        if value > max_amount:
            await message.answer(f"⚠️ Минимум не может быть больше максимума ({max_amount})!")
            return
        
        current["min_amount"] = value
        dialog_manager.dialog_data["current_transfers"] = current
        
        logger.info(f"{log(user)} Set transfer min amount to '{value}' (not saved yet)")
        try:
            await message.delete()
        except Exception:
            pass
        await dialog_manager.switch_to(DashboardSettings.TRANSFERS)
        
    except ValueError:
        await message.answer("⚠️ Введите корректное число!")


@inject
async def on_select_max_amount(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход к вводу максимальной суммы."""
    await dialog_manager.switch_to(DashboardSettings.TRANSFERS_MAX_AMOUNT)


@inject
async def on_max_amount_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    """Обработка ввода максимальной суммы."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_transfers", {})
    
    try:
        value = float(message.text.strip().replace(",", "."))
        if value < 0:
            await message.answer("⚠️ Введите положительное число!")
            return
        
        # Проверяем что максимум больше минимума
        min_amount = current.get("min_amount", 10)
        if value < min_amount:
            await message.answer(f"⚠️ Максимум не может быть меньше минимума ({min_amount})!")
            return
        
        current["max_amount"] = value
        dialog_manager.dialog_data["current_transfers"] = current
        
        logger.info(f"{log(user)} Set transfer max amount to '{value}' (not saved yet)")
        try:
            await message.delete()
        except Exception:
            pass
        await dialog_manager.switch_to(DashboardSettings.TRANSFERS)
        
    except ValueError:
        await message.answer("⚠️ Введите корректное число!")


@inject
async def on_cancel_transfers(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена - сбросить временные изменения."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Восстанавливаем начальные значения в current
    initial = dialog_manager.dialog_data.get("initial_transfers", {})
    dialog_manager.dialog_data["current_transfers"] = initial.copy()
    
    logger.info(f"{log(user)} Cancelled transfer settings changes")
    
    # Очищаем данные
    dialog_manager.dialog_data.pop("initial_transfers", None)
    dialog_manager.dialog_data.pop("current_transfers", None)
    
    # Возвращаемся в главное меню настроек
    await dialog_manager.switch_to(DashboardSettings.MAIN)


@inject
async def on_accept_transfers(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Принять изменения - сохранить в базу."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_transfers", {})
    
    if current:
        # Применяем все изменения
        await settings_service.update_transfer_settings(
            enabled=current.get("enabled"),
            commission_type=current.get("commission_type"),
            commission_value=current.get("commission_value"),
            min_amount=current.get("min_amount"),
            max_amount=current.get("max_amount"),
        )
        
        logger.info(f"{log(user)} Accepted and saved transfer settings changes")
    
    # Очищаем данные
    dialog_manager.dialog_data.pop("initial_transfers", None)
    dialog_manager.dialog_data.pop("current_transfers", None)
    
    # Возвращаемся в главное меню настроек
    await dialog_manager.switch_to(DashboardSettings.MAIN)


# === Обработчики для кнопок выбора предустановленных значений ===

@inject
async def on_commission_preset_select(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор предустановленного значения комиссии."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    # widget_id может быть "commission_1", "commission_5", "commission_50", "commission_free", и т.д.
    if widget.widget_id == "commission_free":
        value = 0
    elif widget.widget_id == "manual_input_dummy":
        # Это кнопка "Ручной ввод", не делаем ничего
        return
    else:
        # Убираем префикс и суффикс для корректного парсинга
        widget_id = widget.widget_id.replace("commission_", "")
        # Убираем суффикс _percent если есть
        widget_id = widget_id.replace("_percent", "")
        value = int(widget_id)
    
    current = dialog_manager.dialog_data.get("current_transfers", {})
    current["commission_value"] = value
    dialog_manager.dialog_data["current_transfers"] = current
    
    logger.info(f"{log(user)} Selected commission preset: {value}")


@inject
async def on_commission_manual_input_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переключение в режим ручного ввода комиссии."""
    await dialog_manager.switch_to(DashboardSettings.TRANSFERS_COMMISSION_MANUAL)


@inject
async def on_commission_manual_value_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    """Обработка ручного ввода значения комиссии."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_transfers", {})
    
    try:
        value = float(message.text.strip().replace(",", "."))
        
        commission_type = current.get("commission_type", "percent")
        
        if commission_type == "percent":
            if not (0 <= value <= 100):
                await message.answer("⚠️ Для процентной комиссии введите число от 0 до 100!")
                return
        else:  # fixed
            if value < 0:
                await message.answer("⚠️ Для фиксированной комиссии введите число больше или равное 0!")
                return
        
        current["commission_value"] = value
        dialog_manager.dialog_data["current_transfers"] = current
        
        logger.info(f"{log(user)} Set transfer commission value to '{value}' (not saved yet)")
        
        # Возвращаемся к окну выбора значения
        await dialog_manager.switch_to(DashboardSettings.TRANSFERS_COMMISSION_VALUE)
        
        try:
            await message.delete()
        except Exception:
            pass
        
    except ValueError:
        await message.answer("⚠️ Введите корректное число!")


@inject
async def on_commission_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Отмена изменения комиссии."""
    dialog_manager.dialog_data.pop("commission_manual_input_mode", None)
    
    # Отменяем только изменения commission_value, остальные изменения сохраняем
    current = dialog_manager.dialog_data.get("current_transfers")
    if current:
        # Загружаем текущее значение комиссии из БД
        settings = await settings_service.get()
        current["commission_value"] = settings.features.transfers.commission_value
        dialog_manager.dialog_data["current_transfers"] = current
    
    await dialog_manager.switch_to(DashboardSettings.TRANSFERS)


@inject
async def on_commission_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принятие изменения комиссии."""
    dialog_manager.dialog_data.pop("commission_manual_input_mode", None)
    await dialog_manager.switch_to(DashboardSettings.TRANSFERS)


@inject
async def on_min_amount_preset_select(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор предустановленного значения минимальной суммы."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    # widget_id может быть "amount_no_limit", "amount_10", "amount_50", и т.д.
    if widget.widget_id == "amount_no_limit":
        value = None  # Без ограничений
    else:
        value = int(widget.widget_id.replace("amount_", ""))
    
    current = dialog_manager.dialog_data.get("current_transfers", {})
    current["min_amount"] = value
    dialog_manager.dialog_data["current_transfers"] = current
    
    logger.info(f"{log(user)} Selected min amount preset: {value}")


@inject
async def on_min_amount_manual_input_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переключение в режим ручного ввода минимальной суммы."""
    await dialog_manager.switch_to(DashboardSettings.TRANSFERS_MIN_AMOUNT_MANUAL)


@inject
async def on_min_amount_manual_value_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    """Обработка ручного ввода минимальной суммы."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_transfers", {})
    
    try:
        value = float(message.text.strip().replace(",", "."))
        if value < 0:
            await message.answer("⚠️ Введите положительное число!")
            return
        
        # Проверяем что минимум не больше максимума
        max_amount = current.get("max_amount")
        if max_amount is not None and value > max_amount:
            await message.answer(f"⚠️ Минимум не может быть больше максимума ({int(max_amount)} ₽)!")
            return
        
        current["min_amount"] = value
        dialog_manager.dialog_data["current_transfers"] = current
        
        logger.info(f"{log(user)} Set min amount via manual input: {value}")
        try:
            await message.delete()
        except Exception:
            pass
        await dialog_manager.switch_to(DashboardSettings.TRANSFERS_MIN_AMOUNT)
        
    except ValueError:
        await message.answer("⚠️ Введите корректное число!")


@inject
async def on_min_amount_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Отмена изменения минимальной суммы."""
    # Отменяем только изменения min_amount, остальные изменения сохраняем
    current = dialog_manager.dialog_data.get("current_transfers")
    if current:
        # Загружаем текущее значение из БД
        settings = await settings_service.get()
        current["min_amount"] = settings.features.transfers.min_amount
        dialog_manager.dialog_data["current_transfers"] = current
    
    await dialog_manager.switch_to(DashboardSettings.TRANSFERS)


@inject
async def on_min_amount_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принятие изменения минимальной суммы."""
    await dialog_manager.switch_to(DashboardSettings.TRANSFERS)


@inject
async def on_max_amount_preset_select(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор предустановленного значения максимальной суммы."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    # widget_id может быть "amount_no_limit", "amount_1000", "amount_5000", и т.д.
    if widget.widget_id == "amount_no_limit":
        value = None  # Без ограничений
    else:
        value = int(widget.widget_id.replace("amount_", ""))
    
    current = dialog_manager.dialog_data.get("current_transfers", {})
    current["max_amount"] = value
    dialog_manager.dialog_data["current_transfers"] = current
    
    logger.info(f"{log(user)} Selected max amount preset: {value}")


@inject
async def on_max_amount_manual_input_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переключение в режим ручного ввода максимальной суммы."""
    await dialog_manager.switch_to(DashboardSettings.TRANSFERS_MAX_AMOUNT_MANUAL)


@inject
async def on_max_amount_manual_value_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    """Обработка ручного ввода максимальной суммы."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_transfers", {})
    
    try:
        value = float(message.text.strip().replace(",", "."))
        if value < 0:
            await message.answer("⚠️ Введите положительное число!")
            return
        
        # Проверяем что максимум больше минимума
        min_amount = current.get("min_amount")
        if min_amount is not None and value < min_amount:
            await message.answer(f"⚠️ Максимум не может быть меньше минимума ({int(min_amount)} ₽)!")
            return
        
        current["max_amount"] = value
        dialog_manager.dialog_data["current_transfers"] = current
        
        logger.info(f"{log(user)} Set max amount via manual input: {value}")
        try:
            await message.delete()
        except Exception:
            pass
        await dialog_manager.switch_to(DashboardSettings.TRANSFERS_MAX_AMOUNT)
        
    except ValueError:
        await message.answer("⚠️ Введите корректное число!")


@inject
async def on_max_amount_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Отмена изменения максимальной суммы."""
    # Отменяем только изменения max_amount, остальные изменения сохраняем
    current = dialog_manager.dialog_data.get("current_transfers")
    if current:
        # Загружаем текущее значение из БД
        settings = await settings_service.get()
        current["max_amount"] = settings.features.transfers.max_amount
        dialog_manager.dialog_data["current_transfers"] = current
    
    await dialog_manager.switch_to(DashboardSettings.TRANSFERS)


@inject
async def on_max_amount_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принятие изменения максимальной суммы."""
    await dialog_manager.switch_to(DashboardSettings.TRANSFERS)


@inject
async def on_back_to_dashboard(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Возврат в главную панель управления."""
    await dialog_manager.start(Dashboard.MAIN, mode=StartMode.RESET_STACK)


@inject
async def on_back_to_main_menu(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Возврат в главное меню бота."""
    await dialog_manager.start(MainMenu.MAIN, mode=StartMode.RESET_STACK)


# === Обработчики для включения/выключения функций ===

@inject
async def on_extra_devices_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход в настройки доп. устройств."""
    await dialog_manager.switch_to(DashboardSettings.EXTRA_DEVICES)


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
@inject
async def on_balance_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Переход в настройки баланса."""
    # Загружаем текущие настройки при входе
    settings = await settings_service.get()
    features = settings.features
    
    # Сохраняем начальные и текущие значения
    dialog_manager.dialog_data["initial_balance"] = {
        "enabled": features.balance_enabled,
        "balance_min_amount": features.balance_min_amount,
        "balance_max_amount": features.balance_max_amount,
    }
    
    dialog_manager.dialog_data["current_balance"] = {
        "enabled": features.balance_enabled,
        "balance_min_amount": features.balance_min_amount,
        "balance_max_amount": features.balance_max_amount,
    }
    
    await dialog_manager.switch_to(DashboardSettings.BALANCE)


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
async def on_toggle_transfers(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Toggle функционала переводов."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    new_value = await settings_service.toggle_transfers()
    logger.info(f"{log(user)} Toggled transfers_enabled -> {new_value}")


@inject
async def on_community_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Переход в настройки сообщества."""
    # Загружаем текущие настройки при входе
    settings = await settings_service.get()
    community_url = settings.features.community_url or ""
    
    # Сохраняем начальные и текущие значения
    dialog_manager.dialog_data["initial_community"] = {
        "enabled": settings.features.community_enabled,
        "url": community_url,
    }
    
    dialog_manager.dialog_data["current_community"] = {
        "enabled": settings.features.community_enabled,
        "url": community_url,
    }
    
    await dialog_manager.switch_to(DashboardSettings.COMMUNITY)


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
async def on_set_community_url(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход к вводу URL сообщества."""
    await dialog_manager.switch_to(DashboardSettings.COMMUNITY_URL_MANUAL)


@inject
async def on_community_url_input(
    message: Message,
    message_input: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    """Обработка ввода URL сообщества."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    url = message.text.strip()
    
    # Валидация URL
    import re
    tg_url_pattern = r'^https://t\.me/[\w+\-/]+'
    
    if not re.match(tg_url_pattern, url):
        # Отправляем предупреждающее сообщение
        warning_msg = await message.answer(
            "⚠️ Некорректный формат ссылки. Используйте формат: https://t.me/+код или https://t.me/название_группы",
            parse_mode="HTML"
        )
        
        # Удаляем сообщение через 5 секунд
        async def delete_warning():
            try:
                await asyncio.sleep(5)
                await warning_msg.delete()
            except Exception as e:
                logger.debug(f"Failed to delete warning message: {e}")
        asyncio.create_task(delete_warning())
        return
    
    current = dialog_manager.dialog_data.get("current_community", {})
    current["url"] = url
    dialog_manager.dialog_data["current_community"] = current
    
    logger.info(f"{log(user)} Set Community URL to '{url}' (not saved yet)")
    try:
        await message.delete()
    except Exception:
        pass
    
    # Устанавливаем режим замены сообщения, чтобы не создавать новое
    dialog_manager.show_mode = ShowMode.DELETE_AND_SEND
    await dialog_manager.switch_to(DashboardSettings.COMMUNITY)


@inject
async def on_accept_community(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Сохранение настроек сообщества."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_community", {})
    
    # Обновляем URL сообщества в БД
    if "url" in current:
        settings = await settings_service.get()
        settings.features.community_url = current.get("url", "")
        await settings_service.update(settings)
        
        logger.info(f"{log(user)} Updated Community URL to '{current.get('url')}'")
    
    # Очищаем временные данные
    dialog_manager.dialog_data.pop("initial_community", None)
    dialog_manager.dialog_data.pop("current_community", None)
    
    logger.info(f"{log(user)} Accepted Community settings")
    await dialog_manager.switch_to(DashboardSettings.MAIN)


@inject
async def on_cancel_community(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена изменений настроек сообщества."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Восстанавливаем начальные значения
    initial = dialog_manager.dialog_data.get("initial_community", {})
    dialog_manager.dialog_data["current_community"] = initial.copy()
    
    logger.info(f"{log(user)} Cancelled Community settings")
    await dialog_manager.switch_to(DashboardSettings.MAIN)


@inject
async def on_tos_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Переход в настройки соглашения."""
    # Загружаем текущие настройки при входе
    settings = await settings_service.get()
    tos_url = settings.rules_link.get_secret_value()
    
    # Сохраняем начальные и текущие значения
    dialog_manager.dialog_data["initial_tos"] = {
        "enabled": settings.features.tos_enabled,
        "url": tos_url,
    }
    
    dialog_manager.dialog_data["current_tos"] = {
        "enabled": settings.features.tos_enabled,
        "url": tos_url,
    }
    
    await dialog_manager.switch_to(DashboardSettings.TOS)


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
async def on_toggle_notifications(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Toggle отправки уведомлений пользователям."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    new_value = await settings_service.toggle_feature("notifications_enabled")
    logger.info(f"{log(user)} Toggled notifications_enabled -> {new_value}")

@inject
async def on_toggle_access(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    access_service: FromDishka[AccessService],
) -> None:
    """Переключение глобального доступа к боту."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    settings = await settings_service.get()
    
    # Переключаем access_enabled
    new_access_value = not settings.features.access_enabled
    settings.features.access_enabled = new_access_value
    
    # Если доступ выключен - устанавливаем режим RESTRICTED и запрещаем всё
    if not new_access_value:
        settings.access_mode = AccessMode.RESTRICTED
        settings.registration_allowed = False
        settings.purchases_allowed = False
        logger.info(f"{log(user)} Access disabled -> mode=RESTRICTED, registration=False, purchases=False")
    else:
        # Если доступ включен - устанавливаем режим PUBLIC и разрешаем всё
        settings.access_mode = AccessMode.PUBLIC
        settings.registration_allowed = True
        settings.purchases_allowed = True
        logger.info(f"{log(user)} Access enabled -> mode=PUBLIC, registration=True, purchases=True")
    
    settings.features = settings.features  # Trigger change tracking
    await settings_service.update(settings)
    
    logger.info(
        f"{log(user)} Toggled access_enabled -> {new_access_value}"
    )

@inject
async def on_toggle_referral(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Toggle реферальной системы."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    settings = await settings_service.get()
    new_value = not settings.referral.enable
    settings.referral.enable = new_value
    
    # Также обновляем feature flag
    settings.features.referral_enabled = new_value
    settings.features = settings.features  # Trigger change tracking
    
    await settings_service.update(settings)
    
    logger.info(f"{log(user)} Toggled referral_enabled -> {new_value}")

# === Меню доп. устройств ===

@inject
async def on_extra_devices_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход в настройки доп. устройств."""
    await dialog_manager.switch_to(DashboardSettings.EXTRA_DEVICES)


@inject
async def on_toggle_extra_devices_payment_type(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переключение типа оплаты доп. устройств (разовая/ежемесячная)."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    button_id = widget.widget_id
    is_one_time = button_id == "toggle_one_time"
    
    dialog_manager.dialog_data["pending_extra_devices_payment_type"] = is_one_time
    logger.info(f"{log(user)} Changed extra devices payment type to {'one-time' if is_one_time else 'monthly'}")


@inject
async def on_edit_extra_devices_price(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход к окну изменения цены доп. устройств."""
    await dialog_manager.switch_to(DashboardSettings.EXTRA_DEVICES_PRICE)


@inject
async def on_extra_devices_preset_price_select(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор предустановленной цены для доп. устройств."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    price = int(widget.widget_id.replace("preset_", ""))
    
    dialog_manager.dialog_data["pending_extra_devices_price"] = price
    logger.info(f"{log(user)} Selected extra devices price preset: {price}")


@inject
async def on_extra_devices_manual_price_mode(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход в режим ручного ввода цены."""
    await dialog_manager.switch_to(DashboardSettings.EXTRA_DEVICES_PRICE_MANUAL)


@inject
async def on_extra_devices_price_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    """Обработка ручного ввода цены доп. устройств."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    try:
        price = int(message.text.strip())
        if price < 0:
            await message.answer("⚠️ Цена не может быть отрицательной!")
            return
        
        dialog_manager.dialog_data["pending_extra_devices_price"] = price
        logger.info(f"{log(user)} Entered manual extra devices price: {price}")
        
        try:
            await message.delete()
        except Exception:
            pass
        
        await dialog_manager.switch_to(DashboardSettings.EXTRA_DEVICES_PRICE)
        
    except ValueError:
        await message.answer("⚠️ Введите корректное число!")


@inject
async def on_cancel_extra_devices_price(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена изменения цены - возврат к настройкам доп. устройств."""
    dialog_manager.dialog_data.pop("pending_extra_devices_price", None)
    await dialog_manager.switch_to(DashboardSettings.EXTRA_DEVICES)


@inject
async def on_accept_extra_devices_price(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Подтверждение выбора цены - возврат к настройкам доп. устройств."""
    # Цена уже сохранена в pending_extra_devices_price, 
    # она будет применена при нажатии "Принять" в главном окне настроек
    await dialog_manager.switch_to(DashboardSettings.EXTRA_DEVICES)


@inject
async def on_cancel_extra_devices(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена изменений в настройках доп. устройств."""
    dialog_manager.dialog_data.pop("pending_extra_devices_payment_type", None)
    dialog_manager.dialog_data.pop("pending_extra_devices_price", None)
    await dialog_manager.switch_to(DashboardSettings.MAIN)


@inject
async def on_accept_extra_devices(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Сохранение настроек доп. устройств."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    pending_payment_type = dialog_manager.dialog_data.get("pending_extra_devices_payment_type")
    pending_price = dialog_manager.dialog_data.get("pending_extra_devices_price")
    
    if pending_payment_type is not None:
        await settings_service.toggle_extra_devices_payment_type()
        logger.info(f"{log(user)} Updated extra devices payment type")
        dialog_manager.dialog_data.pop("pending_extra_devices_payment_type", None)
    
    if pending_price is not None:
        await settings_service.set_extra_device_price(pending_price)
        logger.info(f"{log(user)} Updated extra devices price to {pending_price}")
        dialog_manager.dialog_data.pop("pending_extra_devices_price", None)
    
    await dialog_manager.switch_to(DashboardSettings.MAIN)


# === Глобальная скидка ===

@inject
async def on_global_discount_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Переход в настройки глобальной скидки."""
    # Загружаем текущие настройки при входе
    settings = await settings_service.get()
    discount_settings = settings.features.global_discount
    
    # Сохраняем начальные и текущие значения
    dialog_manager.dialog_data["initial_global_discount"] = {
        "enabled": discount_settings.enabled,
        "discount_type": discount_settings.discount_type,
        "discount_value": discount_settings.discount_value,
        "stack_discounts": discount_settings.stack_discounts,
        "apply_to_subscription": discount_settings.apply_to_subscription,
        "apply_to_extra_devices": discount_settings.apply_to_extra_devices,
        "apply_to_transfer_commission": discount_settings.apply_to_transfer_commission,
    }
    
    dialog_manager.dialog_data["current_global_discount"] = {
        "enabled": discount_settings.enabled,
        "discount_type": discount_settings.discount_type,
        "discount_value": discount_settings.discount_value,
        "stack_discounts": discount_settings.stack_discounts,
        "apply_to_subscription": discount_settings.apply_to_subscription,
        "apply_to_extra_devices": discount_settings.apply_to_extra_devices,
        "apply_to_transfer_commission": discount_settings.apply_to_transfer_commission,
    }
    
    await dialog_manager.switch_to(DashboardSettings.GLOBAL_DISCOUNT)


@inject
async def on_toggle_global_discount(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Toggle функционала глобальной скидки."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    new_value = await settings_service.toggle_global_discount()
    logger.info(f"{log(user)} Toggled global_discount_enabled -> {new_value}")


@inject
async def on_toggle_stack_discounts(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Toggle складывания скидок."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_global_discount", {})
    current["stack_discounts"] = not current.get("stack_discounts", False)
    dialog_manager.dialog_data["current_global_discount"] = current
    logger.info(f"{log(user)} Toggled stack_discounts -> {current['stack_discounts']}")


@inject
async def on_toggle_apply_to_subscription(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Toggle применения скидки к подписке."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_global_discount", {})
    current["apply_to_subscription"] = not current.get("apply_to_subscription", True)
    dialog_manager.dialog_data["current_global_discount"] = current
    logger.info(f"{log(user)} Toggled apply_to_subscription -> {current['apply_to_subscription']}")


@inject
async def on_toggle_apply_to_extra_devices(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Toggle применения скидки к доп. устройствам."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_global_discount", {})
    current["apply_to_extra_devices"] = not current.get("apply_to_extra_devices", False)
    dialog_manager.dialog_data["current_global_discount"] = current
    logger.info(f"{log(user)} Toggled apply_to_extra_devices -> {current['apply_to_extra_devices']}")


@inject
async def on_toggle_apply_to_transfer_commission(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Toggle применения скидки к комиссии переводов."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_global_discount", {})
    current["apply_to_transfer_commission"] = not current.get("apply_to_transfer_commission", False)
    dialog_manager.dialog_data["current_global_discount"] = current
    logger.info(f"{log(user)} Toggled apply_to_transfer_commission -> {current['apply_to_transfer_commission']}")


@inject
async def on_select_global_discount_type(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Изменение типа скидки (радиокнопка)."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    # widget_id может быть "discount_type_percent" или "discount_type_fixed"
    discount_type = "percent" if "percent" in widget.widget_id else "fixed"
    
    current = dialog_manager.dialog_data.get("current_global_discount", {})
    current["discount_type"] = discount_type
    current["discount_value"] = 0  # Устанавливаем 0 при переключении типа
    dialog_manager.dialog_data["current_global_discount"] = current
    
    logger.info(f"{log(user)} Changed global discount type to '{discount_type}'")


@inject
async def on_select_global_discount_value(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход к вводу значения скидки."""
    await dialog_manager.switch_to(DashboardSettings.GLOBAL_DISCOUNT_VALUE)


@inject
async def on_global_discount_preset_select(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор предустановленного значения скидки."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    # widget_id может быть "discount_free", "discount_5", "discount_50", и т.д.
    if widget.widget_id == "discount_free":
        value = 0
    elif widget.widget_id == "manual_input_dummy":
        # Это кнопка "Ручной ввод", не делаем ничего
        return
    else:
        # Убираем префикс и суффикс для корректного парсинга
        widget_id = widget.widget_id.replace("discount_", "")
        # Убираем суффикс _percent если есть
        widget_id = widget_id.replace("_percent", "")
        value = int(widget_id)
    
    current = dialog_manager.dialog_data.get("current_global_discount", {})
    current["discount_value"] = value
    dialog_manager.dialog_data["current_global_discount"] = current
    
    logger.info(f"{log(user)} Selected global discount preset: {value}")


@inject
async def on_global_discount_manual_input_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переключение в режим ручного ввода скидки."""
    await dialog_manager.switch_to(DashboardSettings.GLOBAL_DISCOUNT_MANUAL)


@inject
async def on_global_discount_manual_value_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    """Обработка ручного ввода значения скидки."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_global_discount", {})
    
    try:
        value = float(message.text.strip().replace(",", "."))
        
        discount_type = current.get("discount_type", "percent")
        
        if discount_type == "percent":
            if not (0 <= value <= 100):
                await message.answer("⚠️ Для процентной скидки введите число от 0 до 100!")
                return
        else:  # fixed
            if value < 0:
                await message.answer("⚠️ Для фиксированной скидки введите число больше или равное 0!")
                return
        
        current["discount_value"] = value
        dialog_manager.dialog_data["current_global_discount"] = current
        
        logger.info(f"{log(user)} Set global discount value to '{value}' (not saved yet)")
        
        # Возвращаемся к окну выбора значения
        await dialog_manager.switch_to(DashboardSettings.GLOBAL_DISCOUNT_VALUE)
        
        try:
            await message.delete()
        except Exception:
            pass
        
    except ValueError:
        await message.answer("⚠️ Введите корректное число!")


@inject
async def on_cancel_global_discount_manual(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена ручного ввода скидки - восстановить значение из исходного состояния."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Восстанавливаем discount_value из исходного состояния
    initial = dialog_manager.dialog_data.get("initial_global_discount", {})
    current = dialog_manager.dialog_data.get("current_global_discount", {})
    
    current["discount_value"] = initial.get("discount_value")
    
    dialog_manager.dialog_data["current_global_discount"] = current
    logger.info(f"{log(user)} Cancelled manual discount value input in global discount settings")
    
    await dialog_manager.switch_to(DashboardSettings.GLOBAL_DISCOUNT_VALUE)


@inject
async def on_global_discount_value_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена изменения скидки - восстановить из исходного состояния."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Восстанавливаем значения discount_type и discount_value из исходного состояния
    initial = dialog_manager.dialog_data.get("initial_global_discount", {})
    current = dialog_manager.dialog_data.get("current_global_discount", {})
    
    current["discount_type"] = initial.get("discount_type")
    current["discount_value"] = initial.get("discount_value")
    
    dialog_manager.dialog_data["current_global_discount"] = current
    logger.info(f"{log(user)} Cancelled discount type/value changes in global discount settings")
    
    await dialog_manager.switch_to(DashboardSettings.GLOBAL_DISCOUNT)


@inject
async def on_global_discount_value_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принятие изменения скидки - вернуться к главному меню."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Accepted discount type/value changes in global discount settings")
    await dialog_manager.switch_to(DashboardSettings.GLOBAL_DISCOUNT)


@inject
async def on_global_discount_apply_to_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход в меню 'Влияние'."""
    await dialog_manager.switch_to(DashboardSettings.GLOBAL_DISCOUNT_APPLY_TO)


@inject
async def on_global_discount_mode_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход в меню 'Режим'."""
    await dialog_manager.switch_to(DashboardSettings.GLOBAL_DISCOUNT_MODE)


@inject
async def on_select_discount_mode(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор режима применения скидок."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    # widget_id может быть "mode_max" или "mode_stack"
    stack_discounts = widget.widget_id == "mode_stack"
    
    current = dialog_manager.dialog_data.get("current_global_discount", {})
    current["stack_discounts"] = stack_discounts
    dialog_manager.dialog_data["current_global_discount"] = current
    
    logger.info(f"{log(user)} Selected discount mode: {'stack' if stack_discounts else 'max'}")


@inject
async def on_cancel_global_discount_apply_to(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена изменений в меню 'Влияние' - восстановить исходные значения."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Восстанавливаем значения apply_to_* из исходного состояния
    initial = dialog_manager.dialog_data.get("initial_global_discount", {})
    current = dialog_manager.dialog_data.get("current_global_discount", {})
    
    current["apply_to_subscription"] = initial.get("apply_to_subscription")
    current["apply_to_extra_devices"] = initial.get("apply_to_extra_devices")
    current["apply_to_transfer_commission"] = initial.get("apply_to_transfer_commission")
    
    dialog_manager.dialog_data["current_global_discount"] = current
    logger.info(f"{log(user)} Cancelled apply_to changes in global discount settings")
    
    await dialog_manager.switch_to(DashboardSettings.GLOBAL_DISCOUNT)


@inject
async def on_accept_global_discount_apply_to(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принять изменения в меню 'Влияние' - сохранить и вернуться."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Accepted apply_to changes in global discount settings")
    await dialog_manager.switch_to(DashboardSettings.GLOBAL_DISCOUNT)


@inject
async def on_cancel_global_discount_mode(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена изменений в меню 'Режим' - восстановить исходное значение."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Восстанавливаем stack_discounts из исходного состояния
    initial = dialog_manager.dialog_data.get("initial_global_discount", {})
    current = dialog_manager.dialog_data.get("current_global_discount", {})
    
    current["stack_discounts"] = initial.get("stack_discounts")
    
    dialog_manager.dialog_data["current_global_discount"] = current
    logger.info(f"{log(user)} Cancelled mode changes in global discount settings")
    
    await dialog_manager.switch_to(DashboardSettings.GLOBAL_DISCOUNT)


@inject
async def on_accept_global_discount_mode(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принять изменения в меню 'Режим' - сохранить и вернуться."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Accepted mode changes in global discount settings")
    await dialog_manager.switch_to(DashboardSettings.GLOBAL_DISCOUNT)


@inject
async def on_cancel_global_discount(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена - сбросить временные изменения."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Восстанавливаем начальные значения в current
    initial = dialog_manager.dialog_data.get("initial_global_discount", {})
    dialog_manager.dialog_data["current_global_discount"] = initial.copy()
    
    logger.info(f"{log(user)} Cancelled global discount settings changes")
    
    # Очищаем данные
    dialog_manager.dialog_data.pop("initial_global_discount", None)
    dialog_manager.dialog_data.pop("current_global_discount", None)
    
    # Возвращаемся в главное меню настроек
    await dialog_manager.switch_to(DashboardSettings.MAIN)


@inject
async def on_accept_global_discount(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Принять изменения - сохранить в базу."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_global_discount", {})
    
    if current:
        # Применяем все изменения
        await settings_service.update_global_discount_settings(
            enabled=current.get("enabled"),
            discount_type=current.get("discount_type"),
            discount_value=current.get("discount_value"),
            stack_discounts=current.get("stack_discounts"),
            apply_to_subscription=current.get("apply_to_subscription"),
            apply_to_extra_devices=current.get("apply_to_extra_devices"),
            apply_to_transfer_commission=current.get("apply_to_transfer_commission"),
        )
        
        logger.info(f"{log(user)} Accepted and saved global discount settings changes")
    
    # Очищаем данные
    dialog_manager.dialog_data.pop("initial_global_discount", None)
    dialog_manager.dialog_data.pop("current_global_discount", None)
    
    # Возвращаемся в главное меню настроек
    await dialog_manager.switch_to(DashboardSettings.MAIN)

# ================= BALANCE SETTINGS HANDLERS =================


@inject
async def on_select_balance_min_amount(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход в меню выбора минимальной суммы пополнения баланса."""
    await dialog_manager.switch_to(DashboardSettings.BALANCE_MIN_AMOUNT)


@inject
async def on_select_balance_max_amount(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход в меню выбора максимальной суммы пополнения баланса."""
    await dialog_manager.switch_to(DashboardSettings.BALANCE_MAX_AMOUNT)


@inject
async def on_balance_min_amount_preset_select(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор предустановленной минимальной суммы."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    widget_id = widget.widget_id
    
    current = dialog_manager.dialog_data.get("current_balance", {})
    
    if widget_id == "amount_no_limit":
        current["balance_min_amount"] = None
        logger.info(f"{log(user)} Set balance min amount to no limit")
    else:
        # Извлекаем сумму из widget_id (например, "amount_50" -> 50)
        amount = int(widget_id.split("_")[1])
        current["balance_min_amount"] = amount
        logger.info(f"{log(user)} Set balance min amount to {amount}")
    
    dialog_manager.dialog_data["current_balance"] = current


@inject
async def on_balance_min_amount_manual_input_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переключение в режим ручного ввода минимальной суммы."""
    await dialog_manager.switch_to(DashboardSettings.BALANCE_MIN_AMOUNT_MANUAL)


@inject
async def on_balance_min_amount_manual_value_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    """Обработка ручного ввода минимальной суммы."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_balance", {})
    
    try:
        value = float(message.text.strip().replace(",", "."))
        if value < 0:
            error_msg = await message.answer("❗️ Введите положительное число!")
            # Удаляем сообщение об ошибке через 5 секунд
            import asyncio
            async def delete_after_delay():
                await asyncio.sleep(5)
                try:
                    await error_msg.delete()
                except Exception:
                    pass
            asyncio.create_task(delete_after_delay())
            return
        
        # Проверяем что минимум не больше максимума
        max_amount = current.get("balance_max_amount")
        if max_amount is not None and value > max_amount:
            error_msg = await message.answer(f"❗️ Минимум не может быть больше максимума ({int(max_amount)} ₽)!")
            # Удаляем сообщение об ошибке через 5 секунд
            import asyncio
            async def delete_after_delay():
                await asyncio.sleep(5)
                try:
                    await error_msg.delete()
                except Exception:
                    pass
            asyncio.create_task(delete_after_delay())
            return
        
        current["balance_min_amount"] = value
        dialog_manager.dialog_data["current_balance"] = current
        
        logger.info(f"{log(user)} Set balance min amount via manual input: {value}")
        try:
            await message.delete()
        except Exception:
            pass
        await dialog_manager.switch_to(DashboardSettings.BALANCE_MIN_AMOUNT)
        
    except ValueError:
        error_msg = await message.answer("❗️ Введите корректное число!")
        # Удаляем сообщение об ошибке через 5 секунд
        import asyncio
        async def delete_after_delay():
            await asyncio.sleep(5)
            try:
                await error_msg.delete()
            except Exception:
                pass
        asyncio.create_task(delete_after_delay())


@inject
async def on_balance_min_amount_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Отмена выбора минимальной суммы - восстанавливаем значение из БД."""
    current = dialog_manager.dialog_data.get("current_balance")
    if current:
        # Загружаем текущее значение из БД
        settings = await settings_service.get()
        current["balance_min_amount"] = settings.features.balance_min_amount
        dialog_manager.dialog_data["current_balance"] = current
    
    await dialog_manager.switch_to(DashboardSettings.BALANCE)


@inject
async def on_balance_min_amount_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принять выбранную минимальную сумму."""
    await dialog_manager.switch_to(DashboardSettings.BALANCE)


@inject
async def on_balance_max_amount_preset_select(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор предустановленной максимальной суммы."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    widget_id = widget.widget_id
    
    current = dialog_manager.dialog_data.get("current_balance", {})
    
    if widget_id == "amount_no_limit":
        current["balance_max_amount"] = None
        logger.info(f"{log(user)} Set balance max amount to no limit")
    else:
        # Извлекаем сумму из widget_id (например, "amount_1000" -> 1000)
        amount = int(widget_id.split("_")[1])
        current["balance_max_amount"] = amount
        logger.info(f"{log(user)} Set balance max amount to {amount}")
    
    dialog_manager.dialog_data["current_balance"] = current


@inject
async def on_balance_max_amount_manual_input_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переключение в режим ручного ввода максимальной суммы."""
    await dialog_manager.switch_to(DashboardSettings.BALANCE_MAX_AMOUNT_MANUAL)


@inject
async def on_balance_max_amount_manual_value_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    """Обработка ручного ввода максимальной суммы."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_balance", {})
    
    try:
        value = float(message.text.strip().replace(",", "."))
        if value < 0:
            error_msg = await message.answer("❗️ Введите положительное число!")
            # Удаляем сообщение об ошибке через 5 секунд
            import asyncio
            async def delete_after_delay():
                await asyncio.sleep(5)
                try:
                    await error_msg.delete()
                except Exception:
                    pass
            asyncio.create_task(delete_after_delay())
            return
        
        # Проверяем что максимум не меньше минимума
        min_amount = current.get("balance_min_amount")
        if min_amount is not None and value < min_amount:
            error_msg = await message.answer(f"❗️ Максимум не может быть меньше минимума ({int(min_amount)} ₽)!")
            # Удаляем сообщение об ошибке через 5 секунд
            import asyncio
            async def delete_after_delay():
                await asyncio.sleep(5)
                try:
                    await error_msg.delete()
                except Exception:
                    pass
            asyncio.create_task(delete_after_delay())
            return
        
        current["balance_max_amount"] = value
        dialog_manager.dialog_data["current_balance"] = current
        
        logger.info(f"{log(user)} Set balance max amount via manual input: {value}")
        try:
            await message.delete()
        except Exception:
            pass
        await dialog_manager.switch_to(DashboardSettings.BALANCE_MAX_AMOUNT)
        
    except ValueError:
        error_msg = await message.answer("❗️ Введите корректное число!")
        # Удаляем сообщение об ошибке через 5 секунд
        import asyncio
        async def delete_after_delay():
            await asyncio.sleep(5)
            try:
                await error_msg.delete()
            except Exception:
                pass
        asyncio.create_task(delete_after_delay())


@inject
async def on_balance_max_amount_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Отмена выбора максимальной суммы - восстанавливаем значение из БД."""
    current = dialog_manager.dialog_data.get("current_balance")
    if current:
        # Загружаем текущее значение из БД
        settings = await settings_service.get()
        current["balance_max_amount"] = settings.features.balance_max_amount
        dialog_manager.dialog_data["current_balance"] = current
    
    await dialog_manager.switch_to(DashboardSettings.BALANCE)


@inject
async def on_balance_max_amount_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принять выбранную максимальную сумму."""
    await dialog_manager.switch_to(DashboardSettings.BALANCE)


@inject
async def on_cancel_balance(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена - сбросить временные изменения."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Восстанавливаем начальные значения в current
    initial = dialog_manager.dialog_data.get("initial_balance", {})
    dialog_manager.dialog_data["current_balance"] = initial.copy()
    
    logger.info(f"{log(user)} Cancelled balance settings changes")
    
    # Очищаем данные
    dialog_manager.dialog_data.pop("initial_balance", None)
    dialog_manager.dialog_data.pop("current_balance", None)
    
    # Возвращаемся в главное меню настроек
    await dialog_manager.switch_to(DashboardSettings.MAIN)


@inject
async def on_accept_balance(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Принять изменения - сохранить в базу."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_balance", {})
    
    if current:
        # Применяем все изменения
        await settings_service.update_balance_settings(
            balance_min_amount=current.get("balance_min_amount"),
            balance_max_amount=current.get("balance_max_amount"),
        )
        
        logger.info(
            f"{log(user)} Accepted and saved balance settings: "
            f"min={current.get('balance_min_amount')}, max={current.get('balance_max_amount')}"
        )
    
    # Очищаем данные
    dialog_manager.dialog_data.pop("initial_balance", None)
    dialog_manager.dialog_data.pop("current_balance", None)
    
    # Возвращаемся в главное меню настроек
    await dialog_manager.switch_to(DashboardSettings.MAIN)

@inject
async def on_tos_url_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход к вводу URL соглашения."""
    await dialog_manager.switch_to(DashboardSettings.TOS_URL_MANUAL)


@inject
async def on_tos_url_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    """Обработка ввода URL соглашения."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_tos", {})
    
    url = message.text.strip()
    
    # Базовая валидация URL
    if not url.startswith(("http://", "https://")):
        warning_msg = await message.answer("⚠️ URL должен начинаться с http:// или https://")
        # Удаляем сообщение через 5 секунд
        async def delete_warning():
            try:
                await asyncio.sleep(5)
                await warning_msg.delete()
            except Exception as e:
                logger.debug(f"Failed to delete warning message: {e}")
        asyncio.create_task(delete_warning())
        return
    
    current["url"] = url
    dialog_manager.dialog_data["current_tos"] = current
    
    logger.info(f"{log(user)} Set ToS URL to '{url}' (not saved yet)")
    try:
        await message.delete()
    except Exception:
        pass
    await dialog_manager.switch_to(DashboardSettings.TOS)


@inject
async def on_toggle_tos_enabled(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Toggle включения/выключения кнопки соглашения."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_tos", {})
    current["enabled"] = not current.get("enabled", True)
    dialog_manager.dialog_data["current_tos"] = current
    logger.info(f"{log(user)} Toggle ToS enabled (not saved yet)")


@inject
async def on_accept_tos(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Сохранение настроек соглашения."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_tos", {})
    
    # Обновляем URL соглашения
    if "url" in current:
        settings = await settings_service.get()
        from pydantic import SecretStr
        settings.rules_link = SecretStr(current.get("url", ""))
        await settings_service.update(settings)
        
        logger.info(f"{log(user)} Updated ToS URL to '{current.get('url')}'")
    
    # Очищаем временные данные
    dialog_manager.dialog_data.pop("initial_tos", None)
    dialog_manager.dialog_data.pop("current_tos", None)
    
    logger.info(f"{log(user)} Accepted ToS settings")
    await dialog_manager.switch_to(DashboardSettings.MAIN)


@inject
async def on_cancel_tos(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена изменений настроек соглашения."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Восстанавливаем начальные значения
    initial = dialog_manager.dialog_data.get("initial_tos", {})
    dialog_manager.dialog_data["current_tos"] = initial.copy()
    
    logger.info(f"{log(user)} Cancelled ToS settings")
    await dialog_manager.switch_to(DashboardSettings.MAIN)


# ═══════════════════════════════════════════════════════════════
# Курсы валют
# ═══════════════════════════════════════════════════════════════

@inject
async def on_currency_rates_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Переход в настройки курсов валют."""
    settings = await settings_service.get()
    rates = settings.features.currency_rates
    
    dialog_manager.dialog_data["initial_rates"] = {
        "usd_rate": rates.usd_rate,
        "eur_rate": rates.eur_rate,
        "stars_rate": rates.stars_rate,
    }
    
    dialog_manager.dialog_data["current_rates"] = {
        "usd_rate": rates.usd_rate,
        "eur_rate": rates.eur_rate,
        "stars_rate": rates.stars_rate,
    }
    
    await dialog_manager.switch_to(DashboardSettings.CURRENCY_RATES)


@inject
async def on_usd_rate_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Переход к редактированию курса USD."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    settings = await settings_service.get()
    
    if settings.features.currency_rates.auto_update:
        logger.warning(f"{log(user)} Attempted to edit USD rate while sync is enabled")
        await callback.answer("❌ Отключите синхронизацию курса для редактирования", show_alert=True)
        return
    
    await dialog_manager.switch_to(DashboardSettings.CURRENCY_RATE_USD)


@inject
async def on_eur_rate_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Переход к редактированию курса EUR."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    settings = await settings_service.get()
    
    if settings.features.currency_rates.auto_update:
        logger.warning(f"{log(user)} Attempted to edit EUR rate while sync is enabled")
        await callback.answer("❌ Отключите синхронизацию курса для редактирования", show_alert=True)
        return
    
    await dialog_manager.switch_to(DashboardSettings.CURRENCY_RATE_EUR)


@inject
async def on_stars_rate_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Переход к редактированию курса Stars."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    settings = await settings_service.get()
    
    if settings.features.currency_rates.auto_update:
        logger.warning(f"{log(user)} Attempted to edit Stars rate while sync is enabled")
        await callback.answer("❌ Отключите синхронизацию курса для редактирования", show_alert=True)
        return
    
    await dialog_manager.switch_to(DashboardSettings.CURRENCY_RATE_STARS)


@inject
async def on_currency_rate_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    rate_type: str,
) -> None:
    """Обработка ввода курса валюты."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    try:
        rate = float(message.text.strip().replace(",", "."))
        if rate <= 0:
            raise ValueError("Rate must be positive")
    except ValueError:
        logger.warning(f"{log(user)} Invalid rate value: {message.text}")
        await message.answer("⚠️ Введите положительное число")
        return
    
    current = dialog_manager.dialog_data.get("current_rates", {})
    current[rate_type] = rate
    dialog_manager.dialog_data["current_rates"] = current
    
    logger.info(f"{log(user)} Set {rate_type} to {rate}")
    await dialog_manager.switch_to(DashboardSettings.CURRENCY_RATES)


async def on_usd_rate_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    await on_currency_rate_input(message, widget, dialog_manager, "usd_rate")


async def on_eur_rate_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    await on_currency_rate_input(message, widget, dialog_manager, "eur_rate")


async def on_stars_rate_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
) -> None:
    await on_currency_rate_input(message, widget, dialog_manager, "stars_rate")


@inject
async def on_accept_rates(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Сохранение курсов валют."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_rates", {})
    
    settings = await settings_service.get()
    settings.features.currency_rates.auto_update = current.get("auto_update", False)
    settings.features.currency_rates.usd_rate = current.get("usd_rate", 90.0)
    settings.features.currency_rates.eur_rate = current.get("eur_rate", 100.0)
    settings.features.currency_rates.stars_rate = current.get("stars_rate", 1.5)
    await settings_service.update(settings)
    
    dialog_manager.dialog_data.pop("initial_rates", None)
    dialog_manager.dialog_data.pop("current_rates", None)
    
    logger.info(f"{log(user)} Saved currency rates")
    await dialog_manager.switch_to(DashboardSettings.FINANCES)


@inject
async def on_cancel_rates(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена изменений курсов валют."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    dialog_manager.dialog_data.pop("initial_rates", None)
    dialog_manager.dialog_data.pop("current_rates", None)
    
    logger.info(f"{log(user)} Cancelled currency rates")
    await dialog_manager.switch_to(DashboardSettings.FINANCES)


@inject
async def on_toggle_currency_auto_update(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Toggle автообновления курсов валют внутри настроек курсов."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    current = dialog_manager.dialog_data.get("current_rates", {})
    current["auto_update"] = not current.get("auto_update", False)
    dialog_manager.dialog_data["current_rates"] = current
    
    # Если включили автообновление - подтягиваем курсы из ЦБ РФ
    if current["auto_update"]:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        usd_rate = data["Valute"]["USD"]["Value"]
                        eur_rate = data["Valute"]["EUR"]["Value"]
                        current["usd_rate"] = round(usd_rate, 2)
                        current["eur_rate"] = round(eur_rate, 2)
                        dialog_manager.dialog_data["current_rates"] = current
                        logger.info(f"{log(user)} Fetched CBR rates: USD={usd_rate}, EUR={eur_rate}")
        except Exception as e:
            logger.warning(f"{log(user)} Failed to fetch CBR rates: {e}")
    
    logger.info(f"{log(user)} Toggle currency auto_update (not saved yet)")


async def on_finances_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Обработчик нажатия на кнопку 'Финансы'."""
    from src.bot.states import DashboardSettings
    await dialog_manager.switch_to(state=DashboardSettings.FINANCES)


async def on_finances_currency_rates_click(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Обработчик нажатия на кнопку 'Курс валют' в меню Финансы."""
    from src.bot.states import DashboardSettings
    await dialog_manager.switch_to(state=DashboardSettings.CURRENCY_RATES)


async def on_finances_back(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Обработчик нажатия на кнопку 'Назад' в меню Финансы."""
    from src.bot.states import DashboardSettings
    await dialog_manager.switch_to(state=DashboardSettings.MAIN)


@inject
async def on_toggle_finances_sync(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Toggle синхронизации курсов валют с ЦБ РФ (внутри меню Финансы)."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    settings = await settings_service.get()
    
    # Сохраняем исходное состояние при первом изменении
    if "pending_finances" not in dialog_manager.dialog_data:
        dialog_manager.dialog_data["pending_finances"] = {
            "sync_enabled": settings.features.currency_rates.auto_update
        }
    
    new_value = not settings.features.currency_rates.auto_update
    settings.features.currency_rates.auto_update = new_value
    
    # Если включили синхронизацию - подтягиваем курсы из ЦБ РФ
    if new_value:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        usd_rate = data["Valute"]["USD"]["Value"]
                        eur_rate = data["Valute"]["EUR"]["Value"]
                        settings.features.currency_rates.usd_rate = round(usd_rate, 2)
                        settings.features.currency_rates.eur_rate = round(eur_rate, 2)
                        logger.info(f"{log(user)} Fetched CBR rates: USD={usd_rate}, EUR={eur_rate}")
        except Exception as e:
            logger.warning(f"{log(user)} Failed to fetch CBR rates: {e}")
    
    await settings_service.update(settings)
    logger.info(f"{log(user)} Toggle finances sync to {new_value} (pending)")


@inject
async def on_toggle_currency_rates_auto(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Toggle автообновления курсов валют из главного меню настроек."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    settings = await settings_service.get()
    
    new_value = not settings.features.currency_rates.auto_update
    settings.features.currency_rates.auto_update = new_value
    
    # Если включили автообновление - подтягиваем курсы из ЦБ РФ
    if new_value:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json(content_type=None)
                        usd_rate = data["Valute"]["USD"]["Value"]
                        eur_rate = data["Valute"]["EUR"]["Value"]
                        settings.features.currency_rates.usd_rate = round(usd_rate, 2)
                        settings.features.currency_rates.eur_rate = round(eur_rate, 2)
                        logger.info(f"{log(user)} Fetched CBR rates: USD={usd_rate}, EUR={eur_rate}")
        except Exception as e:
            logger.warning(f"{log(user)} Failed to fetch CBR rates: {e}")
    
    await settings_service.update(settings)
    logger.info(f"{log(user)} Toggle finances sync from main menu to {new_value}")


@inject
@inject
async def on_finances_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Отменить изменения в меню Финансы"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Восстанавливаем исходные значения если они были изменены
    if "pending_finances" in dialog_manager.dialog_data:
        original_state = dialog_manager.dialog_data["pending_finances"]
        settings = await settings_service.get()
        
        # Восстанавливаем sync если он был изменен
        if "sync_enabled" in original_state:
            settings.features.currency_rates.auto_update = original_state["sync_enabled"]
            await settings_service.update(settings)
        
        dialog_manager.dialog_data.pop("pending_finances", None)
        logger.info(f"{log(user)} Cancelled finances changes")
    
    # Навигируем обратно в главное меню настроек
    await dialog_manager.switch_to(DashboardSettings.MAIN)


@inject
async def on_balance_mode_combined(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Установить режим баланса 'Сумма' (объединенное отображение балансов).
    
    В этом режиме основной и бонусный балансы показываются суммарно,
    но физически остаются раздельными в БД для возможности переключения обратно.
    """
    from src.core.enums import BalanceMode
    
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    settings = await settings_service.get()
    
    settings.features.balance_mode = BalanceMode.COMBINED
    settings.features = settings.features  # Trigger change tracking
    await settings_service.update(settings)
    
    logger.info(f"{log(user)} Set balance mode to COMBINED (display only, data preserved)")


@inject
async def on_balance_mode_separate(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Установить режим баланса 'Раздельно' (отдельный бонусный баланс)."""
    from src.core.enums import BalanceMode
    
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    settings = await settings_service.get()
    settings.features.balance_mode = BalanceMode.SEPARATE
    settings.features = settings.features  # Trigger change tracking
    await settings_service.update(settings)
    
    logger.info(f"{log(user)} Set balance mode to SEPARATE")


@inject
@inject
async def on_finances_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принять изменения в меню Финансы"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Изменения уже сохранены, просто очищаем pending_finances
    if "pending_finances" in dialog_manager.dialog_data:
        dialog_manager.dialog_data.pop("pending_finances", None)
        logger.info(f"{log(user)} Accepted finances changes")
    
    # Навигируем обратно в главное меню настроек
    await dialog_manager.switch_to(DashboardSettings.MAIN)
