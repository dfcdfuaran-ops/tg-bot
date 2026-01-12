from typing import Any

from aiogram_dialog import DialogManager
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject

from src.core.config import AppConfig
from src.services.settings import SettingsService


@inject
async def settings_main_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для главного меню настроек."""
    from src.core.enums import AccessMode
    
    settings = await settings_service.get()
    features = settings.features
    
    return {
        "extra_devices_enabled": 1 if features.extra_devices.enabled else 0,
        "balance_enabled": 1 if features.balance_enabled else 0,
        "transfers_enabled": 1 if features.transfers.enabled else 0,
        "notifications_enabled": 1 if features.notifications_enabled else 0,
        "access_enabled": 1 if settings.access_mode == AccessMode.PUBLIC else 0,
        "referral_enabled": 1 if settings.referral.enable else 0,
        "community_enabled": 1 if features.community_enabled else 0,
        "tos_enabled": 1 if features.tos_enabled else 0,
        "global_discount_enabled": 1 if features.global_discount.enabled else 0,
        "finances_sync_enabled": 1 if features.currency_rates.auto_update else 0,
    }


@inject
async def balance_settings_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для настроек баланса."""
    from src.core.enums import BalanceMode
    
    # Загружаем текущие значения из БД
    settings = await settings_service.get()
    features = settings.features
    db_balance_min_amount = features.balance_min_amount
    db_balance_max_amount = features.balance_max_amount
    balance_mode = features.balance_mode
    
    # Используем данные из dialog_data, если они есть, иначе используем значения из БД
    current = dialog_manager.dialog_data.get("current_balance")
    
    if not current:
        # Первое открытие - загружаем из БД
        current = {
            "enabled": features.balance_enabled,
            "balance_min_amount": db_balance_min_amount,
            "balance_max_amount": db_balance_max_amount,
        }
    
    balance_min_amount = current.get("balance_min_amount")
    balance_max_amount = current.get("balance_max_amount")
    
    # Формируем результат
    result = {
        "enabled": 1 if current.get("enabled", True) else 0,
        "balance_min_amount": f"{int(balance_min_amount)} ₽" if balance_min_amount is not None else "Без ограничений",
        "balance_max_amount": f"{int(balance_max_amount)} ₽" if balance_max_amount is not None else "Без ограничений",
        "balance_mode_combined": 1 if balance_mode == BalanceMode.COMBINED else 0,
        "balance_mode_separate": 1 if balance_mode == BalanceMode.SEPARATE else 0,
    }
    
    # Добавляем данные для минимальной суммы
    # balance_min_current_display - текущее значение из БД (то что реально установлено)
    if db_balance_min_amount is None:
        result["balance_min_current_display"] = "Без ограничений"
    else:
        result["balance_min_current_display"] = f"{int(db_balance_min_amount)} ₽"
    
    # balance_min_selected_display - выбранное значение (то что будет установлено при нажатии "Принять")
    if balance_min_amount is None:
        result["balance_min_selected_display"] = "Без ограничений"
        result["amount_no_limit_balance_min_selected"] = 1
    else:
        result["balance_min_selected_display"] = f"{int(balance_min_amount)} ₽"
        result["amount_no_limit_balance_min_selected"] = 0
    
    # Добавляем selected для кнопок минимальной суммы
    for amount in [10, 50, 100, 500, 1000, 5000]:
        result[f"amount_{amount}_balance_min_selected"] = 1 if balance_min_amount == amount else 0
    
    # Добавляем данные для максимальной суммы
    # balance_max_current_display - текущее значение из БД (то что реально установлено)
    if db_balance_max_amount is None:
        result["balance_max_current_display"] = "Без ограничений"
    else:
        result["balance_max_current_display"] = f"{int(db_balance_max_amount)} ₽"
    
    # balance_max_selected_display - выбранное значение (то что будет установлено при нажатии "Принять")
    if balance_max_amount is None:
        result["balance_max_selected_display"] = "Без ограничений"
        result["amount_no_limit_balance_max_selected"] = 1
    else:
        result["balance_max_selected_display"] = f"{int(balance_max_amount)} ₽"
        result["amount_no_limit_balance_max_selected"] = 0
    
    # Добавляем selected для кнопок максимальной суммы
    for amount in [1000, 5000, 10000, 50000, 100000, 500000]:
        result[f"amount_{amount}_balance_max_selected"] = 1 if balance_max_amount == amount else 0
    
    return result


@inject
async def transfers_settings_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для настроек переводов."""
    # Загружаем текущие значения из БД
    settings = await settings_service.get()
    transfer_settings = settings.features.transfers
    db_commission_type = transfer_settings.commission_type
    db_commission_value = transfer_settings.commission_value
    
    # Используем данные из dialog_data, если они есть, иначе используем значения из БД
    current = dialog_manager.dialog_data.get("current_transfers")
    
    if not current:
        # Первое открытие - загружаем из БД
        current = {
            "enabled": transfer_settings.enabled,
            "commission_type": db_commission_type,
            "commission_value": db_commission_value,
            "min_amount": transfer_settings.min_amount,
            "max_amount": transfer_settings.max_amount,
        }
    
    # Формируем отображение типа комиссии
    commission_type = current.get("commission_type", "percent")
    commission_value = current.get("commission_value", 5)
    
    # commission_type_display - отображение выбранного типа комиссии из current
    if commission_type == "percent":
        commission_type_display = "Процентная"
    else:
        commission_type_display = "Фиксированная"
    
    # commission_display - отображение выбранной комиссии из current (для меню "Переводы")
    if commission_type == "percent":
        if int(commission_value) == 0:
            commission_display = "Бесплатно"
        else:
            commission_display = f"{int(commission_value)}%"
    else:
        if int(commission_value) == 0:
            commission_display = "Бесплатно"
        else:
            commission_display = f"{int(commission_value)} ₽"
    
    # db_commission_display - текущая активная комиссия из БД (для подменю "Комиссия")
    if db_commission_type == "percent":
        if int(db_commission_value) == 0:
            db_commission_display = "Бесплатно"
        else:
            db_commission_display = f"{int(db_commission_value)}%"
    else:
        if int(db_commission_value) == 0:
            db_commission_display = "Бесплатно"
        else:
            db_commission_display = f"{int(db_commission_value)} ₽"
    
    # selected_display - выбранная комиссия (которая будет применена в подменю)
    # В подменю это показывает что выбрано, в главном меню не используется
    selected_display = commission_display
    
    # Создаем selected значения для всех кнопок
    result = {
        "enabled": 1 if current.get("enabled", True) else 0,
        "commission_type": commission_type,  # Используем выбранный тип
        "commission_type_display": commission_type_display,
        "is_percent": 1 if commission_type == "percent" else 0,
        "is_fixed": 0 if commission_type == "percent" else 1,
        "commission_value": int(commission_value),  # Используем выбранное значение
        "commission_display": commission_display,  # Выбранное значение для меню "Переводы"
        "db_commission_display": db_commission_display,  # Текущее значение из БД для подменю "Комиссия"
        "selected_display": selected_display,
        "min_amount": current.get("min_amount", 10),
        "max_amount": current.get("max_amount", 100000),
    }
    
    # Добавляем selected для кнопки "Бесплатно"
    result["commission_free_selected"] = 1 if int(commission_value) == 0 else 0
    
    # Добавляем selected для процентных кнопок (5-20%, 25-100% с шагом 5)
    for i in range(5, 21):
        result[f"commission_{i}_selected"] = 1 if commission_type == "percent" and int(commission_value) == i else 0
    for i in range(25, 101, 5):
        if i == 50:
            # Для 50% используем commission_50_percent_selected, чтобы не путать с 50₽
            result[f"commission_50_percent_selected"] = 1 if commission_type == "percent" and int(commission_value) == 50 else 0
        else:
            result[f"commission_{i}_selected"] = 1 if commission_type == "percent" and int(commission_value) == i else 0
    
    # Добавляем selected для фиксированных кнопок (50-1000₽ с шагом 50)
    for i in range(50, 1001, 50):
        result[f"commission_{i}_selected"] = 1 if commission_type == "fixed" and int(commission_value) == i else 0
    
    # Добавляем данные для минимальной суммы
    db_min_amount = transfer_settings.min_amount  # Текущее значение из БД
    min_amount = current.get("min_amount")  # Выбранное значение
    
    # db_min_current_display - текущее значение из БД
    if db_min_amount is None:
        result["db_min_current_display"] = "Без ограничений"
    else:
        result["db_min_current_display"] = f"{int(db_min_amount)} ₽"
    
    # min_selected_display - выбранное значение
    if min_amount is None:
        result["min_current_display"] = "Без ограничений"
        result["min_selected_display"] = "Без ограничений"
        result["amount_no_limit_min_selected"] = 1
    else:
        result["min_current_display"] = f"{int(min_amount)} ₽"
        result["min_selected_display"] = f"{int(min_amount)} ₽"
        result["amount_no_limit_min_selected"] = 0
    
    # Добавляем selected для кнопок минимальной суммы
    for amount in [10, 50, 100, 500, 1000, 5000]:
        result[f"amount_{amount}_min_selected"] = 1 if min_amount == amount else 0
    
    # Добавляем данные для максимальной суммы
    db_max_amount = transfer_settings.max_amount  # Текущее значение из БД
    max_amount = current.get("max_amount")  # Выбранное значение
    
    # db_max_current_display - текущее значение из БД
    if db_max_amount is None:
        result["db_max_current_display"] = "Без ограничений"
    else:
        result["db_max_current_display"] = f"{int(db_max_amount)} ₽"
    
    # max_selected_display - выбранное значение
    if max_amount is None:
        result["max_current_display"] = "Без ограничений"
        result["max_selected_display"] = "Без ограничений"
        result["amount_no_limit_max_selected"] = 1
    else:
        result["max_current_display"] = f"{int(max_amount)} ₽"
        result["max_selected_display"] = f"{int(max_amount)} ₽"
        result["amount_no_limit_max_selected"] = 0
    
    # Добавляем selected для кнопок максимальной суммы
    for amount in [1000, 5000, 10000, 50000, 100000, 500000]:
        result[f"amount_{amount}_max_selected"] = 1 if max_amount == amount else 0
    
    return result


@inject
async def extra_devices_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для настроек доп. устройств."""
    settings = await settings_service.get()
    features = settings.features
    
    # Получаем pending значения из dialog_data или используем текущие
    pending_payment_type = dialog_manager.dialog_data.get("pending_extra_devices_payment_type")
    is_one_time = pending_payment_type if pending_payment_type is not None else features.extra_devices.is_one_time
    
    # Получаем pending цену или текущую из БД
    pending_price = dialog_manager.dialog_data.get("pending_extra_devices_price")
    extra_devices_price = pending_price if pending_price is not None else features.extra_devices.price_per_device
    
    payment_type_display = "Разовая платёж" if is_one_time else "Ежемесячно"
    
    return {
        "enabled": 1 if features.extra_devices.enabled else 0,
        "extra_devices_price": extra_devices_price,
        "is_one_time": 1 if is_one_time else 0,
        "is_monthly": 0 if is_one_time else 1,
        "payment_type_display": payment_type_display,
    }


@inject
async def extra_devices_price_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна изменения цены доп. устройств."""
    settings = await settings_service.get()
    features = settings.features
    
    # Получаем pending price или текущую
    pending_price = dialog_manager.dialog_data.get("pending_extra_devices_price")
    current_price = features.extra_devices.price_per_device
    selected_price = pending_price if pending_price is not None else current_price
    
    return {
        "current_price": current_price,
        "selected_price": selected_price,
    }


@inject
async def global_discount_settings_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для настроек глобальной скидки."""
    # Загружаем текущие значения из БД
    settings = await settings_service.get()
    discount_settings = settings.features.global_discount
    db_discount_type = discount_settings.discount_type
    db_discount_value = discount_settings.discount_value
    
    # Используем данные из dialog_data, если они есть, иначе используем значения из БД
    current = dialog_manager.dialog_data.get("current_global_discount")
    
    if not current:
        # Первое открытие - загружаем из БД
        current = {
            "enabled": discount_settings.enabled,
            "discount_type": db_discount_type,
            "discount_value": db_discount_value,
            "stack_discounts": discount_settings.stack_discounts,
            "apply_to_subscription": discount_settings.apply_to_subscription,
            "apply_to_extra_devices": discount_settings.apply_to_extra_devices,
            "apply_to_transfer_commission": discount_settings.apply_to_transfer_commission,
        }
    
    # Формируем отображение типа скидки
    discount_type = current.get("discount_type", "percent")
    discount_value = current.get("discount_value", 0)
    stack_discounts = current.get("stack_discounts", False)
    apply_to_subscription = current.get("apply_to_subscription", True)
    apply_to_extra_devices = current.get("apply_to_extra_devices", False)
    apply_to_transfer_commission = current.get("apply_to_transfer_commission", False)
    
    # discount_type_display - отображение выбранного типа скидки из current
    if discount_type == "percent":
        discount_type_display = "Процентная"
    else:
        discount_type_display = "Фиксированная"
    
    # discount_display - отображение выбранной скидки из current (для меню "Глобальная скидка")
    if discount_type == "percent":
        if int(discount_value) == 0:
            discount_display = "Нет скидки"
        else:
            discount_display = f"{int(discount_value)}%"
    else:
        if int(discount_value) == 0:
            discount_display = "Нет скидки"
        else:
            discount_display = f"{int(discount_value)} ₽"
    
    # db_discount_display - текущая активная скидка из БД (для подменю "Скидка")
    if db_discount_type == "percent":
        if int(db_discount_value) == 0:
            db_discount_display = "Нет скидки"
        else:
            db_discount_display = f"{int(db_discount_value)}%"
    else:
        if int(db_discount_value) == 0:
            db_discount_display = "Нет скидки"
        else:
            db_discount_display = f"{int(db_discount_value)} ₽"
    
    # selected_display - выбранная скидка (которая будет применена в подменю)
    selected_display = discount_display
    
    # Отображение режима складывания скидок
    stack_mode_display = "Сложенная" if stack_discounts else "Максимальная"
    
    # Собираем список на что применяется скидка
    apply_to_list = []
    if apply_to_subscription:
        apply_to_list.append("Подписка")
    if apply_to_extra_devices:
        apply_to_list.append("Доп.устройства")
    if apply_to_transfer_commission:
        apply_to_list.append("Комиссия")
    apply_to_display = ", ".join(apply_to_list) if apply_to_list else "Ничего"
    
    # Создаем selected значения для всех кнопок
    result = {
        "enabled": 1 if current.get("enabled", False) else 0,
        "discount_type": discount_type,  # Используем выбранный тип
        "discount_type_display": discount_type_display,
        "is_percent": 1 if discount_type == "percent" else 0,
        "is_fixed": 0 if discount_type == "percent" else 1,
        "discount_value": int(discount_value),  # Используем выбранное значение
        "discount_display": discount_display,  # Выбранное значение для меню "Глобальная скидка"
        "db_discount_display": db_discount_display,  # Текущее значение из БД для подменю "Скидка"
        "selected_display": selected_display,
        # Новые поля
        "stack_discounts": 1 if stack_discounts else 0,
        "stack_mode_display": stack_mode_display,
        "apply_to_subscription": 1 if apply_to_subscription else 0,
        "apply_to_extra_devices": 1 if apply_to_extra_devices else 0,
        "apply_to_transfer_commission": 1 if apply_to_transfer_commission else 0,
        "apply_to_display": apply_to_display,
    }
    
    # Добавляем selected для кнопки "Нет скидки"
    result["discount_free_selected"] = 1 if int(discount_value) == 0 else 0
    
    # Добавляем selected для процентных кнопок (5-20%, 25-100% с шагом 5)
    for i in range(5, 21):
        result[f"discount_{i}_selected"] = 1 if discount_type == "percent" and int(discount_value) == i else 0
    for i in range(25, 101, 5):
        if i == 50:
            # Для 50% используем discount_50_percent_selected, чтобы не путать с 50₽
            result[f"discount_50_percent_selected"] = 1 if discount_type == "percent" and int(discount_value) == 50 else 0
        else:
            result[f"discount_{i}_selected"] = 1 if discount_type == "percent" and int(discount_value) == i else 0
    
    # Добавляем selected для фиксированных кнопок (50-1000₽ с шагом 50)
    for i in range(50, 1001, 50):
        result[f"discount_{i}_selected"] = 1 if discount_type == "fixed" and int(discount_value) == i else 0
    
    return result


@inject
async def global_discount_apply_to_getter(
    dialog_manager: DialogManager,
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для меню 'На что влияет скидка'."""
    current = dialog_manager.dialog_data.get("current_global_discount", {})
    
    apply_to_subscription = current.get("apply_to_subscription", True)
    apply_to_extra_devices = current.get("apply_to_extra_devices", False)
    apply_to_transfer_commission = current.get("apply_to_transfer_commission", False)
    
    return {
        "apply_to_subscription": 1 if apply_to_subscription else 0,
        "apply_to_extra_devices": 1 if apply_to_extra_devices else 0,
        "apply_to_transfer_commission": 1 if apply_to_transfer_commission else 0,
    }


@inject
async def global_discount_mode_getter(
    dialog_manager: DialogManager,
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для меню 'Режим применения скидок'."""
    current = dialog_manager.dialog_data.get("current_global_discount", {})
    stack_discounts = current.get("stack_discounts", False)
    
    return {
        "stack_discounts": 1 if stack_discounts else 0,
        "mode_max_selected": 0 if stack_discounts else 1,
        "mode_stack_selected": 1 if stack_discounts else 0,
    }


@inject
async def tos_settings_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для настроек соглашения (Terms of Service)."""
    settings = await settings_service.get()
    tos_url = settings.rules_link.get_secret_value()
    
    # Используем данные из dialog_data, если они есть, иначе используем значения из БД
    current = dialog_manager.dialog_data.get("current_tos")
    
    if not current:
        # Первое открытие - загружаем из БД
        current = {
            "enabled": settings.features.tos_enabled,
            "url": tos_url,
        }
    
    url = current.get("url", "")
    enabled = current.get("enabled", True)
    
    # Форматируем URL для отображения (показываем первые 50 символов)
    if url:
        url_display = url[:50] + "..." if len(url) > 50 else url
    else:
        url_display = "Не установлено"
    
    # Статус для отображения в шапке
    status_text = "🟢 Включено" if enabled else "🔴 Выключено"
    
    return {
        "enabled": 1 if enabled else 0,
        "url": url,
        "url_display": url_display,
        "status_text": status_text,
    }


@inject
async def community_settings_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для настроек сообщества."""
    settings = await settings_service.get()
    community_url = settings.features.community_url or ""
    
    # Используем данные из dialog_data, если они есть
    current = dialog_manager.dialog_data.get("current_community")
    
    if not current:
        # Первое открытие - загружаем текущие значения из БД
        current = {
            "enabled": settings.features.community_enabled,
            "url": community_url,
        }
    
    url = current.get("url", "")
    enabled = current.get("enabled", True)
    
    # Форматируем URL для отображения
    if url:
        url_display = url[:50] + "..." if len(url) > 50 else url
    else:
        url_display = "Не установлено"
    
    # Статус для отображения с эмодзи
    status = "Включено 🟢" if enabled else "Выключено 🔴"
    
    return {
        "enabled": 1 if enabled else 0,
        "url": url,
        "url_display": url_display,
        "status": status,
    }


@inject
async def finances_settings_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для меню Финансы."""
    settings = await settings_service.get()
    rates = settings.features.currency_rates
    default_currency = await settings_service.get_default_currency()
    
    sync_enabled = rates.auto_update
    
    return {
        "sync_enabled": 1 if sync_enabled else 0,
        "sync_status": "🟢 Включена" if sync_enabled else "🔴 Выключена",
        "default_currency": default_currency.symbol,
        "default_currency_name": default_currency.value,
    }


@inject
async def currency_rates_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для настроек курсов валют."""
    settings = await settings_service.get()
    rates = settings.features.currency_rates
    
    current = dialog_manager.dialog_data.get("current_rates")
    
    if not current:
        current = {
            "auto_update": rates.auto_update,
            "usd_rate": rates.usd_rate,
            "eur_rate": rates.eur_rate,
            "stars_rate": rates.stars_rate,
        }
    
    usd_rate = current.get("usd_rate", 90.0)
    eur_rate = current.get("eur_rate", 100.0)
    stars_rate = current.get("stars_rate", 1.5)
    auto_update = current.get("auto_update", False)
    
    # Сохраняем в dialog_data для доступа из обработчиков
    dialog_manager.dialog_data["current_rates"] = current
    
    def format_rate(rate: float) -> str:
        """Форматирует курс, убирая ненужные нули."""
        formatted = f"{rate:.2f}".rstrip('0').rstrip('.')
        return formatted
    
    return {
        "auto_update": 1 if auto_update else 0,
        "sync_enabled": 1 if auto_update else 0,
        "usd_rate": usd_rate,
        "eur_rate": eur_rate,
        "stars_rate": stars_rate,
        # Форматированные строки для кнопок
        "usd_display": f"{format_rate(usd_rate)} ₽ = 1 $",
        "eur_display": f"{format_rate(eur_rate)} ₽ = 1 €",
        "stars_display": f"{format_rate(stars_rate)} ₽ = 1 ★",
    }
