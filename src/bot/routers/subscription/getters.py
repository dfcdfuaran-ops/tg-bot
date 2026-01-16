from decimal import Decimal
from math import ceil
from typing import Any, cast

from aiogram_dialog import DialogManager, ShowMode, StartMode
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from fluentogram import TranslatorRunner
from loguru import logger

from src.core.config import AppConfig
from src.core.enums import Currency, PaymentGatewayType, PurchaseType, ReferralRewardType
from src.core.utils.adapter import DialogDataAdapter
from src.core.utils.formatters import (
    format_price,
    i18n_format_days,
    i18n_format_device_limit,
    i18n_format_expire_time,
    i18n_format_traffic_limit,
)
from src.infrastructure.database.models.dto import PlanDto, PriceDetailsDto, UserDto
from src.services.extra_device import ExtraDeviceService
from src.services.payment_gateway import PaymentGatewayService
from src.services.plan import PlanService
from src.services.pricing import PricingService
from src.services.referral import ReferralService
from src.services.remnawave import RemnawaveService
from src.services.settings import SettingsService
from src.services.subscription import SubscriptionService
from src.services.user import UserService


def get_display_balance(user_balance: int, referral_balance: int, is_combined: bool) -> int:
    """
    Вычисляет отображаемый баланс в зависимости от режима.
    
    В режиме COMBINED возвращает сумму основного и бонусного баланса.
    В режиме SEPARATE возвращает только основной баланс.
    """
    return user_balance + referral_balance if is_combined else user_balance


@inject
async def referral_code_input_getter(
    dialog_manager: DialogManager,
    **kwargs: Any,
) -> dict[str, Any]:
    error_key = dialog_manager.dialog_data.get("referral_code_error", "none")
    return {
        "error_key": error_key,
    }


@inject
async def subscription_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    i18n: FromDishka[TranslatorRunner],
    referral_service: FromDishka[ReferralService],
    plan_service: FromDishka[PlanService],
    subscription_service: FromDishka[SubscriptionService],
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    from datetime import datetime, timezone
    has_active = bool(user.current_subscription and not user.current_subscription.is_trial)
    is_unlimited = user.current_subscription.is_unlimited if user.current_subscription else False
    purchase_type = dialog_manager.dialog_data.get("purchase_type")
    is_topup_mode = purchase_type == "TOPUP"
    
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )
    
    # Определяем, является ли пользователь приглашённым
    # Проверяем напрямую через сервис, так как user.is_invited_user может быть не установлен корректно
    referral = await referral_service.get_referral_by_referred(user.telegram_id)
    is_invited = bool(referral)
    
    # Проверяем доступность пробной подписки
    # Приглашённые пользователи получают INVITED план, остальные - TRIAL план
    plan = await plan_service.get_appropriate_trial_plan(user, is_invited=is_invited)
    has_used_trial = await subscription_service.has_used_trial(user.telegram_id)
    trial_available = not has_used_trial and plan and not has_active
    
    # Определяем, является ли пробная подписка реферальной
    is_referral_trial = trial_available and is_invited
    
    # Определяем, может ли пользователь улучшить пробную подписку до реферальной
    # Условия: есть активная пробная подписка (по флагу или имени) и нет реферальной связи
    # и подписка НЕ реферальная
    is_trial_by_name = bool(
        user.current_subscription 
        and user.current_subscription.is_active
        and "пробн" in user.current_subscription.plan.name.lower()
    )
    is_referral_by_name = bool(
        user.current_subscription 
        and user.current_subscription.is_active
        and "реферал" in user.current_subscription.plan.name.lower()
    )
    
    can_upgrade_to_referral = bool(
        user.current_subscription 
        and user.current_subscription.is_active 
        and not referral
        and (user.current_subscription.is_trial or is_trial_by_name)
        and not is_referral_by_name
    )
    
    # Определяем, является ли текущая подписка реферальной (приглашённой)
    # Проверяем по is_trial ИЛИ по имени плана (для подписок выданных через панель)
    is_referral_subscription = bool(
        user.current_subscription 
        and user.current_subscription.is_active
        and (
            (user.current_subscription.is_trial and is_invited)
            or is_referral_by_name
        )
    )
    
    # Определяем, является ли текущая подписка пробной (любой - Пробный или Реферальный)
    # Используем уже вычисленные переменные is_trial_by_name и is_referral_by_name
    # Для пробных подписок скрываем кнопки "Продлить" и "Изменить"
    is_trial_subscription = bool(
        user.current_subscription 
        and user.current_subscription.is_active
        and (
            user.current_subscription.is_trial
            or is_trial_by_name
            or is_referral_by_name
        )
    )
    
    logger.info(
        f"[subscription_getter] user={user.telegram_id}: "
        f"plan_name='{user.current_subscription.plan.name if user.current_subscription else None}', "
        f"is_trial_flag={user.current_subscription.is_trial if user.current_subscription else None}, "
        f"is_trial_by_name={is_trial_by_name}, "
        f"is_referral_by_name={is_referral_by_name}, "
        f"is_trial_subscription={is_trial_subscription}, "
        f"can_upgrade_to_referral={can_upgrade_to_referral}"
    )

    # Безопасное преобразование trial_available к int
    safe_trial_available = int(bool(trial_available)) if trial_available is not None else 0
    safe_is_referral_trial = int(bool(is_referral_trial)) if is_referral_trial is not None else 0
    safe_can_upgrade_to_referral = int(bool(can_upgrade_to_referral)) if can_upgrade_to_referral is not None else 0
    safe_is_referral_subscription = int(bool(is_referral_subscription)) if is_referral_subscription is not None else 0
    safe_is_trial_subscription = int(bool(is_trial_subscription)) if is_trial_subscription is not None else 0
    
    logger.debug(
        f"[subscription_getter] user={user.telegram_id}: "
        f"is_trial_subscription={is_trial_subscription}, "
        f"safe_is_trial_subscription={safe_is_trial_subscription}, "
        f"current_subscription={user.current_subscription}, "
        f"is_trial={user.current_subscription.is_trial if user.current_subscription else None}, "
        f"is_active={user.current_subscription.is_active if user.current_subscription else None}"
    )

    # Вычисляем скидку пользователя
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    # Проверяем срок действия одноразовой скидки
    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    # Определяем, какую скидку показывать
    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    # Проверяем, включен ли функционал баланса
    is_balance_enabled = await settings_service.is_balance_enabled()
    
    # Проверяем режим баланса (раздельный или объединённый)
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    # Вычисляем отображаемый баланс
    display_balance = get_display_balance(user.balance, referral_balance, is_balance_combined)
    
    result = {
        "has_active_subscription": has_active,
        "is_not_unlimited": not is_unlimited,
        "is_topup_mode": is_topup_mode,
        "trial_available": safe_trial_available,
        "is_referral_trial": safe_is_referral_trial,
        "can_upgrade_to_referral": safe_can_upgrade_to_referral,
        "is_referral_subscription": safe_is_referral_subscription,
        "is_trial_subscription": safe_is_trial_subscription,
        # Данные пользователя для шапки
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "balance": display_balance,
        "referral_balance": referral_balance,
        "referral_code": user.referral_code,
        "is_balance_enabled": 1 if is_balance_enabled else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,
        # Для кнопки "Мои устройства"
        "has_device_limit": bool(
            user.current_subscription 
            and user.current_subscription.has_devices_limit 
            and user.current_subscription.is_active
        ),
    }
    
    # Данные о текущей подписке (если есть)
    subscription = user.current_subscription
    if subscription:
        extra_devices = subscription.extra_devices or 0
        
        # Вычисляем бонус устройств (разница между реальным лимитом из Remnawave и планом, БЕЗ купленных доп.)
        plan_device_limit = subscription.plan.device_limit if subscription.plan.device_limit > 0 else 0
        actual_device_limit = subscription.device_limit
        device_limit_bonus = max(0, actual_device_limit - plan_device_limit - extra_devices) if plan_device_limit > 0 else 0
        
        result.update({
            "has_subscription": "true",
            "current_plan_name": subscription.plan.name,
            "plan_name": subscription.plan.name,
            "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
            "device_limit": i18n_format_device_limit(subscription.device_limit),
            "device_limit_number": subscription.plan.device_limit,
            "device_limit_bonus": device_limit_bonus,
            "extra_devices": extra_devices,
            "expire_time": i18n_format_expire_time(subscription.expire_at),
        })
    else:
        result.update({
            "has_subscription": "false",
            "current_plan_name": "",
            "plan_name": "",
            "traffic_limit": "",
            "device_limit": "",
            "device_limit_number": 0,
            "device_limit_bonus": 0,
            "extra_devices": 0,
            "expire_time": "",
        })
    
    return result


@inject
async def plans_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    plan_service: FromDishka[PlanService],
    referral_service: FromDishka[ReferralService],
    settings_service: FromDishka[SettingsService],
    i18n: FromDishka[TranslatorRunner],
    **kwargs: Any,
) -> dict[str, Any]:
    plans = await plan_service.get_available_plans(user)

    # Если пользователь меняет подписку (CHANGE), исключаем текущий активный план из списка
    purchase_type = dialog_manager.dialog_data.get("purchase_type")
    if purchase_type == PurchaseType.CHANGE and user.current_subscription:
        current_plan_id = user.current_subscription.plan.id
        plans = [plan for plan in plans if plan.id != current_plan_id]

    formatted_plans = [
        {
            "id": plan.id,
            "name": plan.name,
        }
        for plan in plans
    ]

    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )

    # Вычисляем скидку пользователя
    from datetime import datetime, timezone
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    # Проверяем, включен ли функционал баланса
    is_balance_enabled = await settings_service.is_balance_enabled()
    
    # Проверяем режим баланса (раздельный или объединённый)
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    # Вычисляем отображаемый баланс
    display_balance = get_display_balance(user.balance, referral_balance, is_balance_combined)
    
    result = {
        "plans": formatted_plans,
        # Данные пользователя для шапки
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "balance": display_balance,
        "referral_balance": referral_balance,
        "referral_code": user.referral_code,
        "is_balance_enabled": 1 if is_balance_enabled else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,
    }

    # Данные о текущей подписке (если есть)
    subscription = user.current_subscription
    if subscription:
        extra_devices = subscription.extra_devices or 0
        # Вычисляем бонус устройств (БЕЗ купленных доп.)
        plan_device_limit = subscription.plan.device_limit if subscription.plan.device_limit > 0 else 0
        actual_device_limit = subscription.device_limit
        device_limit_bonus = max(0, actual_device_limit - plan_device_limit - extra_devices) if plan_device_limit > 0 else 0
        
        result.update({
            "has_subscription": "true",
            "current_plan_name": subscription.plan.name,
            "plan_name": subscription.plan.name,
            "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
            "device_limit": i18n_format_device_limit(subscription.device_limit),
            "device_limit_number": subscription.plan.device_limit,
            "device_limit_bonus": device_limit_bonus,
            "extra_devices": extra_devices,
            "expire_time": i18n_format_expire_time(subscription.expire_at),
        })
    else:
        result.update({
            "has_subscription": "false",
            "current_plan_name": "",
            "plan_name": "",
            "traffic_limit": "",
            "device_limit": "",
            "device_limit_number": 0,
            "device_limit_bonus": 0,
            "extra_devices": 0,
            "expire_time": "",
        })

    return result


@inject
async def duration_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    i18n: FromDishka[TranslatorRunner],
    settings_service: FromDishka[SettingsService],
    pricing_service: FromDishka[PricingService],
    referral_service: FromDishka[ReferralService],
    extra_device_service: FromDishka[ExtraDeviceService],
    **kwargs: Any,
) -> dict[str, Any]:
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    currency = await settings_service.get_default_currency()
    only_single_plan = dialog_manager.dialog_data.get("only_single_plan", False)
    dialog_manager.dialog_data["is_free"] = False
    
    # Получаем настройки глобальной скидки
    global_discount = await settings_service.get_global_discount_settings()
    
    # Получаем курсы валют для конвертации
    settings = await settings_service.get()
    rates = settings.features.currency_rates
    usd_rate = rates.usd_rate
    eur_rate = rates.eur_rate
    stars_rate = rates.stars_rate
    
    # Получаем стоимость дополнительных устройств для всех типов покупок
    purchase_type = dialog_manager.dialog_data.get("purchase_type")
    extra_devices_monthly_cost = 0
    
    # Для NEW, RENEW и CHANGE проверяем наличие активных доп. устройств
    if user.current_subscription:
        # Получаем количество активных дополнительных устройств
        active_extra_devices = await extra_device_service.get_total_active_devices(
            user.current_subscription.id
        )
        
        # Получаем месячную цену за одно дополнительное устройство
        if active_extra_devices > 0:
            device_price_monthly = await settings_service.get_extra_device_price()
            extra_devices_monthly_cost = device_price_monthly * active_extra_devices
    
    durations = []

    for duration in plan.durations:
        key, kw = i18n_format_days(duration.days)
        base_price = duration.get_price(currency, usd_rate, eur_rate, stars_rate)
        
        # Добавляем стоимость доп. устройств пропорционально периоду
        if extra_devices_monthly_cost > 0:
            # Рассчитываем стоимость доп. устройств за период (целые месяцы)
            months = duration.days // 30  # Используем целочисленное деление
            extra_devices_cost = extra_devices_monthly_cost * months
            total_price = base_price + extra_devices_cost
        else:
            total_price = base_price
            extra_devices_cost = 0
        
        price = pricing_service.calculate(user, total_price, currency, global_discount, context="subscription")
        has_discount = 1 if price.discount_percent > 0 or price.final_amount < price.original_amount else 0
        durations.append(
            {
                "days": duration.days,
                "period": i18n.get(key, **kw),
                "final_amount": price.final_amount,
                "discount_percent": price.discount_percent,
                "original_amount": price.original_amount,
                "currency": currency.symbol,
                "extra_devices_cost": extra_devices_cost,
                "has_discount": has_discount,
            }
        )

    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )

    # Вычисляем скидку пользователя
    from datetime import datetime, timezone
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    # Проверяем, включен ли функционал баланса
    is_balance_enabled = await settings_service.is_balance_enabled()
    
    # Проверяем режим баланса (раздельный или объединённый)
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    # Вычисляем отображаемый баланс
    display_balance = get_display_balance(user.balance, referral_balance, is_balance_combined)
    
    # Получаем информацию о планируемых дополнительных устройствах (если выбраны)
    planned_extra_devices = dialog_manager.dialog_data.get("device_count", 0)
    
    # Базовые данные о плане
    result = {
        "plan": plan.name,
        "plan_name": plan.name,
        "description": plan.description or False,
        "type": plan.type,
        "devices": i18n_format_device_limit(plan.device_limit),
        "traffic": i18n_format_traffic_limit(plan.traffic_limit),
        "durations": durations,
        "period": 0,
        "final_amount": 0,
        "currency": "",
        "only_single_plan": only_single_plan,
        # Данные пользователя для шапки
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "balance": display_balance,
        "referral_balance": referral_balance,
        "referral_code": user.referral_code,
        "is_balance_enabled": 1 if is_balance_enabled else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,
        # Данные о стоимости доп. устройств
        "extra_devices_monthly_cost": extra_devices_monthly_cost,
        "has_extra_devices_cost": 1 if extra_devices_monthly_cost > 0 else 0,
        "purchase_type": purchase_type,
        # Планируемые дополнительные устройства
        "planned_extra_devices": planned_extra_devices,
        "has_planned_extra_devices": 1 if planned_extra_devices > 0 else 0,
    }

    # Данные о текущей подписке (если есть)
    subscription = user.current_subscription
    if subscription:
        extra_devices = subscription.extra_devices or 0
        # Вычисляем бонус устройств (БЕЗ купленных доп.)
        plan_device_limit = subscription.plan.device_limit if subscription.plan.device_limit > 0 else 0
        actual_device_limit = subscription.device_limit
        device_limit_bonus = max(0, actual_device_limit - plan_device_limit - extra_devices) if plan_device_limit > 0 else 0
        
        result.update({
            "has_subscription": "true",
            "current_plan_name": subscription.plan.name,
            "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
            "device_limit": i18n_format_device_limit(subscription.device_limit),
            "device_limit_number": subscription.plan.device_limit,
            "device_limit_bonus": device_limit_bonus,
            "extra_devices": extra_devices,
            "has_extra_devices": 1 if extra_devices > 0 else 0,
            "expire_time": i18n_format_expire_time(subscription.expire_at),
        })
    else:
        result.update({
            "has_subscription": "false",
            "current_plan_name": "",
            "traffic_limit": "",
            "device_limit": "",
            "device_limit_number": 0,
            "device_limit_bonus": 0,
            "extra_devices": 0,
            "has_extra_devices": 0,
            "expire_time": "",
        })

    return result


@inject
async def payment_method_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    payment_gateway_service: FromDishka[PaymentGatewayService],
    settings_service: FromDishka[SettingsService],
    pricing_service: FromDishka[PricingService],
    referral_service: FromDishka[ReferralService],
    extra_device_service: FromDishka[ExtraDeviceService],
    i18n: FromDishka[TranslatorRunner],
    **kwargs: Any,
) -> dict[str, Any]:
    from src.core.enums import PaymentGatewayType
    
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    # Получаем настройки глобальной скидки
    global_discount = await settings_service.get_global_discount_settings()

    # Данные о текущей подписке (если есть)
    subscription = user.current_subscription
    device_limit_bonus = 0
    if subscription:
        has_subscription = "true"
        current_plan_name = subscription.plan.name
        traffic_limit = i18n_format_traffic_limit(subscription.traffic_limit)
        device_limit = i18n_format_device_limit(subscription.device_limit)
        device_limit_number = subscription.plan.device_limit
        # Получаем дополнительные устройства
        extra_devices = subscription.extra_devices or 0
        # Вычисляем бонус устройств (БЕЗ купленных доп.)
        plan_device_limit = subscription.plan.device_limit if subscription.plan.device_limit > 0 else 0
        actual_device_limit = subscription.device_limit
        device_limit_bonus = max(0, actual_device_limit - plan_device_limit - extra_devices) if plan_device_limit > 0 else 0
        expire_time = i18n_format_expire_time(subscription.expire_at)
    else:
        has_subscription = "false"
        current_plan_name = ""
        traffic_limit = ""
        device_limit = ""
        device_limit_number = 0
        extra_devices = 0
        expire_time = ""

    gateways = await payment_gateway_service.filter_active()
    selected_duration = dialog_manager.dialog_data["selected_duration"]
    only_single_duration = dialog_manager.dialog_data.get("only_single_duration", False)
    purchase_type = dialog_manager.dialog_data.get("purchase_type")
    duration = plan.get_duration(selected_duration)

    if not duration:
        raise ValueError(f"Duration '{selected_duration}' not found in plan '{plan.name}'")

    # Получаем стоимость дополнительных устройств
    # Используем цену из настроек * количество активных устройств
    extra_devices_monthly_cost = 0
    is_extra_devices_one_time = await settings_service.is_extra_devices_one_time()
    
    if subscription and not is_extra_devices_one_time:
        # Получаем количество активных доп. устройств и цену из настроек
        active_extra_devices = await extra_device_service.get_total_active_devices(subscription.id)
        if active_extra_devices > 0:
            device_price_monthly = await settings_service.get_extra_device_price()
            extra_devices_monthly_cost = device_price_monthly * active_extra_devices
    
    # Рассчитываем стоимость доп. устройств за период (целые месяцы)
    months = duration.days // 30  # Используем целочисленное деление
    extra_devices_cost = extra_devices_monthly_cost * months if extra_devices_monthly_cost > 0 else 0

    # Вычисляем скидку пользователя заранее
    from datetime import datetime, timezone
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    payment_methods = []
    
    # Получаем бонусный баланс пользователя
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )
    
    # Получаем курсы валют для конвертации
    settings = await settings_service.get()
    rates = settings.features.currency_rates
    usd_rate = rates.usd_rate
    eur_rate = rates.eur_rate
    stars_rate = rates.stars_rate
    
    # Проверяем, включен ли функционал баланса
    is_balance_enabled = await settings_service.is_balance_enabled()
    
    # Добавляем оплату с баланса ПЕРВОЙ (если функционал включен, показываем ВСЕГДА даже при нулевом балансе)
    if is_balance_enabled:
        currency = await settings_service.get_default_currency()
        base_price = duration.get_price(currency, usd_rate, eur_rate, stars_rate)
        total_price = base_price + extra_devices_cost if extra_devices_cost > 0 else base_price
        price = pricing_service.calculate(user, total_price, currency, global_discount, context="subscription")
        
        # Вычисляем доступный баланс с учётом режима (COMBINED или SEPARATE)
        is_balance_combined = await settings_service.is_balance_combined()
        available_balance = user.balance + referral_balance if is_balance_combined else user.balance
        
        payment_methods.append(
            {
                "gateway_type": PaymentGatewayType.BALANCE,
                "price": format_price(price.final_amount, Currency.RUB),
                "original_price": format_price(price.original_amount, Currency.RUB),
                "user_balance": available_balance,
                "discount_percent": price.discount_percent,
                "has_discount": 1 if price.discount_percent > 0 else 0,
            }
        )
    
    for gateway in gateways:
        # Пропускаем BALANCE так как он уже добавлен выше
        if gateway.type == PaymentGatewayType.BALANCE:
            continue
            
        gateway_base_price = duration.get_price(gateway.currency, usd_rate, eur_rate, stars_rate)
        
        # Конвертируем стоимость доп. устройств в валюту шлюза (extra_devices_cost в рублях)
        gateway_extra_devices_cost = Decimal(0)
        if extra_devices_cost > 0:
            gateway_extra_devices_cost = pricing_service.convert_currency(
                Decimal(extra_devices_cost),
                gateway.currency,
                usd_rate,
                eur_rate,
                stars_rate,
            )
        
        # Добавляем стоимость доп. устройств (оба значения теперь в валюте шлюза)
        gateway_total_price = gateway_base_price + gateway_extra_devices_cost
        
        # Используем pricing_service для правильного расчёта с учётом всех скидок
        gateway_price = pricing_service.calculate(user, gateway_total_price, gateway.currency, global_discount, context="subscription")
        
        payment_methods.append(
            {
                "gateway_type": gateway.type,
                "price": format_price(gateway_price.final_amount, gateway.currency),
                "original_price": format_price(gateway_price.original_amount, gateway.currency),
                "discount_percent": gateway_price.discount_percent,
                "has_discount": 1 if gateway_price.discount_percent > 0 else 0,
            }
        )

    key, kw = i18n_format_days(duration.days)

    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )
    
    # Проверяем режим баланса (раздельный или объединённый)
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    # Лимит устройств для покупаемой подписки
    # Не показываем (+X) так как дополнительные устройства выводятся отдельной строкой
    device_limit_display = str(plan.device_limit)
    
    # Получаем информацию о планируемых дополнительных устройствах (если выбраны на экране ADD_DEVICE_SELECT_COUNT)
    planned_extra_devices = dialog_manager.dialog_data.get("device_count", 0)
    
    return {
        "has_subscription": has_subscription,
        "current_plan_name": current_plan_name,
        "traffic_limit": traffic_limit,
        "device_limit": device_limit_display,
        "device_limit_number": device_limit_number,
        "device_limit_bonus": device_limit_bonus,
        "extra_devices": extra_devices,
        "has_extra_devices": 1 if extra_devices > 0 else 0,
        "expire_time": expire_time,
        "plan": plan.name,
        "plan_name": plan.name,
        "description": plan.description or False,
        "type": plan.type,
        "devices": i18n_format_device_limit(plan.device_limit),
        "traffic": i18n_format_traffic_limit(plan.traffic_limit),
        "period": i18n.get(key, **kw),
        "payment_methods": payment_methods,
        "final_amount": 0,
        "currency": "",
        "only_single_duration": only_single_duration,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        # Данные пользователя для шапки
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "balance": get_display_balance(user.balance, referral_balance, is_balance_combined),
        "referral_balance": referral_balance,
        "referral_code": user.referral_code,
        "is_balance_enabled": 1 if is_balance_enabled else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,
        # Данные о стоимости доп. устройств
        "extra_devices_monthly_cost": extra_devices_monthly_cost,
        "extra_devices_cost": extra_devices_cost,
        "has_extra_devices_cost": 1 if extra_devices_cost > 0 else 0,
        # Планируемые дополнительные устройства
        "planned_extra_devices": planned_extra_devices,
        "has_planned_extra_devices": 1 if planned_extra_devices > 0 else 0,
    }


@inject
async def confirm_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    i18n: FromDishka[TranslatorRunner],
    payment_gateway_service: FromDishka[PaymentGatewayService],
    referral_service: FromDishka[ReferralService],
    settings_service: FromDishka[SettingsService],
    extra_device_service: FromDishka[ExtraDeviceService],
    pricing_service: FromDishka[PricingService],
    **kwargs: Any,
) -> dict[str, Any]:
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    selected_duration = dialog_manager.dialog_data["selected_duration"]
    only_single_duration = dialog_manager.dialog_data.get("only_single_duration", False)
    is_free = dialog_manager.dialog_data.get("is_free", False)
    selected_payment_method = dialog_manager.dialog_data["selected_payment_method"]
    purchase_type = dialog_manager.dialog_data["purchase_type"]
    payment_gateway = await payment_gateway_service.get_by_type(selected_payment_method)
    duration = plan.get_duration(selected_duration)

    if not duration:
        raise ValueError(f"Duration '{selected_duration}' not found in plan '{plan.name}'")

    if not payment_gateway:
        raise ValueError(f"Not found PaymentGateway by selected type '{selected_payment_method}'")

    result_url = dialog_manager.dialog_data["payment_url"]
    pricing_data = dialog_manager.dialog_data["final_pricing"]
    pricing = PriceDetailsDto.model_validate_json(pricing_data)

    key, kw = i18n_format_days(duration.days)
    gateways = await payment_gateway_service.filter_active()

    from src.core.enums import PaymentGatewayType, ReferralRewardType

    # Получаем курсы валют для конвертации
    settings = await settings_service.get()
    rates = settings.features.currency_rates
    usd_rate = rates.usd_rate
    eur_rate = rates.eur_rate
    stars_rate = rates.stars_rate

    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )

    # Вычисляем скидку пользователя
    from datetime import datetime, timezone
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    # Проверяем, включен ли функционал баланса
    is_balance_enabled = await settings_service.is_balance_enabled()
    
    # Проверяем режим баланса (раздельный или объединённый)
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    # Получаем стоимость доп. устройств из dialog_data (сохранена при создании платежа)
    extra_devices_cost_rub = float(dialog_manager.dialog_data.get("extra_devices_cost", 0) or 0)
    base_subscription_price = float(dialog_manager.dialog_data.get("base_subscription_price", 0) or 0)
    
    # Рассчитываем месячную стоимость для отображения
    # Но только если включена ежемесячная оплата (is_one_time = False)
    from src.core.enums import PurchaseType
    extra_devices_monthly_cost_rub = 0
    is_extra_devices_one_time = await settings_service.is_extra_devices_one_time()
    
    if user.current_subscription and not is_extra_devices_one_time:
        # Получаем количество активных доп. устройств и цену из настроек
        active_extra_devices = await extra_device_service.get_total_active_devices(user.current_subscription.id)
        if active_extra_devices > 0:
            device_price_monthly = await settings_service.get_extra_device_price()
            extra_devices_monthly_cost_rub = device_price_monthly * active_extra_devices
    
    # Получаем информацию о планируемых дополнительных устройствах (если выбраны)
    planned_extra_devices = dialog_manager.dialog_data.get("device_count", 0)
    
    # Данные о текущей подписке (если есть)
    subscription = user.current_subscription
    if subscription:
        has_subscription = "true"
        current_plan_name = subscription.plan.name
        traffic_limit = i18n_format_traffic_limit(subscription.traffic_limit)
        device_limit_current = i18n_format_device_limit(subscription.device_limit)
        device_limit_number = subscription.plan.device_limit
        extra_devices = subscription.extra_devices or 0
        device_limit_bonus = max(0, subscription.device_limit - device_limit_number - extra_devices) if device_limit_number > 0 else 0
        expire_time = i18n_format_expire_time(subscription.expire_at)
    else:
        has_subscription = "false"
        current_plan_name = ""
        traffic_limit = ""
        device_limit_current = ""
        device_limit_number = 0
        extra_devices = 0
        device_limit_bonus = 0
        expire_time = ""
    
    final_amount_for_display = pricing.final_amount
    
    # base_subscription_price и extra_devices_cost_rub уже в валюте шлюза (не нужно конвертировать)
    if base_subscription_price > 0:
        base_subscription_price_converted = format_price(
            Decimal(str(base_subscription_price)),
            payment_gateway.currency
        )
    else:
        # Если base_subscription_price не установлена, вычисляем из общей суммы
        if extra_devices_cost_rub > 0:
            subscription_only_price = pricing.original_amount - Decimal(str(extra_devices_cost_rub))
            base_subscription_price_converted = format_price(subscription_only_price, payment_gateway.currency)
        else:
            base_subscription_price_converted = format_price(pricing.original_amount, payment_gateway.currency)
    
    return {
        "purchase_type": purchase_type,
        "plan": plan.name,
        "plan_name": plan.name,
        "description": plan.description or False,
        "type": plan.type,
        "devices": i18n_format_device_limit(plan.device_limit),
        "traffic": i18n_format_traffic_limit(plan.traffic_limit),
        "period": i18n.get(key, **kw),
        "payment_method": selected_payment_method,
        "gateway_type": payment_gateway.type,
        "final_amount": format_price(final_amount_for_display, payment_gateway.currency),
        "discount_percent": pricing.discount_percent,
        "original_amount": base_subscription_price_converted,
        "url": result_url,
        "only_single_gateway": len(gateways) == 1,
        "only_single_duration": only_single_duration,
        "is_free": is_free,
        "is_telegram_stars": selected_payment_method == PaymentGatewayType.TELEGRAM_STARS,
        "is_yoomoney": selected_payment_method == PaymentGatewayType.YOOMONEY,
        "is_heleket": selected_payment_method == PaymentGatewayType.HELEKET,
        # Данные пользователя для шапки
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "balance": get_display_balance(user.balance, referral_balance, is_balance_combined),
        "referral_balance": referral_balance,
        "referral_code": user.referral_code,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        # Данные о текущей подписке
        "has_subscription": has_subscription,
        "current_plan_name": current_plan_name,
        "traffic_limit": traffic_limit,
        "device_limit_current": device_limit_current,
        "device_limit_number": device_limit_number,
        "device_limit_bonus": device_limit_bonus,
        "extra_devices": extra_devices,
        "expire_time": expire_time,
        "is_balance_enabled": 1 if is_balance_enabled else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,
        # Данные о стоимости доп. устройств
        # extra_devices_monthly_cost_rub - рассчитано в рублях, конвертируем
        # extra_devices_cost_rub - уже в валюте шлюза (не конвертируем)
        "extra_devices_monthly_cost": format_price(
            pricing_service.convert_currency(Decimal(extra_devices_monthly_cost_rub), payment_gateway.currency, usd_rate, eur_rate, stars_rate),
            payment_gateway.currency
        ) if extra_devices_monthly_cost_rub > 0 else "0",
        "extra_devices_cost": format_price(
            Decimal(str(extra_devices_cost_rub)),
            payment_gateway.currency
        ) if extra_devices_cost_rub > 0 else "0",
        "has_extra_devices_cost": 1 if extra_devices_cost_rub > 0 else 0,
        "total_payment": format_price(pricing.original_amount, payment_gateway.currency),
        # Планируемые дополнительные устройства
        "planned_extra_devices": planned_extra_devices,
        "has_planned_extra_devices": 1 if planned_extra_devices > 0 else 0,
    }


@inject
async def confirm_balance_getter(
    dialog_manager: DialogManager,
    i18n: FromDishka[TranslatorRunner],
    user: UserDto,
    referral_service: FromDishka[ReferralService],
    settings_service: FromDishka[SettingsService],
    extra_device_service: FromDishka[ExtraDeviceService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Getter for balance payment confirmation page."""
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    selected_duration = dialog_manager.dialog_data["selected_duration"]
    only_single_duration = dialog_manager.dialog_data.get("only_single_duration", False)
    purchase_type = dialog_manager.dialog_data["purchase_type"]
    duration = plan.get_duration(selected_duration)

    if not duration:
        raise ValueError(f"Duration '{selected_duration}' not found in plan '{plan.name}'")

    pricing_data = dialog_manager.dialog_data["final_pricing"]
    pricing = PriceDetailsDto.model_validate_json(pricing_data)
    currency = dialog_manager.dialog_data["balance_currency"]

    key, kw = i18n_format_days(duration.days)

    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )

    # Вычисляем скидку пользователя
    from datetime import datetime, timezone
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    # Вычисляем доступный баланс с учётом режима (COMBINED или SEPARATE)
    is_balance_combined = await settings_service.is_balance_combined()
    available_balance = user.balance + referral_balance if is_balance_combined else user.balance

    result = {
        "purchase_type": purchase_type,
        "plan": plan.name,
        "plan_name": plan.name,
        "description": plan.description or False,
        "type": plan.type,
        "devices": i18n_format_device_limit(plan.device_limit),
        "traffic": i18n_format_traffic_limit(plan.traffic_limit),
        "period": i18n.get(key, **kw),
        "final_amount": format_price(int(pricing.final_amount), Currency.RUB),
        "discount_percent": pricing.discount_percent,
        "original_amount": format_price(int(pricing.original_amount), Currency.RUB),
        "currency": currency,
        "user_balance": format_price(int(available_balance), Currency.RUB),
        "balance_after": format_price(int(available_balance - pricing.final_amount), Currency.RUB),
        "only_single_duration": only_single_duration,
        # Данные пользователя для профиля
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "balance": format_price(int(available_balance), Currency.RUB),
        "referral_balance": format_price(int(referral_balance), Currency.RUB),
        "referral_code": user.referral_code,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
    }

    # DEBUG: Логируем значения для отладки
    from src.core.logger import logger
    logger.info(
        f"[confirm_balance_getter] user={user.telegram_id}: "
        f"user_balance={user.balance}, "
        f"final_amount={pricing.final_amount}, "
        f"original_amount={pricing.original_amount}, "
        f"balance_after={user.balance - pricing.final_amount}"
    )

    # Проверяем, включен ли функционал баланса
    is_balance_enabled = await settings_service.is_balance_enabled()
    result["is_balance_enabled"] = 1 if is_balance_enabled else 0
    
    # Проверяем режим баланса (раздельный или объединённый)
    is_balance_separate = not is_balance_combined
    result["is_balance_separate"] = 1 if is_balance_separate else 0

    # Получаем информацию о планируемых дополнительных устройствах (если выбраны)
    planned_extra_devices = dialog_manager.dialog_data.get("device_count", 0)
    
    # Получаем сохранённые данные о стоимости из dialog_data
    base_subscription_price = dialog_manager.dialog_data.get("base_subscription_price", int(pricing.original_amount))
    saved_extra_devices_cost = dialog_manager.dialog_data.get("extra_devices_cost", 0)

    # Данные о текущей подписке (если есть)
    subscription = user.current_subscription
    if subscription:
        extra_devices = subscription.extra_devices or 0
        device_limit_number = subscription.plan.device_limit
        device_limit_bonus = max(0, subscription.device_limit - device_limit_number - extra_devices) if device_limit_number > 0 else 0
        
        # Получаем месячную стоимость для отображения
        # Используем цену из настроек * количество активных устройств
        extra_devices_monthly_cost = 0
        is_extra_devices_one_time = await settings_service.is_extra_devices_one_time()
        
        if not is_extra_devices_one_time:
            active_extra_devices = await extra_device_service.get_total_active_devices(subscription.id)
            if active_extra_devices > 0:
                device_price_monthly = await settings_service.get_extra_device_price()
                extra_devices_monthly_cost = device_price_monthly * active_extra_devices
        
        # total_payment = pricing.original_amount (уже включает доп. устройства)
        total_payment = pricing.original_amount
        
        result.update({
            "has_subscription": "true",
            "current_plan_name": subscription.plan.name,
            "plan_name": subscription.plan.name,
            "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
            "device_limit": i18n_format_device_limit(subscription.device_limit),
            "device_limit_number": device_limit_number,
            "device_limit_bonus": device_limit_bonus,
            "extra_devices": extra_devices,
            "expire_time": i18n_format_expire_time(subscription.expire_at),
            "extra_devices_monthly_cost": format_price(int(extra_devices_monthly_cost), Currency.RUB) if extra_devices_monthly_cost > 0 else "0",
            "extra_devices_cost": format_price(int(saved_extra_devices_cost), Currency.RUB) if saved_extra_devices_cost > 0 else "0",
            "has_extra_devices_cost": 1 if saved_extra_devices_cost > 0 else 0,
            "total_payment": format_price(int(total_payment), Currency.RUB),
            "balance_after": format_price(int(available_balance - pricing.final_amount), Currency.RUB),
            "original_amount": format_price(int(base_subscription_price), Currency.RUB),  # Цена подписки БЕЗ доп. устройств
            "user_balance": format_price(int(available_balance), Currency.RUB),
            "planned_extra_devices": planned_extra_devices,
            "has_planned_extra_devices": 1 if planned_extra_devices > 0 else 0,
        })
    else:
        result.update({
            "has_subscription": "false",
            "current_plan_name": "",
            "plan_name": "",
            "traffic_limit": "",
            "device_limit": "",
            "device_limit_number": 0,
            "device_limit_bonus": 0,
            "extra_devices": 0,
            "expire_time": "",
            "extra_devices_monthly_cost": "0",
            "extra_devices_cost": "0",
            "has_extra_devices_cost": 0,
            "total_payment": format_price(int(pricing.original_amount), Currency.RUB),
            "planned_extra_devices": planned_extra_devices,
            "has_planned_extra_devices": 1 if planned_extra_devices > 0 else 0,
        })

    return result


@inject
async def confirm_yoomoney_getter(
    dialog_manager: DialogManager,
    i18n: FromDishka[TranslatorRunner],
    user: UserDto,
    extra_device_service: FromDishka[ExtraDeviceService],
    settings_service: FromDishka[SettingsService],
    referral_service: FromDishka[ReferralService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Getter for Yoomoney/Bank card payment confirmation page."""
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    selected_duration = dialog_manager.dialog_data["selected_duration"]
    purchase_type = dialog_manager.dialog_data["purchase_type"]
    duration = plan.get_duration(selected_duration)

    if not duration:
        raise ValueError(f"Duration '{selected_duration}' not found in plan '{plan.name}'")

    pricing_data = dialog_manager.dialog_data["final_pricing"]
    pricing = PriceDetailsDto.model_validate_json(pricing_data)
    currency = dialog_manager.dialog_data.get("selected_currency", "RUB")
    result_url = dialog_manager.dialog_data["payment_url"]

    key, kw = i18n_format_days(duration.days)
    
    # Получаем информацию о планируемых дополнительных устройствах (если выбраны)
    planned_extra_devices = dialog_manager.dialog_data.get("device_count", 0)
    
    # Получаем сохранённые данные о стоимости из dialog_data
    base_subscription_price = dialog_manager.dialog_data.get("base_subscription_price", int(pricing.original_amount))
    saved_extra_devices_cost = dialog_manager.dialog_data.get("extra_devices_cost", 0)
    
    # Получаем месячную стоимость для отображения
    # Используем цену из настроек * количество активных устройств
    from src.core.enums import PurchaseType
    extra_devices_monthly_cost = 0
    is_extra_devices_one_time = await settings_service.is_extra_devices_one_time()
    
    if user.current_subscription and not is_extra_devices_one_time:
        active_extra_devices_yoomoney = await extra_device_service.get_total_active_devices(user.current_subscription.id)
        if active_extra_devices_yoomoney > 0:
            device_price_monthly = await settings_service.get_extra_device_price()
            extra_devices_monthly_cost = device_price_monthly * active_extra_devices_yoomoney

    # Получаем реферальный баланс
    from src.core.enums import ReferralRewardType
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )

    # Вычисляем скидку пользователя
    from datetime import datetime, timezone
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    return {
        "purchase_type": purchase_type,
        "plan": plan.name,
        "plan_name": plan.name,
        "description": plan.description or False,
        "type": plan.type,
        "devices": i18n_format_device_limit(plan.device_limit),
        "traffic": i18n_format_traffic_limit(plan.traffic_limit),
        "period": i18n.get(key, **kw),
        "final_amount": format_price(int(pricing.final_amount), Currency.RUB),
        "discount_percent": pricing.discount_percent,
        "original_amount": format_price(int(base_subscription_price), Currency.RUB),  # Цена подписки БЕЗ доп. устройств
        "currency": currency,
        "url": result_url,
        # Данные о стоимости доп. устройств
        "extra_devices_monthly_cost": format_price(int(extra_devices_monthly_cost), Currency.RUB) if extra_devices_monthly_cost > 0 else "0",
        "extra_devices_cost": format_price(int(saved_extra_devices_cost), Currency.RUB) if saved_extra_devices_cost > 0 else "0",
        "has_extra_devices_cost": 1 if saved_extra_devices_cost > 0 else 0,
        "total_payment": format_price(int(pricing.final_amount), Currency.RUB),
        # Планируемые дополнительные устройства
        "planned_extra_devices": planned_extra_devices,
        "has_planned_extra_devices": 1 if planned_extra_devices > 0 else 0,
        # User profile data
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "balance": user.balance,
        "referral_balance": referral_balance,
        "referral_code": user.referral_code,
        # Discount data
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        # Subscription data
        "has_subscription": "true" if user.current_subscription else "false",
        "current_plan_name": user.current_subscription.plan.name if user.current_subscription else "",
        "plan_name": user.current_subscription.plan.name if user.current_subscription else "",
        "traffic_limit": i18n_format_traffic_limit(user.current_subscription.traffic_limit) if user.current_subscription else "",
        "device_limit_current": i18n_format_device_limit(user.current_subscription.device_limit) if user.current_subscription else "",
        "device_limit_number": user.current_subscription.plan.device_limit if user.current_subscription else 0,
        "device_limit_bonus": max(0, user.current_subscription.device_limit - user.current_subscription.plan.device_limit - (user.current_subscription.extra_devices or 0)) if user.current_subscription and user.current_subscription.plan.device_limit > 0 else 0,
        "extra_devices": user.current_subscription.extra_devices or 0 if user.current_subscription else 0,
        "expire_time": i18n_format_expire_time(user.current_subscription.expire_at) if user.current_subscription else "",
        # Balance settings
        "is_balance_enabled": 1 if await settings_service.is_balance_enabled() else 0,
        "is_balance_separate": 0 if await settings_service.is_balance_combined() else 1,
    }


@inject
async def confirm_yookassa_getter(
    dialog_manager: DialogManager,
    i18n: FromDishka[TranslatorRunner],
    user: UserDto,
    extra_device_service: FromDishka[ExtraDeviceService],
    settings_service: FromDishka[SettingsService],
    referral_service: FromDishka[ReferralService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Getter for Yookassa payment confirmation page."""
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    selected_duration = dialog_manager.dialog_data["selected_duration"]
    purchase_type = dialog_manager.dialog_data["purchase_type"]
    duration = plan.get_duration(selected_duration)

    if not duration:
        raise ValueError(f"Duration '{selected_duration}' not found in plan '{plan.name}'")

    pricing_data = dialog_manager.dialog_data["final_pricing"]
    pricing = PriceDetailsDto.model_validate_json(pricing_data)
    currency = dialog_manager.dialog_data.get("selected_currency", "RUB")
    result_url = dialog_manager.dialog_data["payment_url"]

    key, kw = i18n_format_days(duration.days)
    
    # Получаем информацию о планируемых дополнительных устройствах (если выбраны)
    planned_extra_devices = dialog_manager.dialog_data.get("device_count", 0)
    
    # Получаем сохранённые данные о стоимости из dialog_data
    base_subscription_price = dialog_manager.dialog_data.get("base_subscription_price", int(pricing.original_amount))
    saved_extra_devices_cost = dialog_manager.dialog_data.get("extra_devices_cost", 0)
    
    # Получаем месячную стоимость для отображения
    # Используем цену из настроек * количество активных устройств
    from src.core.enums import PurchaseType
    extra_devices_monthly_cost = 0
    is_extra_devices_one_time = await settings_service.is_extra_devices_one_time()
    
    if user.current_subscription and not is_extra_devices_one_time:
        active_extra_devices_yookassa = await extra_device_service.get_total_active_devices(user.current_subscription.id)
        if active_extra_devices_yookassa > 0:
            device_price_monthly = await settings_service.get_extra_device_price()
            extra_devices_monthly_cost = device_price_monthly * active_extra_devices_yookassa

    # Получаем реферальный баланс
    from src.core.enums import ReferralRewardType
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )

    # Вычисляем скидку пользователя
    from datetime import datetime, timezone
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    return {
        "purchase_type": purchase_type,
        "plan": plan.name,
        "plan_name": plan.name,
        "description": plan.description or False,
        "type": plan.type,
        "devices": i18n_format_device_limit(plan.device_limit),
        "traffic": i18n_format_traffic_limit(plan.traffic_limit),
        "period": i18n.get(key, **kw),
        "final_amount": format_price(int(pricing.final_amount), Currency.RUB),
        "discount_percent": pricing.discount_percent,
        "original_amount": format_price(int(base_subscription_price), Currency.RUB),  # Цена подписки БЕЗ доп. устройств
        "currency": currency,
        "url": result_url,
        # Данные о стоимости доп. устройств
        "extra_devices_monthly_cost": format_price(int(extra_devices_monthly_cost), Currency.RUB) if extra_devices_monthly_cost > 0 else "0",
        "extra_devices_cost": format_price(int(saved_extra_devices_cost), Currency.RUB) if saved_extra_devices_cost > 0 else "0",
        "has_extra_devices_cost": 1 if saved_extra_devices_cost > 0 else 0,
        "total_payment": format_price(int(pricing.final_amount), Currency.RUB),
        # Планируемые дополнительные устройства
        "planned_extra_devices": planned_extra_devices,
        "has_planned_extra_devices": 1 if planned_extra_devices > 0 else 0,
        # User profile data
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "balance": user.balance,
        "referral_balance": referral_balance,
        "referral_code": user.referral_code,
        # Discount data
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        # Subscription data
        "has_subscription": "true" if user.current_subscription else "false",
        "current_plan_name": user.current_subscription.plan.name if user.current_subscription else "",
        "plan_name": user.current_subscription.plan.name if user.current_subscription else "",
        "traffic_limit": i18n_format_traffic_limit(user.current_subscription.traffic_limit) if user.current_subscription else "",
        "device_limit_current": i18n_format_device_limit(user.current_subscription.device_limit) if user.current_subscription else "",
        "device_limit_number": user.current_subscription.plan.device_limit if user.current_subscription else 0,
        "device_limit_bonus": max(0, user.current_subscription.device_limit - user.current_subscription.plan.device_limit - (user.current_subscription.extra_devices or 0)) if user.current_subscription and user.current_subscription.plan.device_limit > 0 else 0,
        "extra_devices": user.current_subscription.extra_devices or 0 if user.current_subscription else 0,
        "expire_time": i18n_format_expire_time(user.current_subscription.expire_at) if user.current_subscription else "",
        # Balance settings
        "is_balance_enabled": 1 if await settings_service.is_balance_enabled() else 0,
        "is_balance_separate": 0 if await settings_service.is_balance_combined() else 1,
    }


@inject
async def getter_connect(
    dialog_manager: DialogManager,
    config: AppConfig,
    user: UserDto,
    referral_service: FromDishka[ReferralService],
    settings_service: FromDishka[SettingsService],
    user_service: FromDishka[UserService],
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Getter для экрана подключения после успешного создания пробной подписки.
    Безопасно работает даже если подписка не найдена сразу (может быть задержка БД).
    """
    
    # Пытаемся получить подписку
    subscription = user.current_subscription
    
    # Если нет подписки в текущих данных, пытаемся перезагрузить
    if not subscription:
        try:
            fresh_user = await user_service.get(user.telegram_id)
            if fresh_user and fresh_user.current_subscription:
                subscription = fresh_user.current_subscription
                user = fresh_user
                logger.info(f"getter_connect: Loaded subscription from fresh user data for {user.telegram_id}")
        except Exception as e:
            logger.warning(f"getter_connect: Failed to reload user: {e}")
    
    # Если всё ещё нет подписки - это нормально, показываем что можем
    # (она была только что создана, может быть задержка)
    if not subscription:
        logger.warning(
            f"getter_connect: No subscription found for user '{user.telegram_id}' "
            f"(but it should have been just created)"
        )
        
        # Возвращаем безопасные данные для рендеринга
        # Пользователь увидит экран с общей информацией
        return {
            "has_subscription": 0,
            "plan_name": "Подписка активирована",
            "traffic_limit": "Загружается...",
            "device_limit": "Загружается...",
            "expire_time": "Загружается...",
            "user_id": str(user.telegram_id),
            "user_name": user.name,
            "balance": user.balance,
            "referral_balance": 0,
            "referral_code": user.referral_code,
            "is_balance_enabled": 1 if await settings_service.is_balance_enabled() else 0,
            "is_balance_separate": 1 if not await settings_service.is_balance_combined() else 0,
        }
    
    # Есть подписка - показываем её данные
    # Get referral balance
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )
    
    # Format subscription data safely
    try:
        plan_name = subscription.plan.name if subscription.plan else "Unknown"
    except Exception as e:
        plan_name = "Unknown"
    
    try:
        traffic_limit = i18n_format_traffic_limit(subscription.traffic_limit)
    except Exception as e:
        traffic_limit = "Unknown"
    
    try:
        device_limit = i18n_format_device_limit(subscription.device_limit)
    except Exception as e:
        device_limit = "Unknown"
    
    try:
        expire_time = i18n_format_expire_time(subscription.expire_at)
    except Exception as e:
        expire_time = "Unknown"

    # Вычисляем скидку пользователя
    from datetime import datetime, timezone
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    # Get extra devices and device limit number
    extra_devices = subscription.extra_devices or 0
    device_limit_number = subscription.plan.device_limit if subscription.plan else 0
    
    # Get balance mode
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    return {
        "is_app": config.bot.is_mini_app,
        "url": config.bot.mini_app_url or subscription.url,
        "connectable": True,
        # User data
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "referral_code": user.referral_code or "—",
        "referral_balance": referral_balance,
        "balance": user.balance,
        "is_balance_enabled": 1 if await settings_service.is_balance_enabled() else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        # Subscription data
        "plan_name": plan_name,
        "traffic_limit": traffic_limit,
        "device_limit": device_limit,
        "device_limit_number": device_limit_number,
        "device_limit_bonus": max(0, subscription.device_limit - device_limit_number) if device_limit_number > 0 else 0,
        "extra_devices": extra_devices,
        "expire_time": expire_time,
    }


@inject
async def success_payment_getter(
    dialog_manager: DialogManager,
    config: AppConfig,
    user: UserDto,
    user_service: FromDishka[UserService],
    referral_service: FromDishka[ReferralService],
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    # Try to get purchase_type from dialog_data first, then from start_data
    purchase_type: PurchaseType = dialog_manager.dialog_data.get("purchase_type")
    if not purchase_type:
        start_data = cast(dict[str, Any], dialog_manager.start_data)
        if start_data:
            purchase_type = start_data.get("purchase_type", PurchaseType.NEW)
        else:
            purchase_type = PurchaseType.NEW
    
    # Очищаем кэш и получаем свежие данные пользователя
    await user_service.clear_user_cache(user.telegram_id)
    fresh_user = await user_service.get(user.telegram_id)
    if not fresh_user:
        fresh_user = user
    
    subscription = fresh_user.current_subscription

    if not subscription:
        raise ValueError(f"User '{fresh_user.telegram_id}' has no active subscription after purchase")

    # Получаем реферальный баланс
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=fresh_user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )

    # Вычисляем скидку пользователя
    from datetime import datetime, timezone
    purchase_disc = fresh_user.purchase_discount if fresh_user.purchase_discount is not None else 0
    personal_disc = fresh_user.personal_discount if fresh_user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and fresh_user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if fresh_user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = fresh_user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    # Проверяем, включен ли функционал баланса
    is_balance_enabled = await settings_service.is_balance_enabled()
    
    # Проверяем режим баланса (раздельный или объединённый)
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    # Вычисляем лимиты устройств
    extra_devices = subscription.extra_devices or 0
    # device_limit_number - базовый лимит из тарифа
    device_limit_number = subscription.plan.device_limit
    device_limit_bonus = max(0, subscription.device_limit - device_limit_number - extra_devices) if device_limit_number > 0 else 0
    
    # Получаем device_count из dialog_data для ADD_DEVICE
    device_count = dialog_manager.dialog_data.get("device_count", 0)
    
    return {
        "purchase_type": purchase_type,
        "plan_name": subscription.plan.name,
        "is_trial": 1 if subscription.is_trial else 0,
        "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
        "device_limit": i18n_format_device_limit(subscription.device_limit),
        "device_limit_number": device_limit_number,
        "device_limit_bonus": device_limit_bonus,
        "extra_devices": extra_devices,
        "expire_time": i18n_format_expire_time(subscription.expire_at),
        "added_duration": i18n_format_days(subscription.plan.duration),
        "is_app": config.bot.is_mini_app,
        "url": config.bot.mini_app_url or subscription.url,
        "connectable": True,
        # Данные профиля пользователя
        "user_id": str(fresh_user.telegram_id),
        "user_name": fresh_user.name,
        "balance": fresh_user.balance,
        "referral_balance": referral_balance,
        "referral_code": fresh_user.referral_code,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "is_balance_enabled": 1 if is_balance_enabled else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,
        # Для ADD_DEVICE
        "device_count": device_count,
    }


@inject
@inject
async def referral_success_getter(
    dialog_manager: DialogManager,
    config: AppConfig,
    user: UserDto,
    referral_service: FromDishka[ReferralService],
    user_service: FromDishka[UserService],
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для экрана успеха реферальной подписки.
    
    ВАЖНО: Получает СВЕЖИЕ данные пользователя из базы, так как
    user из middleware может быть устаревшим после обновления подписки.
    """
    # Получаем свежие данные пользователя
    await user_service.clear_user_cache(user.telegram_id)
    fresh_user = await user_service.get(user.telegram_id)
    
    if not fresh_user or not fresh_user.current_subscription:
        raise ValueError(f"User '{user.telegram_id}' has no active subscription after referral upgrade")

    subscription = fresh_user.current_subscription
    
    # Get referral balance
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=fresh_user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )
    
    # Проверяем режим баланса (раздельный или объединённый)
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    # Вычисляем скидку пользователя
    from datetime import datetime, timezone
    purchase_disc = fresh_user.purchase_discount if fresh_user.purchase_discount is not None else 0
    personal_disc = fresh_user.personal_discount if fresh_user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and fresh_user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if fresh_user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = fresh_user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    return {
        "is_app": config.bot.is_mini_app,
        "url": config.bot.mini_app_url or subscription.url,
        "connectable": True,
        # User data (свежие данные)
        "user_id": str(fresh_user.telegram_id),
        "user_name": fresh_user.name,
        "referral_code": fresh_user.referral_code or "—",
        "referral_balance": referral_balance,
        "balance": fresh_user.balance,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "is_balance_enabled": 1 if await settings_service.is_balance_enabled() else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,
        # Subscription data (свежие данные)
        "plan_name": subscription.plan.name if subscription.plan else "Unknown",
        "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
        "device_limit": i18n_format_device_limit(subscription.device_limit),
        "device_limit_number": subscription.plan.device_limit,
        "device_limit_bonus": max(0, subscription.device_limit - subscription.plan.device_limit - (subscription.extra_devices or 0)) if subscription.plan.device_limit > 0 else 0,
        "extra_devices": subscription.extra_devices or 0,
        "expire_time": i18n_format_expire_time(subscription.expire_at),
    }


@inject
async def add_device_select_count_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    referral_service: FromDishka[ReferralService],
    settings_service: FromDishka[SettingsService],
    pricing_service: FromDishka[PricingService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна выбора количества дополнительных устройств."""
    from decimal import Decimal
    
    # Получаем цену дополнительного устройства из настроек (за месяц)
    # Показываем МЕСЯЧНУЮ цену из настроек, не пропорциональную
    device_price_monthly = await settings_service.get_extra_device_price()
    
    # Получаем реферальный баланс
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )

    # Получаем глобальную скидку
    global_discount = await settings_service.get_global_discount_settings()
    
    # Вычисляем цену со скидкой используя PricingService (для месячной цены)
    price_details = pricing_service.calculate(
        user=user,
        price=Decimal(device_price_monthly),
        currency=Currency.RUB,
        global_discount=global_discount,
        context="extra_devices",
    )
    
    discounted_device_price = int(price_details.final_amount)
    has_discount = price_details.discount_percent > 0
    
    # Вычисляем информацию о скидке для отображения
    from datetime import datetime, timezone
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    # Проверяем, включен ли функционал баланса
    is_balance_enabled = await settings_service.is_balance_enabled()
    
    # Проверяем режим баланса (раздельный или объединённый)
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    # Вычисляем отображаемый баланс
    display_balance = get_display_balance(user.balance, referral_balance, is_balance_combined)
    
    # Вычисляем лимиты устройств
    subscription = user.current_subscription
    extra_devices = subscription.extra_devices or 0 if subscription else 0
    # device_limit_number - это лимит из тарифного плана
    plan_device_limit = subscription.plan.device_limit if subscription and subscription.plan and subscription.plan.device_limit > 0 else 0
    device_limit_number = plan_device_limit if plan_device_limit > 0 else (subscription.device_limit if subscription else 0)
    # device_limit_bonus - добавлено админом (общий лимит - план - купленные)
    device_limit_bonus = max(0, subscription.device_limit - plan_device_limit - extra_devices) if subscription and plan_device_limit > 0 else 0
    
    return {
        # Данные пользователя
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "referral_code": user.referral_code,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "balance": display_balance,
        "referral_balance": referral_balance,
        "is_balance_enabled": 1 if is_balance_enabled else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,
        # Данные подписки
        "plan_name": subscription.plan.name if subscription else "",
        "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit) if subscription else "",
        "device_limit": i18n_format_device_limit(subscription.device_limit) if subscription else "",
        "device_limit_number": device_limit_number,
        "device_limit_bonus": device_limit_bonus,
        "extra_devices": extra_devices,
        "expire_time": i18n_format_expire_time(subscription.expire_at) if subscription else "",
        # Цена за МЕСЯЦ (из настроек, со скидкой)
        "device_price": discounted_device_price,
        "device_price_original": device_price_monthly,
        "has_discount": 1 if has_discount else 0,
    }


@inject
async def add_device_duration_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    referral_service: FromDishka[ReferralService],
    settings_service: FromDishka[SettingsService],
    pricing_service: FromDishka[PricingService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна выбора типа покупки дополнительных устройств."""
    from decimal import Decimal
    from src.core.utils.pricing import (
        calculate_device_price_until_subscription_end,
        calculate_device_price_until_month_end,
        MIN_EXTRA_DEVICE_DAYS,
    )
    
    # Получаем количество устройств из dialog_data
    device_count = dialog_manager.dialog_data.get("device_count", 1)
    
    # Получаем цену дополнительного устройства из настроек (за месяц)
    device_price_monthly = await settings_service.get_extra_device_price()
    
    # Получаем реферальный баланс
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )

    # Получаем глобальную скидку
    global_discount = await settings_service.get_global_discount_settings()
    
    subscription = user.current_subscription
    
    # Рассчитываем стоимость для обоих вариантов
    if subscription:
        # Вариант 1: До конца подписки
        price_full, days_full = calculate_device_price_until_subscription_end(
            monthly_price=device_price_monthly,
            subscription_expire_at=subscription.expire_at,
            min_days=MIN_EXTRA_DEVICE_DAYS,
        )
        
        # Вариант 2: До конца месяца подписки
        price_month, days_month = calculate_device_price_until_month_end(
            monthly_price=device_price_monthly,
            subscription_expire_at=subscription.expire_at,
            min_days=MIN_EXTRA_DEVICE_DAYS,
        )
    else:
        # Если нет подписки, используем полную цену
        price_full = device_price_monthly
        days_full = 30
        price_month = device_price_monthly
        days_month = 30
    
    # Умножаем на количество устройств
    total_price_full = price_full * device_count
    total_price_month = price_month * device_count
    
    # Применяем скидки через PricingService
    price_details_full = pricing_service.calculate(
        user=user,
        price=Decimal(total_price_full),
        currency=Currency.RUB,
        global_discount=global_discount,
        context="extra_devices",
    )
    
    price_details_month = pricing_service.calculate(
        user=user,
        price=Decimal(total_price_month),
        currency=Currency.RUB,
        global_discount=global_discount,
        context="extra_devices",
    )
    
    discounted_price_full = int(price_details_full.final_amount)
    discounted_price_month = int(price_details_month.final_amount)
    has_discount = price_details_full.discount_percent > 0
    
    # Вычисляем информацию о скидке для отображения
    from datetime import datetime, timezone
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    # Проверяем, включен ли функционал баланса
    is_balance_enabled = await settings_service.is_balance_enabled()
    
    # Проверяем режим баланса (раздельный или объединённый)
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    # Вычисляем отображаемый баланс
    display_balance = get_display_balance(user.balance, referral_balance, is_balance_combined)
    
    # Вычисляем лимиты устройств
    extra_devices = subscription.extra_devices or 0 if subscription else 0
    plan_device_limit = subscription.plan.device_limit if subscription and subscription.plan and subscription.plan.device_limit > 0 else 0
    device_limit_number = plan_device_limit if plan_device_limit > 0 else (subscription.device_limit if subscription else 0)
    device_limit_bonus = max(0, subscription.device_limit - plan_device_limit - extra_devices) if subscription and plan_device_limit > 0 else 0
    
    return {
        # Данные пользователя
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "referral_code": user.referral_code,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "balance": display_balance,
        "referral_balance": referral_balance,
        "is_balance_enabled": 1 if is_balance_enabled else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,
        # Данные подписки
        "plan_name": subscription.plan.name if subscription else "",
        "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit) if subscription else "",
        "device_limit": i18n_format_device_limit(subscription.device_limit) if subscription else "",
        "device_limit_number": device_limit_number,
        "device_limit_bonus": device_limit_bonus,
        "extra_devices": extra_devices,
        "expire_time": i18n_format_expire_time(subscription.expire_at) if subscription else "",
        # Данные о покупке
        "device_count": device_count,
        # Вариант 1: До конца подписки
        "price_full": discounted_price_full,
        "price_full_original": total_price_full,
        "days_full": days_full,
        # Вариант 2: До конца месяца
        "price_month": discounted_price_month,
        "price_month_original": total_price_month,
        "days_month": days_month,
        # Общие данные о скидке
        "has_discount": 1 if has_discount else 0,
        # Месячная цена для информации
        "device_price_monthly": device_price_monthly,
    }


@inject
async def add_device_payment_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    payment_gateway_service: FromDishka[PaymentGatewayService],
    referral_service: FromDishka[ReferralService],
    settings_service: FromDishka[SettingsService],
    pricing_service: FromDishka[PricingService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна выбора способа оплаты при добавлении устройств."""
    from decimal import Decimal
    
    # Получаем количество устройств и тип покупки из dialog_data
    device_count = dialog_manager.dialog_data.get("device_count", 1)
    duration_type = dialog_manager.dialog_data.get("duration_type", "full")  # "full" или "month"
    
    # Получаем уже рассчитанную цену из dialog_data (установлена на шаге выбора типа)
    # Если не установлена - рассчитываем заново
    device_price_rub = dialog_manager.dialog_data.get("calculated_price")
    duration_days = dialog_manager.dialog_data.get("duration_days", 30)
    
    if device_price_rub is None:
        from src.core.utils.pricing import (
            calculate_device_price_until_subscription_end,
            calculate_device_price_until_month_end,
            MIN_EXTRA_DEVICE_DAYS,
        )
        
        device_price_monthly = await settings_service.get_extra_device_price()
        
        if user.current_subscription:
            if duration_type == "month":
                price_per_device, duration_days = calculate_device_price_until_month_end(
                    monthly_price=device_price_monthly,
                    subscription_expire_at=user.current_subscription.expire_at,
                    min_days=MIN_EXTRA_DEVICE_DAYS,
                )
            else:
                price_per_device, duration_days = calculate_device_price_until_subscription_end(
                    monthly_price=device_price_monthly,
                    subscription_expire_at=user.current_subscription.expire_at,
                    min_days=MIN_EXTRA_DEVICE_DAYS,
                )
            device_price_rub = price_per_device * device_count
        else:
            device_price_rub = device_price_monthly * device_count
    
    # Получаем реферальный баланс
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )

    # Получаем глобальную скидку
    global_discount = await settings_service.get_global_discount_settings()
    
    # Получаем курсы валют для конвертации
    settings = await settings_service.get()
    rates = settings.features.currency_rates
    usd_rate = rates.usd_rate
    eur_rate = rates.eur_rate
    stars_rate = rates.stars_rate
    
    # Вычисляем цену со скидкой используя PricingService
    original_price = device_price_rub
    price_details = pricing_service.calculate(
        user=user,
        price=Decimal(original_price),
        currency=Currency.RUB,
        global_discount=global_discount,
        context="extra_devices",
    )
    
    # Результат в рублях (не умножаем на 100, цены хранятся в рублях)
    total_price_rub = int(price_details.final_amount)
    original_price_rub = int(price_details.original_amount)
    has_discount = price_details.discount_percent > 0
    
    # Вычисляем информацию о скидке для отображения
    from datetime import datetime, timezone
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    # Проверяем, включен ли функционал баланса
    is_balance_enabled = await settings_service.is_balance_enabled()
    
    # Проверяем режим баланса (раздельный или объединённый)
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    # Вычисляем отображаемый баланс
    display_balance = get_display_balance(user.balance, referral_balance, is_balance_combined)
    
    # Вычисляем лимиты устройств
    subscription = user.current_subscription
    extra_devices = subscription.extra_devices or 0 if subscription else 0
    # device_limit_number - это лимит из тарифного плана
    plan_device_limit = subscription.plan.device_limit if subscription and subscription.plan and subscription.plan.device_limit > 0 else 0
    device_limit_number = plan_device_limit if plan_device_limit > 0 else (subscription.device_limit if subscription else 0)
    # device_limit_bonus - добавлено админом (общий лимит - план - купленные)
    device_limit_bonus = max(0, subscription.device_limit - plan_device_limit - extra_devices) if subscription and plan_device_limit > 0 else 0
    
    gateways = await payment_gateway_service.filter_active()
    currency = await settings_service.get_default_currency()
    
    payment_methods = []
    
    # Добавляем оплату с баланса ВСЕГДА ПЕРВОЙ (даже если баланса недостаточно)
    # Сохраняем цены для возвращения в результате (в валюте по умолчанию - RUB)
    total_price = total_price_rub
    original_price = original_price_rub
    
    payment_methods.append({
        "gateway_type": PaymentGatewayType.BALANCE,
        "price": format_price(total_price_rub, Currency.RUB),
        "original_price": format_price(original_price_rub, Currency.RUB),
        "has_discount": 1 if has_discount else 0,
        "discount_percent": price_details.discount_percent,
    })
    
    # Добавляем другие способы оплаты
    for gateway in gateways:
        # Пропускаем BALANCE так как он уже добавлен выше
        if gateway.type == PaymentGatewayType.BALANCE:
            continue
            
        # Получаем валюту для конкретного шлюза
        gateway_currency = Currency.from_gateway_type(gateway.type)
        
        # Конвертируем цену в валюту способа оплаты
        # total_price_rub и original_price_rub уже в рублях
        # Результат convert_currency в целевой валюте (Decimal)
        converted_original_decimal = pricing_service.convert_currency(
            Decimal(original_price_rub),
            gateway_currency,
            usd_rate,
            eur_rate,
            stars_rate,
        )
        converted_total_decimal = pricing_service.convert_currency(
            Decimal(total_price_rub),
            gateway_currency,
            usd_rate,
            eur_rate,
            stars_rate,
        )
        
        # Возвращаем цены в базовых единицах валюты (не центы)
        # для согласованности с payment_method_getter
        payment_methods.append({
            "gateway_type": gateway.type,
            "price": format_price(converted_total_decimal, gateway_currency),
            "original_price": format_price(converted_original_decimal, gateway_currency),
            "has_discount": 1 if has_discount else 0,
            "discount_percent": price_details.discount_percent,
        })
    
    # Формируем текст типа покупки
    duration_type_text = "до конца месяца подписки" if duration_type == "month" else "до конца подписки"
    
    return {
        # Данные пользователя
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "referral_code": user.referral_code,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "balance": display_balance,
        "referral_balance": referral_balance,
        "is_balance_enabled": 1 if is_balance_enabled else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,
        # Данные подписки
        "plan_name": subscription.plan.name if subscription else "",
        "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit) if subscription else "",
        "device_limit": i18n_format_device_limit(subscription.device_limit) if subscription else "",
        "device_limit_number": device_limit_number,
        "device_limit_bonus": device_limit_bonus,
        "extra_devices": extra_devices,
        "expire_time": i18n_format_expire_time(subscription.expire_at) if subscription else "",
        # Данные покупки (со скидкой)
        "device_count": device_count,
        "duration_days": duration_days,
        "duration_type": duration_type,
        "duration_type_text": duration_type_text,
        "total_price": format_price(total_price, currency),
        "original_price": format_price(original_price, currency),
        "payment_methods": payment_methods,
    }


@inject
async def add_device_confirm_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    referral_service: FromDishka[ReferralService],
    settings_service: FromDishka[SettingsService],
    pricing_service: FromDishka[PricingService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна подтверждения покупки устройств."""
    from decimal import Decimal
    
    # Получаем данные из dialog_data
    device_count = dialog_manager.dialog_data.get("device_count", 1)
    selected_method = dialog_manager.dialog_data.get("selected_payment_method")
    duration_type = dialog_manager.dialog_data.get("duration_type", "full")
    duration_days = dialog_manager.dialog_data.get("duration_days", 30)
    
    # Получаем уже рассчитанную цену из dialog_data
    device_price_rub = dialog_manager.dialog_data.get("calculated_price")
    
    if device_price_rub is None:
        from src.core.utils.pricing import (
            calculate_device_price_until_subscription_end,
            calculate_device_price_until_month_end,
            MIN_EXTRA_DEVICE_DAYS,
        )
        
        device_price_monthly = await settings_service.get_extra_device_price()
        
        if user.current_subscription:
            if duration_type == "month":
                price_per_device, duration_days = calculate_device_price_until_month_end(
                    monthly_price=device_price_monthly,
                    subscription_expire_at=user.current_subscription.expire_at,
                    min_days=MIN_EXTRA_DEVICE_DAYS,
                )
            else:
                price_per_device, duration_days = calculate_device_price_until_subscription_end(
                    monthly_price=device_price_monthly,
                    subscription_expire_at=user.current_subscription.expire_at,
                    min_days=MIN_EXTRA_DEVICE_DAYS,
                )
            device_price_rub = price_per_device * device_count
        else:
            device_price_rub = device_price_monthly * device_count
    
    # Определяем валюту в зависимости от выбранного метода оплаты
    if selected_method:
        currency = Currency.from_gateway_type(selected_method)
    else:
        currency = await settings_service.get_default_currency()
    
    # Получаем курсы валют для конвертации
    settings = await settings_service.get()
    rates = settings.features.currency_rates
    usd_rate = rates.usd_rate
    eur_rate = rates.eur_rate
    stars_rate = rates.stars_rate
    
    # Форматируем название способа оплаты
    if selected_method == PaymentGatewayType.BALANCE:
        selected_method_formatted = "С баланса"
    elif selected_method == PaymentGatewayType.YOOMONEY:
        selected_method_formatted = "💳 Банковская карта"
    elif selected_method == PaymentGatewayType.CRYPTOMUS:
        selected_method_formatted = "₿ Cryptomus"
    elif selected_method == PaymentGatewayType.TELEGRAM_STARS:
        selected_method_formatted = "⭐ Телеграм"
    else:
        selected_method_formatted = selected_method.value if selected_method else "N/A"
    
    # Получаем реферальный баланс
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )

    # Получаем глобальную скидку
    global_discount = await settings_service.get_global_discount_settings()

    # Вычисляем скидку пользователя
    from datetime import datetime, timezone
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    # Используем PricingService для расчета цены с учетом глобальной скидки
    original_price_rub = device_price_rub
    price_details = pricing_service.calculate(
        user=user,
        price=Decimal(original_price_rub),
        currency=Currency.RUB,
        global_discount=global_discount,
        context="extra_devices",
    )

    # Вычисляем итоговую цену за все устройства (в рублях)
    total_price_rub_amount = int(price_details.final_amount)
    original_price_rub_amount = int(price_details.original_amount)
    
    # Конвертируем цену в валюту выбранного способа оплаты
    # Результат convert_currency в целевой валюте (Decimal)
    original_price_decimal = pricing_service.convert_currency(
        Decimal(original_price_rub_amount),
        currency,
        usd_rate,
        eur_rate,
        stars_rate,
    )
    total_price_decimal = pricing_service.convert_currency(
        Decimal(total_price_rub_amount),
        currency,
        usd_rate,
        eur_rate,
        stars_rate,
    )
    # Keep Decimal for proper fractional display (USD supports cents)
    original_price = original_price_decimal
    total_price = total_price_decimal
    has_discount = price_details.discount_percent > 0

    # Флаг для условного отображения баланса (показываем только при оплате с баланса)
    is_balance_payment = 1 if selected_method == PaymentGatewayType.BALANCE else 0

    # Проверяем, включен ли функционал баланса
    is_balance_enabled = await settings_service.is_balance_enabled()
    
    # Проверяем режим баланса (раздельный или объединённый)
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    # Вычисляем отображаемый баланс
    display_balance = get_display_balance(user.balance, referral_balance, is_balance_combined)
    
    # Вычисляем лимиты устройств
    subscription = user.current_subscription
    extra_devices = subscription.extra_devices or 0 if subscription else 0
    # device_limit_number - это лимит из тарифного плана
    plan_device_limit = subscription.plan.device_limit if subscription and subscription.plan and subscription.plan.device_limit > 0 else 0
    device_limit_number = plan_device_limit if plan_device_limit > 0 else (subscription.device_limit if subscription else 0)
    # device_limit_bonus - добавлено админом (общий лимит - план - купленные)
    device_limit_bonus = max(0, subscription.device_limit - plan_device_limit - extra_devices) if subscription and plan_device_limit > 0 else 0
    
    # Вычисляем баланс после оплаты (если баланс) - для баланса нужен int
    if selected_method == PaymentGatewayType.BALANCE:
        new_balance = display_balance - int(total_price)
    else:
        new_balance = display_balance
    
    # Формируем текст типа покупки
    duration_type_text = "до конца месяца подписки" if duration_type == "month" else "до конца подписки"
    
    return {
        # Заголовок
        "title": "🛒 Подтверждение покупки",
        # Данные пользователя
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "referral_code": user.referral_code,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "balance": format_price(display_balance, Currency.RUB),
        "new_balance": format_price(new_balance, Currency.RUB),
        "referral_balance": referral_balance,
        "is_balance_enabled": 1 if is_balance_enabled else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,
        # Данные подписки
        "plan_name": subscription.plan.name if subscription else "",
        "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit) if subscription else "",
        "device_limit": i18n_format_device_limit(subscription.device_limit) if subscription else "",
        "device_limit_number": device_limit_number,
        "device_limit_bonus": device_limit_bonus,
        "extra_devices": extra_devices,
        "expire_time": i18n_format_expire_time(subscription.expire_at) if subscription else "",
        # Данные покупки (со скидкой)
        "device_count": device_count,
        "duration_days": duration_days,
        "duration_type": duration_type,
        "duration_type_text": duration_type_text,
        "total_price": format_price(total_price, currency),
        "original_price": format_price(original_price, currency),
        "selected_method": selected_method_formatted,
        "currency": currency.symbol,
        "is_balance_payment": is_balance_payment,
        "has_discount": 1 if has_discount else 0,
        # Данные о платеже (если не баланс)
        "payment_url": dialog_manager.dialog_data.get("payment_url", "") if selected_method != PaymentGatewayType.BALANCE else "",
    }


@inject
async def devices_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    remnawave_service: FromDishka[RemnawaveService],
    referral_service: FromDishka[ReferralService],
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна управления устройствами в меню подписки."""
    from datetime import datetime, timezone
    
    if not user.current_subscription:
        raise ValueError(f"Current subscription for user '{user.telegram_id}' not found")

    devices = await remnawave_service.get_devices_user(user)

    formatted_devices = [
        {
            "short_hwid": device.hwid[:32],
            "hwid": device.hwid,
            "platform": device.platform,
            "device_model": device.device_model,
            "user_agent": device.user_agent,
        }
        for device in devices
    ]

    dialog_manager.dialog_data["hwid_map"] = formatted_devices
    
    # Получаем текущий и максимальный лимит устройств
    subscription = user.current_subscription
    current_count = len(devices)
    max_count = subscription.device_limit
    base_device_limit = subscription.plan.device_limit
    
    # Докупленные устройства
    extra_devices = getattr(subscription, 'extra_devices', 0) or 0
    
    # Определяем, является ли подписка пробной или реферальной
    plan_name_lower = subscription.plan.name.lower() if subscription.plan else ""
    is_trial_or_referral = (
        subscription.is_trial 
        or "пробн" in plan_name_lower 
        or "реферал" in plan_name_lower
    )
    
    # Проверяем включён ли функционал доп. устройств
    is_extra_devices_enabled = await settings_service.is_extra_devices_enabled()
    
    # Проверяем, можно ли добавить устройство
    # Запрещаем для пробных и реферальных подписок
    # Запрещаем если функционал доп. устройств отключён
    can_add_device = (
        max_count is not None 
        and max_count > 0 
        and not is_trial_or_referral
        and is_extra_devices_enabled
    )

    # Данные профиля
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )
    
    # Вычисляем скидку пользователя
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0
    
    # Режим баланса
    is_balance_combined = await settings_service.is_balance_combined()
    
    # Вычисляем отображаемый баланс
    display_balance = get_display_balance(
        user.balance,
        referral_balance,
        is_balance_combined,
    )

    return {
        # Данные устройств
        "current_count": current_count,
        "max_count": i18n_format_device_limit(max_count),
        "devices": formatted_devices,
        "devices_empty": len(devices) == 0,
        "can_add_device": can_add_device,
        # Данные профиля
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "referral_code": user.referral_code,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "referral_balance": referral_balance,
        "balance": display_balance,
        "is_balance_enabled": 1 if await settings_service.is_balance_enabled() else 0,
        "is_balance_separate": 1 if not is_balance_combined else 0,
        # Данные подписки
        "is_trial": 1 if subscription.is_trial else 0,
        "plan_name": subscription.plan.name if subscription.plan else "Unknown",
        "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
        "device_limit": i18n_format_device_limit(max_count),
        "device_limit_number": base_device_limit,
        "device_limit_bonus": max(0, max_count - base_device_limit - extra_devices) if base_device_limit > 0 else 0,
        "extra_devices": extra_devices,
        "expire_time": i18n_format_expire_time(subscription.expire_at),
    }


@inject
async def add_device_success_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    user_service: FromDishka[UserService],
    referral_service: FromDishka[ReferralService],
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна успешного добавления устройств."""
    # Очищаем кэш и получаем свежие данные пользователя из БД
    await user_service.clear_user_cache(user.telegram_id)
    fresh_user = await user_service.get(user.telegram_id)
    if not fresh_user:
        fresh_user = user
    
    # Получаем данные из dialog_data
    device_count = dialog_manager.dialog_data.get("device_count", 1)
    
    # Получаем реферальный баланс
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=fresh_user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )

    # Вычисляем скидку пользователя
    from datetime import datetime, timezone
    purchase_disc = fresh_user.purchase_discount if fresh_user.purchase_discount is not None else 0
    personal_disc = fresh_user.personal_discount if fresh_user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and fresh_user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if fresh_user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = fresh_user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    # Проверяем, включен ли функционал баланса
    is_balance_enabled = await settings_service.is_balance_enabled()
    
    # Проверяем режим баланса (раздельный или объединённый)
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    # Вычисляем лимиты устройств (получаем обновленные данные)
    subscription = fresh_user.current_subscription
    extra_devices = subscription.extra_devices or 0 if subscription else 0
    device_limit_number = (subscription.plan.device_limit) if subscription else 0
    
    # Определяем склонение слова "устройство"
    device_count_word = "устройство" if device_count % 10 == 1 and device_count != 11 else \
                       "устройства" if device_count % 10 in [2, 3, 4] and device_count not in [12, 13, 14] else \
                       "устройств"
    
    # Вычисляем отображаемый баланс
    display_balance = get_display_balance(
        fresh_user.balance,
        referral_balance,
        is_balance_combined,
    )
    
    return {
        # Данные пользователя
        "user_id": str(fresh_user.telegram_id),
        "user_name": fresh_user.name,
        "referral_code": fresh_user.referral_code,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "balance": display_balance,
        "referral_balance": referral_balance,
        "is_balance_enabled": 1 if is_balance_enabled else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,
        # Данные подписки
        "plan_name": subscription.plan.name if subscription else "",
        "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit) if subscription else "",
        "device_limit": i18n_format_device_limit(subscription.device_limit) if subscription else "",
        "device_limit_number": device_limit_number,
        "device_limit_bonus": max(0, subscription.device_limit - device_limit_number - extra_devices) if subscription and device_limit_number > 0 else 0,
        "extra_devices": extra_devices,
        "expire_time": i18n_format_expire_time(subscription.expire_at) if subscription else "",
        # Данные покупки
        "device_count": device_count,
        "device_count_word": device_count_word,
    }


@inject
async def extra_devices_list_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    extra_device_service: FromDishka[ExtraDeviceService],
    referral_service: FromDishka[ReferralService],
    settings_service: FromDishka[SettingsService],
    pricing_service: FromDishka[PricingService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для списка купленных дополнительных устройств."""
    from datetime import datetime, timezone
    
    if not user.current_subscription:
        raise ValueError(f"Current subscription for user '{user.telegram_id}' not found")
    
    subscription = user.current_subscription
    
    # Получаем активные покупки дополнительных устройств
    purchases = await extra_device_service.get_active_by_subscription(subscription.id)
    
    # Получаем курсы валют для конвертации
    settings = await settings_service.get()
    rates = settings.features.currency_rates
    usd_rate = rates.usd_rate
    eur_rate = rates.eur_rate
    stars_rate = rates.stars_rate
    
    # Получаем валюту по умолчанию
    default_currency = await settings_service.get_default_currency()
    
    # Форматируем для отображения
    formatted_purchases = []
    for p in purchases:
        # Конвертируем цену в валюту по умолчанию
        converted_price = int(pricing_service.convert_currency(
            Decimal(p.price),
            default_currency,
            usd_rate,
            eur_rate,
            stars_rate,
        ))
        formatted_purchases.append({
            "id": p.id,
            "device_count": p.device_count,
            "price": format_price(converted_price, default_currency),
            "auto_renew": p.auto_renew,
            "expires_at": i18n_format_expire_time(p.expires_at),
            "days_remaining": p.days_remaining,
        })
    
    # Сохраняем в dialog_data для использования в обработчиках
    dialog_manager.dialog_data["extra_device_purchases"] = [
        {"id": p.id, "device_count": p.device_count}
        for p in purchases
    ]
    
    # Общая месячная стоимость дополнительных устройств
    # Используем цену из настроек * количество активных устройств
    total_extra_devices = await extra_device_service.get_total_active_devices(subscription.id)
    device_price_monthly = await settings_service.get_extra_device_price()
    total_monthly_cost_rub = device_price_monthly * total_extra_devices
    total_monthly_cost = int(pricing_service.convert_currency(
        Decimal(total_monthly_cost_rub),
        default_currency,
        usd_rate,
        eur_rate,
        stars_rate,
    ))  # Конвертируем в валюту по умолчанию
    
    # Данные профиля
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )
    
    # Вычисляем скидку пользователя
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0
    
    # Данные подписки
    extra_devices = subscription.extra_devices or 0
    device_limit_number = subscription.plan.device_limit if subscription.plan else 0
    # device_limit_bonus - устройства добавленные администратором через панель (не extra_devices)
    device_limit_bonus = max(0, subscription.device_limit - device_limit_number - extra_devices) if device_limit_number > 0 else 0
    
    # Режим баланса
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    return {
        # Список покупок
        "purchases": formatted_purchases,
        "purchases_empty": len(formatted_purchases) == 0,
        "total_monthly_cost": format_price(total_monthly_cost, default_currency),
        "total_extra_devices": total_extra_devices,
        # Данные профиля
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "referral_code": user.referral_code,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "referral_balance": referral_balance,
        "balance": get_display_balance(user.balance, referral_balance, is_balance_combined),
        "is_balance_enabled": 1 if await settings_service.is_balance_enabled() else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,
        # Данные подписки
        "is_trial": 1 if subscription.is_trial else 0,
        "plan_name": subscription.plan.name if subscription.plan else "Unknown",
        "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
        "device_limit": i18n_format_device_limit(subscription.device_limit),
        "device_limit_number": device_limit_number,
        "device_limit_bonus": device_limit_bonus,
        "extra_devices": extra_devices,
        "expire_time": i18n_format_expire_time(subscription.expire_at),
        # Флаги для кнопок
        "can_add_device": subscription.is_active and subscription.has_devices_limit,
    }


@inject
async def extra_device_manage_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    extra_device_service: FromDishka[ExtraDeviceService],
    referral_service: FromDishka[ReferralService],
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для управления конкретной покупкой дополнительных устройств."""
    from datetime import datetime, timezone
    
    purchase_id = dialog_manager.dialog_data.get("selected_purchase_id")
    if not purchase_id:
        raise ValueError("No purchase_id in dialog_data")
    
    purchase = await extra_device_service.get(purchase_id)
    if not purchase:
        raise ValueError(f"Purchase '{purchase_id}' not found")
    
    subscription = user.current_subscription
    if not subscription:
        raise ValueError(f"Current subscription for user '{user.telegram_id}' not found")
    
    # Данные профиля
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )
    
    # Вычисляем скидку пользователя
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary_discount = False
    is_permanent_discount = False

    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary_discount = True

    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0
    
    # Данные подписки
    extra_devices = subscription.extra_devices or 0
    device_limit_number = subscription.plan.device_limit if subscription.plan else 0
    
    # Режим баланса
    is_balance_combined = await settings_service.is_balance_combined()
    
    return {
        # Данные покупки
        "purchase_id": purchase.id,
        "purchase_device_count": purchase.device_count,
        "purchase_price": purchase.price,
        "purchase_auto_renew": 1 if purchase.auto_renew else 0,
        "purchase_expires_at": i18n_format_expire_time(purchase.expires_at),
        "purchase_days_remaining": purchase.days_remaining,
        # Данные профиля
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "referral_code": user.referral_code,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "referral_balance": referral_balance,
        "balance": get_display_balance(user.balance, referral_balance, is_balance_combined),
        "is_balance_enabled": 1 if await settings_service.is_balance_enabled() else 0,
        # Данные подписки
        "is_trial": 1 if subscription.is_trial else 0,
        "plan_name": subscription.plan.name if subscription.plan else "Unknown",
        "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
        "device_limit": i18n_format_device_limit(subscription.device_limit),
        "device_limit_number": device_limit_number,
        "device_limit_bonus": max(0, subscription.device_limit - device_limit_number) if device_limit_number > 0 else 0,
        "extra_devices": extra_devices,
        "expire_time": i18n_format_expire_time(subscription.expire_at),
    }


@inject
async def add_device_payment_link_getter(
    dialog_manager: DialogManager,
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для экрана ссылки платежа доп. устройств."""
    payment_url = dialog_manager.dialog_data.get("payment_url", "")
    
    return {
        "payment_url": payment_url,
    }
