import traceback
from decimal import Decimal
from typing import Optional, TypedDict, cast

from aiogram.types import CallbackQuery
from aiogram.utils.formatting import Text
from aiogram_dialog import DialogManager, ShowMode, StartMode, SubManager
from aiogram_dialog.widgets.kbd import Button, Select
from aiogram_dialog.widgets.input import MessageInput
from aiogram.types import Message
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from fluentogram import TranslatorRunner
from loguru import logger

from src.bot.keyboards import get_user_keyboard
from src.bot.states import Subscription, MainMenu
from src.core.constants import PURCHASE_PREFIX, USER_KEY
from src.core.enums import Currency, PaymentGatewayType, PurchaseType, ReferralLevel, ReferralRewardType, TransactionStatus
from src.core.utils.adapter import DialogDataAdapter
from src.core.utils.formatters import format_user_log as log, i18n_format_bytes_to_unit, i18n_format_traffic_limit
from src.core.utils.message_payload import MessagePayload
from src.infrastructure.database.models.dto import PlanDto, PlanSnapshotDto, UserDto, TransactionDto
from src.services.notification import NotificationService
from src.services.payment_gateway import PaymentGatewayService
from src.services.plan import PlanService
from src.services.pricing import PricingService
from src.services.promocode import PromocodeService
from src.services.settings import SettingsService
from src.services.subscription import SubscriptionService
from src.services.transaction import TransactionService
from src.services.user import UserService
from src.services.referral import ReferralService
from src.services.remnawave import RemnawaveService
from src.services.extra_device import ExtraDeviceService

PAYMENT_CACHE_KEY = "payment_cache"
CURRENT_DURATION_KEY = "selected_duration"
CURRENT_METHOD_KEY = "selected_payment_method"


class CachedPaymentData(TypedDict):
    payment_id: str
    payment_url: Optional[str]
    final_pricing: str
    base_subscription_price: int  # Базовая цена подписки БЕЗ доп. устройств
    extra_devices_cost: int  # Стоимость доп. устройств


def _get_cache_key(duration: int, gateway_type: PaymentGatewayType) -> str:
    return f"{duration}:{gateway_type.value}"


def _load_payment_data(dialog_manager: DialogManager) -> dict[str, CachedPaymentData]:
    if PAYMENT_CACHE_KEY not in dialog_manager.dialog_data:
        dialog_manager.dialog_data[PAYMENT_CACHE_KEY] = {}
    return cast(dict[str, CachedPaymentData], dialog_manager.dialog_data[PAYMENT_CACHE_KEY])


def _save_payment_data(dialog_manager: DialogManager, payment_data: CachedPaymentData) -> None:
    dialog_manager.dialog_data["payment_id"] = payment_data["payment_id"]
    dialog_manager.dialog_data["payment_url"] = payment_data["payment_url"]
    dialog_manager.dialog_data["final_pricing"] = payment_data["final_pricing"]
    dialog_manager.dialog_data["base_subscription_price"] = payment_data["base_subscription_price"]
    dialog_manager.dialog_data["extra_devices_cost"] = payment_data["extra_devices_cost"]


async def _create_payment_and_get_data(
    dialog_manager: DialogManager,
    plan: PlanDto,
    duration_days: int,
    gateway_type: PaymentGatewayType,
    payment_gateway_service: PaymentGatewayService,
    notification_service: NotificationService,
    pricing_service: PricingService,
    extra_device_service: FromDishka[ExtraDeviceService],
    settings_service: FromDishka[SettingsService],
) -> Optional[CachedPaymentData]:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    duration = plan.get_duration(duration_days)
    payment_gateway = await payment_gateway_service.get_by_type(gateway_type)
    purchase_type: PurchaseType = dialog_manager.dialog_data["purchase_type"]

    if not duration or not payment_gateway:
        logger.error(f"{log(user)} Failed to find duration or gateway for payment creation")
        return None

    transaction_plan = PlanSnapshotDto.from_plan(plan, duration.days)
    
    # Получаем курсы валют для конвертации
    settings = await settings_service.get()
    rates = settings.features.currency_rates
    base_price = duration.get_price(
        payment_gateway.currency, 
        rates.usd_rate, 
        rates.eur_rate, 
        rates.stars_rate
    )
    
    # Получаем настройки глобальной скидки
    global_discount = await settings_service.get_global_discount_settings()
    
    # Добавляем стоимость доп. устройств
    # Используем цену из настроек * количество активных устройств
    extra_devices_cost = 0
    extra_devices_cost_rub = 0  # Для хранения стоимости в рублях
    is_extra_devices_one_time = await settings_service.is_extra_devices_one_time()
    
    if user.current_subscription and not is_extra_devices_one_time:
        active_extra_devices = await extra_device_service.get_total_active_devices(user.current_subscription.id)
        if active_extra_devices > 0:
            device_price_monthly = await settings_service.get_extra_device_price()
            extra_devices_monthly_cost = device_price_monthly * active_extra_devices
            months = duration.days // 30  # Используем целочисленное деление
            extra_devices_cost_rub = extra_devices_monthly_cost * months
            
            # Конвертируем стоимость доп. устройств в валюту шлюза
            if extra_devices_cost_rub > 0:
                extra_devices_cost = pricing_service.convert_currency(
                    Decimal(extra_devices_cost_rub),
                    payment_gateway.currency,
                    rates.usd_rate,
                    rates.eur_rate,
                    rates.stars_rate,
                )
    
    # Итоговая цена = базовая подписка + доп. устройства (оба в валюте шлюза)
    total_price = base_price + Decimal(extra_devices_cost)
    pricing = pricing_service.calculate(user, total_price, payment_gateway.currency, global_discount, context="subscription")

    try:
        result = await payment_gateway_service.create_payment(
            user=user,
            plan=transaction_plan,
            pricing=pricing,
            purchase_type=purchase_type,
            gateway_type=gateway_type,
        )

        return CachedPaymentData(
            payment_id=str(result.id),
            payment_url=result.url,
            final_pricing=pricing.model_dump_json(),
            base_subscription_price=float(base_price),  # В валюте шлюза
            extra_devices_cost=float(extra_devices_cost),  # В валюте шлюза
        )

    except Exception as exception:
        logger.error(f"{log(user)} Failed to create payment: {exception}")
        traceback_str = traceback.format_exc()
        error_type_name = type(exception).__name__
        error_message = Text(str(exception)[:512])

        await notification_service.error_notify(
            error_id=user.telegram_id,
            traceback_str=traceback_str,
            payload=MessagePayload.not_deleted(
                i18n_key="ntf-event-error",
                i18n_kwargs={
                    "user": True,
                    "user_id": str(user.telegram_id),
                    "user_name": user.name,
                    "username": user.username or False,
                    "error": f"{error_type_name}: Failed to create payment "
                    + f"check due to error: {error_message.as_html()}",
                },
                reply_markup=get_user_keyboard(user.telegram_id),
            ),
        )

        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-subscription-payment-creation-failed"),
        )
        return None


@inject
async def on_purchase_type_select(
    purchase_type: PurchaseType,
    dialog_manager: DialogManager,
    plan_service: FromDishka[PlanService],
    payment_gateway_service: FromDishka[PaymentGatewayService],
    notification_service: FromDishka[NotificationService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    plans: list[PlanDto] = await plan_service.get_available_plans(user)
    gateways = await payment_gateway_service.filter_active()
    dialog_manager.dialog_data["purchase_type"] = purchase_type
    dialog_manager.dialog_data.pop(CURRENT_DURATION_KEY, None)

    if not plans:
        logger.warning(f"{log(user)} No available subscription plans")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-subscription-plans-not-available", auto_delete_after=5),
        )
        return

    if not gateways:
        logger.warning(f"{log(user)} No active payment gateways")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-subscription-gateways-not-available"),
        )
        return

    adapter = DialogDataAdapter(dialog_manager)

    if purchase_type == PurchaseType.RENEW:
        if user.current_subscription:
            matched_plan = SubscriptionService.find_matching_plan(
                plan_snapshot=user.current_subscription.plan,
                plans=plans,
            )
            logger.debug(f"Matched plan for renewal: '{matched_plan}'")

            if matched_plan:
                adapter.save(matched_plan)
                dialog_manager.dialog_data["only_single_plan"] = True
                await dialog_manager.switch_to(state=Subscription.DURATION)
                return
            else:
                logger.warning(f"{log(user)} Tried to renew, but no matching plan found")
                await notification_service.notify_user(
                    user=user,
                    payload=MessagePayload(i18n_key="ntf-subscription-renew-plan-unavailable"),
                )
                return

    # Для смены подписки всегда показываем список планов, даже если план один
    if len(plans) == 1 and purchase_type != PurchaseType.CHANGE:
        logger.info(f"{log(user)} Auto-selected single plan '{plans[0].id}'")
        adapter.save(plans[0])
        dialog_manager.dialog_data["only_single_plan"] = True
        await dialog_manager.switch_to(state=Subscription.DURATION)
        return

    dialog_manager.dialog_data["only_single_plan"] = False
    await dialog_manager.switch_to(state=Subscription.PLANS)


@inject
async def on_subscription_plans(  # noqa: C901
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    plan_service: FromDishka[PlanService],
    payment_gateway_service: FromDishka[PaymentGatewayService],
    notification_service: FromDishka[NotificationService],
    pricing_service: FromDishka[PricingService],
    settings_service: FromDishka[SettingsService],
    extra_device_service: FromDishka[ExtraDeviceService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Opened subscription plans menu")

    plans: list[PlanDto] = await plan_service.get_available_plans(user)
    gateways = await payment_gateway_service.filter_active()

    if not callback.data:
        raise ValueError("Callback data is empty")

    purchase_type = PurchaseType(callback.data.removeprefix(PURCHASE_PREFIX))
    dialog_manager.dialog_data["purchase_type"] = purchase_type

    dialog_manager.dialog_data.pop(CURRENT_DURATION_KEY, None)

    if not plans:
        logger.warning(f"{log(user)} No available subscription plans")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-subscription-plans-not-available", auto_delete_after=5),
        )
        return

    if not gateways:
        logger.warning(f"{log(user)} No active payment gateways")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-subscription-gateways-not-available"),
        )
        return

    adapter = DialogDataAdapter(dialog_manager)

    if purchase_type == PurchaseType.RENEW:
        if user.current_subscription:
            matched_plan = SubscriptionService.find_matching_plan(
                plan_snapshot=user.current_subscription.plan,
                plans=plans,
            )
            logger.debug(f"Matched plan for renewal: '{matched_plan}'")

            if matched_plan:
                adapter.save(matched_plan)
                dialog_manager.dialog_data["only_single_plan"] = True
                await dialog_manager.switch_to(state=Subscription.DURATION)
                return
            else:
                logger.warning(f"{log(user)} Tried to renew, but no matching plan found")
                await notification_service.notify_user(
                    user=user,
                    payload=MessagePayload(i18n_key="ntf-subscription-renew-plan-unavailable"),
                )
                return

    # Для изменения подписки исключаем текущий активный план из списка
    if purchase_type == PurchaseType.CHANGE and user.current_subscription:
        current_plan_id = user.current_subscription.plan.id
        plans = [plan for plan in plans if plan.id != current_plan_id]
        
        if not plans:
            logger.warning(f"{log(user)} No available plans for subscription change")
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(i18n_key="ntf-subscription-change-plans-not-available"),
            )
            return

    # Для смены подписки всегда показываем список планов, даже если план один
    if len(plans) == 1 and purchase_type != PurchaseType.CHANGE:
        logger.info(f"{log(user)} Auto-selected single plan '{plans[0].id}'")
        adapter.save(plans[0])
        dialog_manager.dialog_data["only_single_plan"] = True

        if len(plans[0].durations) == 1:
            logger.info(f"{log(user)} Auto-selected duration '{plans[0].durations[0].days}'")
            dialog_manager.dialog_data["selected_duration"] = plans[0].durations[0].days
            dialog_manager.dialog_data["only_single_duration"] = True

            if len(gateways) == 1:
                logger.info(f"{log(user)} Auto-selected payment method '{gateways[0].type}'")
                dialog_manager.dialog_data["selected_payment_method"] = gateways[0].type
                dialog_manager.dialog_data["only_single_payment_method"] = True

                payment_data = await _create_payment_and_get_data(
                    dialog_manager=dialog_manager,
                    plan=plans[0],
                    duration_days=plans[0].durations[0].days,
                    gateway_type=gateways[0].type,
                    payment_gateway_service=payment_gateway_service,
                    notification_service=notification_service,
                    pricing_service=pricing_service,
                    extra_device_service=extra_device_service,
                    settings_service=settings_service,
                )

                if payment_data:
                    _save_payment_data(dialog_manager, payment_data)
                    await dialog_manager.switch_to(state=Subscription.CONFIRM)
                else:
                    # Payment creation failed, go to payment method selection
                    logger.warning(f"{log(user)} Payment creation failed, redirecting to payment method selection")
                    await dialog_manager.switch_to(state=Subscription.PAYMENT_METHOD)
                return

            await dialog_manager.switch_to(state=Subscription.PAYMENT_METHOD)
            return

        await dialog_manager.switch_to(state=Subscription.DURATION)
        return

    dialog_manager.dialog_data["only_single_plan"] = False
    dialog_manager.dialog_data["only_single_duration"] = False
    await dialog_manager.switch_to(state=Subscription.PLANS)


@inject
async def on_plan_select(
    callback: CallbackQuery,
    widget: Select,
    dialog_manager: DialogManager,
    selected_plan: int,
    plan_service: FromDishka[PlanService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    plan = await plan_service.get(plan_id=selected_plan)

    if not plan:
        raise ValueError(f"Selected plan '{selected_plan}' not found")

    logger.info(f"{log(user)} Selected plan '{plan.id}'")
    adapter = DialogDataAdapter(dialog_manager)
    adapter.save(plan)

    dialog_manager.dialog_data.pop(PAYMENT_CACHE_KEY, None)
    dialog_manager.dialog_data.pop(CURRENT_DURATION_KEY, None)
    dialog_manager.dialog_data.pop(CURRENT_METHOD_KEY, None)

    if len(plan.durations) == 1:
        logger.info(f"{log(user)} Auto-selected single duration '{plan.durations[0].days}'")
        dialog_manager.dialog_data["only_single_duration"] = True
        await on_duration_select(callback, widget, dialog_manager, plan.durations[0].days)
        return

    await dialog_manager.switch_to(state=Subscription.DURATION)


@inject
async def on_duration_select(
    callback: CallbackQuery,
    widget: Select,
    dialog_manager: DialogManager,
    selected_duration: int,
    settings_service: FromDishka[SettingsService],
    payment_gateway_service: FromDishka[PaymentGatewayService],
    notification_service: FromDishka[NotificationService],
    pricing_service: FromDishka[PricingService],
    extra_device_service: FromDishka[ExtraDeviceService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Selected subscription duration '{selected_duration}' days")
    dialog_manager.dialog_data[CURRENT_DURATION_KEY] = selected_duration

    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    gateways = await payment_gateway_service.filter_active()
    currency = await settings_service.get_default_currency()
    global_discount = await settings_service.get_global_discount_settings()
    
    # Получаем курсы валют для конвертации
    settings = await settings_service.get()
    rates = settings.features.currency_rates
    
    price = pricing_service.calculate(
        user=user,
        price=plan.get_duration(selected_duration).get_price(
            currency, rates.usd_rate, rates.eur_rate, rates.stars_rate
        ),  # type: ignore[union-attr]
        currency=currency,
        global_discount=global_discount,
        context="subscription",
    )
    dialog_manager.dialog_data["is_free"] = price.is_free

    if len(gateways) == 1 or price.is_free:
        selected_payment_method = gateways[0].type
        dialog_manager.dialog_data[CURRENT_METHOD_KEY] = selected_payment_method

        cache = _load_payment_data(dialog_manager)
        cache_key = _get_cache_key(selected_duration, selected_payment_method)

        if cache_key in cache:
            logger.info(f"{log(user)} Re-selected same duration and single gateway")
            _save_payment_data(dialog_manager, cache[cache_key])
            await dialog_manager.switch_to(state=Subscription.CONFIRM)
            return

        logger.info(f"{log(user)} Auto-selected single gateway '{selected_payment_method}'")

        payment_data = await _create_payment_and_get_data(
            dialog_manager=dialog_manager,
            plan=plan,
            duration_days=selected_duration,
            gateway_type=selected_payment_method,
            payment_gateway_service=payment_gateway_service,
            notification_service=notification_service,
            pricing_service=pricing_service,
            extra_device_service=extra_device_service,
            settings_service=settings_service,
        )

        if payment_data:
            cache[cache_key] = payment_data
            _save_payment_data(dialog_manager, payment_data)
            await dialog_manager.switch_to(state=Subscription.CONFIRM)
            return

    dialog_manager.dialog_data.pop(CURRENT_METHOD_KEY, None)
    await dialog_manager.switch_to(state=Subscription.PAYMENT_METHOD)


@inject
async def on_payment_method_select(
    callback: CallbackQuery,
    widget: Select,
    dialog_manager: DialogManager,
    selected_payment_method: PaymentGatewayType,
    payment_gateway_service: FromDishka[PaymentGatewayService],
    notification_service: FromDishka[NotificationService],
    pricing_service: FromDishka[PricingService],
    user_service: FromDishka[UserService],
    settings_service: FromDishka[SettingsService],
    extra_device_service: FromDishka[ExtraDeviceService],
    referral_service: FromDishka[ReferralService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Selected payment method '{selected_payment_method}'")

    selected_duration = dialog_manager.dialog_data[CURRENT_DURATION_KEY]
    dialog_manager.dialog_data[CURRENT_METHOD_KEY] = selected_payment_method
    
    # Handle balance payment - go to confirmation page
    if selected_payment_method == PaymentGatewayType.BALANCE:
        adapter = DialogDataAdapter(dialog_manager)
        plan = adapter.load(PlanDto)

        if not plan:
            raise ValueError("PlanDto not found in dialog data")
        
        duration = plan.get_duration(selected_duration)
        if not duration:
            raise ValueError(f"Duration '{selected_duration}' not found in plan '{plan.name}'")
        
        currency = await settings_service.get_default_currency()
        global_discount = await settings_service.get_global_discount_settings()
        
        # Получаем курсы валют для конвертации
        settings = await settings_service.get()
        rates = settings.features.currency_rates
        
        base_price = duration.get_price(currency, rates.usd_rate, rates.eur_rate, rates.stars_rate)
        base_subscription_price = float(base_price)  # Сохраняем цену подписки БЕЗ доп. устройств (в рублях)
        
        # Добавляем стоимость доп. устройств
        # Используем цену из настроек * количество активных устройств
        purchase_type: PurchaseType = dialog_manager.dialog_data["purchase_type"]
        extra_devices_cost = 0
        is_extra_devices_one_time = await settings_service.is_extra_devices_one_time()
        if user.current_subscription and not is_extra_devices_one_time:
            active_extra_devices = await extra_device_service.get_total_active_devices(user.current_subscription.id)
            if active_extra_devices > 0:
                device_price_monthly = await settings_service.get_extra_device_price()
                extra_devices_monthly_cost = device_price_monthly * active_extra_devices
                months = duration.days // 30  # Используем целочисленное деление
                extra_devices_cost = extra_devices_monthly_cost * months
        
        # Итоговая цена = базовая подписка + доп. устройства
        total_price = base_price + Decimal(extra_devices_cost)
        price = pricing_service.calculate(user, total_price, currency, global_discount, context="subscription")
        
        # Check if user still has enough balance
        # В режиме COMBINED учитываем и бонусный баланс
        is_balance_combined = await settings_service.is_balance_combined()
        referral_balance = await referral_service.get_pending_rewards_amount(
            telegram_id=user.telegram_id,
            reward_type=ReferralRewardType.MONEY,
        )
        available_balance = user.balance + referral_balance if is_balance_combined else user.balance
        
        if available_balance < price.final_amount:
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(i18n_key="ntf-subscription-insufficient-balance"),
            )
            return
        
        # Save pricing data for confirm page
        dialog_manager.dialog_data["final_pricing"] = price.model_dump_json()
        dialog_manager.dialog_data["balance_currency"] = currency.symbol
        dialog_manager.dialog_data["base_subscription_price"] = base_subscription_price
        dialog_manager.dialog_data["extra_devices_cost"] = extra_devices_cost
        
        # Go to balance confirmation page
        await dialog_manager.switch_to(state=Subscription.CONFIRM_BALANCE)
        return
    
    cache = _load_payment_data(dialog_manager)
    cache_key = _get_cache_key(selected_duration, selected_payment_method)

    if cache_key in cache:
        logger.info(f"{log(user)} Re-selected same method and duration")
        _save_payment_data(dialog_manager, cache[cache_key])
        # Route to appropriate confirmation page based on payment method
        if selected_payment_method == PaymentGatewayType.YOOMONEY:
            await dialog_manager.switch_to(state=Subscription.CONFIRM_YOOMONEY)
        elif selected_payment_method == PaymentGatewayType.YOOKASSA:
            await dialog_manager.switch_to(state=Subscription.CONFIRM_YOOKASSA)
        else:
            await dialog_manager.switch_to(state=Subscription.CONFIRM)
        return

    logger.info(f"{log(user)} New combination. Creating new payment")

    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")

    payment_data = await _create_payment_and_get_data(
        dialog_manager=dialog_manager,
        plan=plan,
        duration_days=selected_duration,
        gateway_type=selected_payment_method,
        payment_gateway_service=payment_gateway_service,
        notification_service=notification_service,
        pricing_service=pricing_service,
        extra_device_service=extra_device_service,
        settings_service=settings_service,
    )

    if payment_data:
        cache[cache_key] = payment_data
        _save_payment_data(dialog_manager, payment_data)
        
        # Route to appropriate confirmation page based on payment method
        if selected_payment_method == PaymentGatewayType.YOOMONEY:
            await dialog_manager.switch_to(state=Subscription.CONFIRM_YOOMONEY)
        elif selected_payment_method == PaymentGatewayType.YOOKASSA:
            await dialog_manager.switch_to(state=Subscription.CONFIRM_YOOKASSA)
        else:
            await dialog_manager.switch_to(state=Subscription.CONFIRM)
    else:
        # Payment creation failed, stay on payment method selection
        logger.warning(f"{log(user)} Payment creation failed for '{selected_payment_method}', staying on payment method selection")
        await dialog_manager.switch_to(state=Subscription.PAYMENT_METHOD)


@inject
async def on_get_subscription(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    payment_gateway_service: FromDishka[PaymentGatewayService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    payment_id = dialog_manager.dialog_data["payment_id"]
    logger.info(f"{log(user)} Getted free subscription '{payment_id}'")
    await payment_gateway_service.handle_payment_succeeded(payment_id)


@inject
async def on_confirm_balance_payment(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    payment_gateway_service: FromDishka[PaymentGatewayService],
    notification_service: FromDishka[NotificationService],
    pricing_service: FromDishka[PricingService],
    user_service: FromDishka[UserService],
    settings_service: FromDishka[SettingsService],
    extra_device_service: FromDishka[ExtraDeviceService],
    referral_service: FromDishka[ReferralService],
) -> None:
    """Handle confirmation of balance payment."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    logger.info(f"{log(user)} Starting balance payment confirmation")
    
    adapter = DialogDataAdapter(dialog_manager)
    plan = adapter.load(PlanDto)

    if not plan:
        raise ValueError("PlanDto not found in dialog data")
    
    selected_duration = dialog_manager.dialog_data[CURRENT_DURATION_KEY]
    duration = plan.get_duration(selected_duration)
    
    if not duration:
        raise ValueError(f"Duration '{selected_duration}' not found in plan '{plan.name}'")
    
    currency = await settings_service.get_default_currency()
    global_discount = await settings_service.get_global_discount_settings()
    
    # Получаем курсы валют для конвертации
    settings = await settings_service.get()
    rates = settings.features.currency_rates
    
    base_price = duration.get_price(currency, rates.usd_rate, rates.eur_rate, rates.stars_rate)
    
    # Добавляем стоимость доп. устройств
    # Используем цену из настроек * количество активных устройств
    purchase_type: PurchaseType = dialog_manager.dialog_data["purchase_type"]
    is_extra_devices_one_time = await settings_service.is_extra_devices_one_time()
    if user.current_subscription and not is_extra_devices_one_time:
        active_extra_devices = await extra_device_service.get_total_active_devices(user.current_subscription.id)
        if active_extra_devices > 0:
            device_price_monthly = await settings_service.get_extra_device_price()
            extra_devices_monthly_cost = device_price_monthly * active_extra_devices
            months = duration.days // 30  # Используем целочисленное деление
            extra_devices_cost = extra_devices_monthly_cost * months
            base_price = base_price + Decimal(extra_devices_cost)
    
    price = pricing_service.calculate(user, base_price, currency, global_discount, context="subscription")
    
    # Re-check balance (user might have spent it elsewhere)
    fresh_user = await user_service.get(user.telegram_id)
    
    # В режиме COMBINED учитываем и бонусный баланс
    is_balance_combined = await settings_service.is_balance_combined()
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )
    available_balance = fresh_user.balance + referral_balance if is_balance_combined else fresh_user.balance
    
    if not fresh_user or available_balance < price.final_amount:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-subscription-insufficient-balance"),
        )
        return
    
    transaction_plan = PlanSnapshotDto.from_plan(plan, duration.days)
    
    try:
        # Create balance payment transaction
        result = await payment_gateway_service.create_balance_payment(
            user=fresh_user,
            plan=transaction_plan,
            pricing=price,
            purchase_type=purchase_type,
        )
        
        # Deduct from balance (with COMBINED mode support)
        from_main, from_bonus = await user_service.subtract_from_combined_balance(
            user=fresh_user,
            amount=int(price.final_amount),
            referral_balance=referral_balance,
            is_combined=is_balance_combined,
        )
        
        # Если списали с бонусного, отмечаем награды как использованные
        if from_bonus > 0:
            await referral_service.withdraw_pending_rewards(
                telegram_id=fresh_user.telegram_id,
                reward_type=ReferralRewardType.MONEY,
                amount=from_bonus,
            )
        
        # Process payment as succeeded
        await payment_gateway_service.handle_payment_succeeded(result.id)
        
        logger.info(f"{log(user)} Paid subscription from balance: {price.final_amount} {currency.symbol}")
        
    except Exception as e:
        logger.error(f"{log(user)} Failed to process balance payment: {e}", exc_info=True)
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-subscription-payment-creation-failed"),
        )
        return
    
    # Go to success page (после успешной обработки платежа)
    try:
        await dialog_manager.switch_to(state=Subscription.SUCCESS)
    except Exception as e:
        logger.error(f"{log(user)} Failed to switch to success state: {e}", exc_info=True)
        # Даже если switch_to не удался, платеж прошел успешно, не показываем ошибку


async def on_referral_code_request(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Обработчик нажатия кнопки 'Реферальная подписка' или 'Улучшить до реферальной' - переход к вводу кода"""
    # Определяем, это upgrade или новая подписка
    is_upgrade = widget.widget_id == "upgrade_referral"
    dialog_manager.dialog_data["is_upgrade_mode"] = is_upgrade
    await dialog_manager.switch_to(state=Subscription.REFERRAL_CODE)


async def _delete_message_after_delay(msg: Message, delay: int, countdown: bool = False) -> None:
    """Вспомогательная функция для удаления сообщения с задержкой.
    
    Args:
        msg: Сообщение для удаления
        delay: Задержка в секундах
        countdown: Если True, показывает обратный отсчёт в сообщении
    """
    import asyncio
    
    if countdown and delay > 0:
        # Получаем исходный текст сообщения (без таймера)
        original_text = msg.text or msg.caption or ""
        # Убираем старую строку с таймером если есть
        lines = original_text.split("\n")
        filtered_lines = [line for line in lines if "⏱" not in line]
        base_text = "\n".join(filtered_lines).rstrip()
        
        for remaining in range(delay, 0, -1):
            try:
                new_text = f"{base_text}\n\n<i>⏱ Сообщение закроется через {remaining} сек.</i>"
                await msg.edit_text(new_text)
            except Exception:
                pass
            await asyncio.sleep(1)
    else:
        await asyncio.sleep(delay)
    
    try:
        await msg.delete()
    except Exception:
        pass


@inject
async def on_referral_code_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    user_service: FromDishka[UserService],
    referral_service: FromDishka[ReferralService],
    plan_service: FromDishka[PlanService],
    subscription_service: FromDishka[SubscriptionService],
    notification_service: FromDishka[NotificationService],
    remnawave_service: FromDishka[RemnawaveService],
    i18n: FromDishka[TranslatorRunner],
) -> None:
    """Обработчик ввода реферального кода"""
    import asyncio
    from src.services.remnawave import RemnawaveService
    
    # Получаем RemnaWaveService через контейнер
    container = dialog_manager.middleware_data.get("dishka_container")
    remnawave_service = await container.get(RemnawaveService)
    
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    referral_code = message.text.strip().lower() if message.text else ""
    
    logger.info(f"{log(user)} Entered referral code: {referral_code}")
    
    # 1. Проверяем, что пользователь не вводит свой код
    if referral_code == user.referral_code.lower():
        logger.warning(f"{log(user)} Tried to use own referral code")
        try:
            await message.delete()
        except Exception:
            pass
        error_msg = await message.answer(i18n.ntf.referral.code.self())
        asyncio.create_task(_delete_message_after_delay(error_msg, 5))
        dialog_manager.show_mode = ShowMode.NO_UPDATE
        return
    
    # 2. Проверяем, существует ли пользователь с таким реферальным кодом
    referrer = await user_service.get_by_referral_code(referral_code)
    if not referrer:
        logger.warning(f"{log(user)} Invalid referral code: {referral_code}")
        try:
            await message.delete()
        except Exception:
            pass
        error_msg = await message.answer(i18n.ntf.referral.code.invalid())
        asyncio.create_task(_delete_message_after_delay(error_msg, 5))
        dialog_manager.show_mode = ShowMode.NO_UPDATE
        return
    
    # 2.1. Проверяем, что пользователь не вводит код своего реферала
    # (если referrer - это реферал текущего user, то запрещаем)
    user_referrals = await referral_service.get_referrals_by_referrer(user.telegram_id)
    if any(ref.referred.telegram_id == referrer.telegram_id for ref in user_referrals):
        logger.warning(f"{log(user)} Tried to use code of own referral: {referrer.telegram_id}")
        try:
            await message.delete()
        except Exception:
            pass
        error_msg = await message.answer(i18n.ntf.referral.code.own.referral())
        asyncio.create_task(_delete_message_after_delay(error_msg, 5))
        dialog_manager.show_mode = ShowMode.NO_UPDATE
        return
    
    # 3. Проверяем, не использовал ли пользователь уже реферальную подписку
    # В режиме upgrade это разрешено, так как у пользователя уже есть пробная подписка
    is_upgrade_mode = dialog_manager.dialog_data.get("is_upgrade_mode", False)
    
    existing_referral = await referral_service.get_referral_by_referred(user.telegram_id)
    if existing_referral and not is_upgrade_mode:
        logger.warning(f"{log(user)} Already used referral subscription")
        try:
            await message.delete()
        except Exception:
            pass
        error_msg = await message.answer(i18n.ntf.referral.code.already.used())
        asyncio.create_task(_delete_message_after_delay(error_msg, 5))
        dialog_manager.show_mode = ShowMode.NO_UPDATE
        return
    
    # 4. Создаем реферальную связь
    await referral_service.create_referral(
        referrer=referrer,
        referred=user,
        level=ReferralLevel.FIRST,
    )
    
    logger.info(f"{log(user)} Referral created: {referrer.telegram_id} -> {user.telegram_id}")
    
    # 5. Уведомляем реферера о новом приглашенном (с кнопкой "Закрыть" вместо автоудаления)
    await notification_service.notify_user(
        user=referrer,
        payload=MessagePayload(
            i18n_key="ntf-event-user-referral-attached",
            i18n_kwargs={"name": user.name},
            auto_delete_after=None,  # Не удалять автоматически
            add_close_button=True,   # Добавить кнопку "Закрыть"
        ),
    )
    
    # 6. Обновляем кеш пользователя
    await user_service.clear_user_cache(user.telegram_id)
    fresh_user = await user_service.get(user.telegram_id)
    
    if not fresh_user:
        logger.error(f"{log(user)} Failed to get fresh user after referral creation")
        return
    
    # 7. Обрабатываем upgrade или новую подписку
    if is_upgrade_mode:
        # Режим улучшения: добавляем 4 дня к текущей подписке И МЕНЯЕМ ПЛАН
        if not fresh_user.current_subscription:
            logger.error(f"{log(user)} No active subscription for upgrade")
            return
        
        # Получаем INVITED план
        invited_plan = await plan_service.get_invited_plan()
        if not invited_plan:
            logger.error(f"{log(user)} No INVITED plan available for upgrade")
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(i18n_key="ntf-trial-unavailable"),
            )
            return
        
        from datetime import timedelta
        
        # Обновляем подписку: добавляем 4 дня И меняем план
        subscription = fresh_user.current_subscription
        new_expire_at = subscription.expire_at + timedelta(days=4)
        subscription.expire_at = new_expire_at
        
        # ВАЖНО: Меняем план с TRIAL на INVITED и обновляем ВСЕ параметры подписки
        subscription.plan = PlanSnapshotDto.from_plan(
            invited_plan, 
            invited_plan.durations[0].days
        )
        # Обновляем tag подписки из нового плана (для RemnaWave)
        subscription.tag = invited_plan.tag
        # Это теперь не пробная подписка
        subscription.is_trial = False
        # Обновляем лимиты из нового плана
        subscription.traffic_limit = invited_plan.traffic_limit
        subscription.device_limit = invited_plan.device_limit
        subscription.traffic_limit_strategy = invited_plan.traffic_limit_strategy
        subscription.internal_squads = invited_plan.internal_squads
        subscription.external_squad = invited_plan.external_squad
        
        logger.info(
            f"{log(user)} Upgrading trial to invited: "
            f"plan changed to '{invited_plan.name}', tag='{invited_plan.tag}', "
            f"added 4 days, new expire: {new_expire_at}"
        )
        
        # DEBUG: Проверяем что tag установлен правильно перед отправкой в RemnaWave
        logger.info(
            f"{log(user)} DEBUG before RemnaWave update: "
            f"subscription.tag='{subscription.tag}', "
            f"subscription.is_trial={subscription.is_trial}, "
            f"subscription.plan.name='{subscription.plan.name}', "
            f"subscription.plan.tag='{subscription.plan.tag}'"
        )
        
        # Обновляем подписку через RemnaWave
        await remnawave_service.updated_user(
            user=fresh_user,
            uuid=subscription.user_remna_id,
            subscription=subscription,
        )
        
        # Обновляем локальную подписку в БД
        await subscription_service.update(subscription)
        
        # Очищаем кеш
        await user_service.clear_user_cache(fresh_user.telegram_id)
        
        logger.info(f"{log(user)} Successfully upgraded trial to invited subscription")

        # Удаляем сообщение пользователя с реферальным кодом
        try:
            await message.delete()
        except Exception:
            pass

        # Переходим на экран успеха реферальной подписки (DELETE_AND_SEND удалит старый диалог)
        dialog_manager.show_mode = ShowMode.DELETE_AND_SEND
        await dialog_manager.start(state=Subscription.REFERRAL_SUCCESS, mode=StartMode.RESET_STACK)
    else:
        # Режим новой подписки: выдаем INVITED подписку
        # Получаем INVITED план (обязательно!)
        plan = await plan_service.get_invited_plan()
        if not plan:
            logger.error(f"{log(user)} No INVITED plan available for referral code activation")
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(i18n_key="ntf-trial-unavailable"),
            )
            return
        
        # 8. Активируем подписку через задачу
        from src.infrastructure.taskiq.tasks.subscription import trial_subscription_task
        
        trial = PlanSnapshotDto.from_plan(plan, plan.durations[0].days)
        await trial_subscription_task.kiq(fresh_user, trial)
        
        # 9. Удаляем сообщение пользователя с реферальным кодом
        try:
            await message.delete()
        except Exception:
            pass
        
        # 10. Переходим на экран подписки и обновляем диалог (DELETE_AND_SEND удалит старый диалог)
        dialog_manager.show_mode = ShowMode.DELETE_AND_SEND
        await dialog_manager.switch_to(state=Subscription.MAIN)


@inject
async def on_promocode_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
    promocode_service: FromDishka[PromocodeService],
    user_service: FromDishka["UserService"],
    i18n: FromDishka[TranslatorRunner],
) -> None:
    """Обработчик ввода промокода для активации."""
    import asyncio
    from src.core.enums import PromocodeRewardType
    from src.infrastructure.database.models.sql import PromocodeActivation
    
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    promocode_text = message.text.strip() if message.text else ""
    
    if not promocode_text:
        logger.warning(f"{log(user)} Empty promocode input")
        try:
            await message.delete()
        except Exception:
            pass
        return
    
    logger.info(f"{log(user)} Trying to activate promocode: {promocode_text}")
    
    try:
        # Ищем промокод по коду
        promocode = await promocode_service.get_by_code(promocode_code=promocode_text)
        
        if not promocode:
            logger.warning(f"{log(user)} Promocode not found: {promocode_text}")
            try:
                await message.delete()
            except Exception:
                pass
            error_msg = await message.answer(i18n.get("ntf-promocode-not-found"))
            asyncio.create_task(_delete_message_after_delay(error_msg, 5))
            dialog_manager.show_mode = ShowMode.NO_UPDATE
            return
        
        if not promocode.is_active:
            logger.warning(f"{log(user)} Promocode is inactive: {promocode_text}")
            try:
                await message.delete()
            except Exception:
                pass
            error_msg = await message.answer(i18n.get("ntf-promocode-inactive"))
            asyncio.create_task(_delete_message_after_delay(error_msg, 5))
            dialog_manager.show_mode = ShowMode.NO_UPDATE
            return
        
        # Проверяем, не активировал ли пользователь уже этот промокод
        user_already_activated = any(
            activation.user_telegram_id == user.telegram_id 
            for activation in promocode.activations
        )
        if user_already_activated:
            logger.warning(f"{log(user)} User already activated this promocode: {promocode_text}")
            try:
                await message.delete()
            except Exception:
                pass
            error_msg = await message.answer(i18n.get("ntf-promocode-already-activated"))
            asyncio.create_task(_delete_message_after_delay(error_msg, 5))
            dialog_manager.show_mode = ShowMode.NO_UPDATE
            return
        
        # Проверяем лимит использований
        if promocode.max_activations is not None and len(promocode.activations) >= promocode.max_activations:
            logger.warning(f"{log(user)} Promocode limit exceeded: {promocode_text}")
            try:
                await message.delete()
            except Exception:
                pass
            error_msg = await message.answer(i18n.get("ntf-promocode-limit-exceeded"))
            asyncio.create_task(_delete_message_after_delay(error_msg, 5))
            dialog_manager.show_mode = ShowMode.NO_UPDATE
            return
        
        # Проверяем доступность промокода для текущего тарифа пользователя
        logger.debug(f"{log(user)} Checking plan access for promocode: allowed_plan_ids={promocode.allowed_plan_ids}, type={type(promocode.allowed_plan_ids)}")
        if promocode.allowed_plan_ids and len(promocode.allowed_plan_ids) > 0:
            user_plan_id = None
            if user.current_subscription and user.current_subscription.plan:
                user_plan_id = user.current_subscription.plan.id
            
            logger.debug(f"{log(user)} User plan_id={user_plan_id}, allowed_plan_ids={promocode.allowed_plan_ids}")
            if user_plan_id is None or user_plan_id not in promocode.allowed_plan_ids:
                logger.warning(f"{log(user)} Promocode not available for user's plan: {promocode_text}, user_plan_id={user_plan_id}, allowed_plan_ids={promocode.allowed_plan_ids}")
                try:
                    await message.delete()
                except Exception:
                    pass
                error_msg = await message.answer(i18n.get("ntf-promocode-plan-unavailable"))
                asyncio.create_task(_delete_message_after_delay(error_msg, 5))
                dialog_manager.show_mode = ShowMode.NO_UPDATE
                return
        
        logger.info(f"{log(user)} Promocode validated successfully: {promocode_text}")
        
        # Сохраняем предыдущую скидку для возможности восстановления при удалении промокода
        previous_discount = 0
        previous_discount_expires_at = None
        
        # Применяем промокод в зависимости от типа
        if promocode.reward_type == PromocodeRewardType.PURCHASE_DISCOUNT:
            # Сохраняем предыдущую скидку и её срок действия
            previous_discount = user.purchase_discount
            previous_discount_expires_at = user.purchase_discount_expires_at
            # Одноразовая скидка - увеличиваем значение если новая больше
            if promocode.reward and promocode.reward > user.purchase_discount:
                from datetime import datetime, timedelta, timezone
                user.purchase_discount = promocode.reward
                # Устанавливаем срок действия скидки на основе lifetime промокода
                if promocode.lifetime and promocode.lifetime > 0:
                    user.purchase_discount_expires_at = datetime.now(timezone.utc) + timedelta(days=promocode.lifetime)
                else:
                    user.purchase_discount_expires_at = None  # Безлимитная скидка
                await user_service.update(user)
                logger.info(f"{log(user)} Applied purchase discount: {promocode.reward}%, expires: {user.purchase_discount_expires_at}")
        
        elif promocode.reward_type == PromocodeRewardType.PERSONAL_DISCOUNT:
            # Сохраняем предыдущую скидку
            previous_discount = user.personal_discount
            # Персональная скидка - увеличиваем значение если новая больше
            if promocode.reward and promocode.reward > user.personal_discount:
                user.personal_discount = promocode.reward
                await user_service.update(user)
                logger.info(f"{log(user)} Applied personal discount: {promocode.reward}%")
        
        elif promocode.reward_type == PromocodeRewardType.DURATION:
            # Бонусные дни - пока не реализовано
            logger.warning(f"{log(user)} DURATION promocode type is not yet implemented")
        
        # Создаем запись активации промокода с сохранением предыдущей скидки и её срока действия
        try:
            activation = PromocodeActivation(
                promocode_id=promocode.id,
                user_telegram_id=user.telegram_id,
                previous_discount=previous_discount,
                previous_discount_expires_at=previous_discount_expires_at,
            )
            promocode_service.uow.repository.session.add(activation)
            await promocode_service.uow.commit()
            logger.info(f"{log(user)} Promocode activation record created with previous_discount={previous_discount}, expires_at={previous_discount_expires_at}")
        except Exception as e:
            logger.error(f"{log(user)} Failed to create activation record: {e}")
        
        # Удаляем сообщение пользователя
        try:
            await message.delete()
        except Exception:
            pass
        
        # Отправляем системное уведомление о промокоде
        from src.core.enums import SystemNotificationType
        await notification_service.system_notify(
            ntf_type=SystemNotificationType.PROMOCODE_ACTIVATED,
            payload=MessagePayload.not_deleted(
                i18n_key="ntf-event-promocode-activated",
                i18n_kwargs={
                    "user_id": str(user.telegram_id),
                    "user_name": user.name,
                    "username": user.username or False,
                    "promocode_code": promocode.code,
                    "promocode_reward": promocode.reward,
                    "promocode_reward_type": promocode.reward_type.value,
                },
                reply_markup=get_user_keyboard(user.telegram_id),
            ),
        )
        logger.info(f"{log(user)} Sent promocode activation notification to devs")
        
        # Сначала возвращаемся в главное меню
        dialog_manager.show_mode = ShowMode.DELETE_AND_SEND
        await dialog_manager.start(state=MainMenu.MAIN, mode=StartMode.RESET_STACK)
        
        # Отправляем сообщение ПОСЛЕ главного меню (без таймера)
        success_text = i18n.get("ntf-promocode-activated", promocode=promocode_text)
        success_msg = await message.answer(success_text)
        asyncio.create_task(_delete_message_after_delay(success_msg, 5, countdown=False))
        
    except Exception as e:
        logger.error(f"{log(user)} Error while activating promocode: {e}\n{traceback.format_exc()}")
        try:
            await message.delete()
        except Exception:
            pass
        error_msg = await message.answer(i18n.get("ntf-promocode-activation-error"))
        asyncio.create_task(_delete_message_after_delay(error_msg, 5))
        dialog_manager.show_mode = ShowMode.NO_UPDATE


# ==================== Устройства ====================


@inject
async def on_device_delete(
    callback: CallbackQuery,
    widget: Button,
    sub_manager: SubManager,
    remnawave_service: FromDishka[RemnawaveService],
) -> None:
    """Удаление устройства из списка."""
    await sub_manager.load_data()
    selected_short_hwid = sub_manager.item_id
    user: UserDto = sub_manager.middleware_data[USER_KEY]
    hwid_map = sub_manager.dialog_data.get("hwid_map")

    if not hwid_map:
        raise ValueError(f"Selected '{selected_short_hwid}' HWID, but 'hwid_map' is missing")

    full_hwid = next((d["hwid"] for d in hwid_map if d["short_hwid"] == selected_short_hwid), None)

    if not full_hwid:
        raise ValueError(f"Full HWID not found for '{selected_short_hwid}'")

    if not (user.current_subscription and user.current_subscription.device_limit):
        raise ValueError("User has no active subscription or device limit unlimited")

    devices = await remnawave_service.delete_device(user=user, hwid=full_hwid)
    logger.info(f"{log(user)} Deleted device '{full_hwid}'")

    if devices:
        return

    await sub_manager.switch_to(state=Subscription.MAIN)


@inject
async def on_add_device(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход к выбору количества устройств для добавления."""
    await dialog_manager.switch_to(state=Subscription.ADD_DEVICE_SELECT_COUNT)


@inject
async def on_add_device_select_count(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    item_id: str,
) -> None:
    """Обработка выбора количества устройств - переход к выбору типа покупки."""
    try:
        device_count = int(item_id)
        # Сохраняем количество в dialog_data
        dialog_manager.dialog_data["device_count"] = device_count
        # Переходим к выбору типа покупки (до конца подписки / до конца месяца)
        await dialog_manager.switch_to(state=Subscription.ADD_DEVICE_DURATION)
    except (ValueError, TypeError):
        logger.error(f"Invalid device count: {item_id}")


@inject
async def on_add_device_duration_select(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Обработка выбора типа покупки (до конца подписки / до конца месяца)."""
    from src.core.utils.pricing import (
        calculate_device_price_until_subscription_end,
        calculate_device_price_until_month_end,
        MIN_EXTRA_DEVICE_DAYS,
    )
    
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Определяем тип покупки по id кнопки
    duration_type = "full" if widget.widget_id == "duration_full" else "month"
    
    device_count = dialog_manager.dialog_data.get("device_count", 1)
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
        calculated_price = price_per_device * device_count
    else:
        calculated_price = device_price_monthly * device_count
        duration_days = 30
    
    # Сохраняем данные в dialog_data
    dialog_manager.dialog_data["duration_type"] = duration_type
    dialog_manager.dialog_data["duration_days"] = duration_days
    dialog_manager.dialog_data["calculated_price"] = calculated_price
    
    logger.info(f"{log(user)} Selected duration type '{duration_type}' for {device_count} devices, {duration_days} days, price={calculated_price}")
    
    # Переходим к выбору способа оплаты
    await dialog_manager.switch_to(state=Subscription.ADD_DEVICE_PAYMENT)


@inject
async def on_add_device_payment_select(
    callback: CallbackQuery,
    widget: Select,
    dialog_manager: DialogManager,
    selected_payment_method: PaymentGatewayType,
    payment_gateway_service: FromDishka[PaymentGatewayService],
    notification_service: FromDishka[NotificationService],
    user_service: FromDishka[UserService],
    remnawave_service: FromDishka[RemnawaveService],
    subscription_service: FromDishka[SubscriptionService],
    settings_service: FromDishka[SettingsService],
    pricing_service: FromDishka[PricingService],
    transaction_service: FromDishka[TransactionService],
    i18n: FromDishka[TranslatorRunner],
) -> None:
    """Обработка выбора способа оплаты для добавления устройства - переход к подтверждению."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    logger.info(f"{log(user)} Selected payment method '{selected_payment_method}' for adding device")
    
    if not user.current_subscription:
        logger.error(f"{log(user)} No active subscription for adding device")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-subscription-required"),
        )
        return
    
    # Сохраняем выбранный метод оплаты
    dialog_manager.dialog_data["selected_payment_method"] = selected_payment_method
    
    # Для оплаты картой - создаём платеж
    if selected_payment_method != PaymentGatewayType.BALANCE:
        try:
            device_count = dialog_manager.dialog_data.get("device_count", 1)
            
            # Получаем уже рассчитанную цену из dialog_data
            calculated_price = dialog_manager.dialog_data.get("calculated_price")
            
            if calculated_price is None:
                # Если цена не была рассчитана, используем старую логику (fallback)
                from src.core.utils.pricing import calculate_prorated_device_price
                device_price_monthly = await settings_service.get_extra_device_price()
                device_price_rub = calculate_prorated_device_price(
                    monthly_price=device_price_monthly,
                    subscription_expire_at=user.current_subscription.expire_at,
                )
                calculated_price = device_price_rub * device_count
            
            # Получаем глобальную скидку
            global_discount = await settings_service.get_global_discount_settings()
            
            payment_gateway = await payment_gateway_service.get_by_type(selected_payment_method)
            if not payment_gateway:
                logger.error(f"{log(user)} Payment gateway '{selected_payment_method}' not found")
                await notification_service.notify_user(
                    user=user,
                    payload=MessagePayload(i18n_key="ntf-payment-gateway-not-available"),
                )
                return
            
            # Получаем курсы валют
            settings = await settings_service.get()
            rates = settings.features.currency_rates
            
            # Применяем скидку к уже рассчитанной цене
            pricing_rub = pricing_service.calculate(
                user=user,
                price=Decimal(calculated_price),
                currency=Currency.RUB,
                global_discount=global_discount,
                context="extra_devices",
            )
            
            # Конвертируем итоговую цену (со скидкой) в валюту шлюза
            final_amount = pricing_service.convert_currency(
                pricing_rub.final_amount,
                payment_gateway.currency,
                rates.usd_rate,
                rates.eur_rate,
                rates.stars_rate,
            )
            
            # Создаём платеж для дополнительных устройств
            duration_days = dialog_manager.dialog_data.get("duration_days", 30)
            payment_result = await payment_gateway_service.create_extra_devices_payment(
                user=user,
                device_count=device_count,
                amount=final_amount,
                gateway_type=selected_payment_method,
                duration_days=duration_days,
            )
            
            logger.info(f"{log(user)} Created payment '{payment_result.id}' for {device_count} extra devices, amount={final_amount} {payment_gateway.currency.symbol}, duration={duration_days} days")
            
            # Сохраняем информацию о платеже в диалог
            dialog_manager.dialog_data["payment_id"] = str(payment_result.id)
            dialog_manager.dialog_data["payment_url"] = payment_result.url
            
        except Exception as exception:
            logger.error(f"{log(user)} Failed to create payment for extra devices: {exception}")
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(i18n_key="ntf-payment-creation-failed"),
            )
            return
    
    # Переходим к окну подтверждения
    await dialog_manager.switch_to(state=Subscription.ADD_DEVICE_CONFIRM)


@inject
async def on_add_device_confirm(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    payment_gateway_service: FromDishka[PaymentGatewayService],
    notification_service: FromDishka[NotificationService],
    user_service: FromDishka[UserService],
    remnawave_service: FromDishka[RemnawaveService],
    subscription_service: FromDishka[SubscriptionService],
    settings_service: FromDishka[SettingsService],
    extra_device_service: FromDishka[ExtraDeviceService],
    pricing_service: FromDishka[PricingService],
    transaction_service: FromDishka[TransactionService],
    referral_service: FromDishka[ReferralService],
    i18n: FromDishka[TranslatorRunner],
) -> None:
    """Обработка подтверждения покупки устройств."""
    from decimal import Decimal
    
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    selected_payment_method = dialog_manager.dialog_data.get("selected_payment_method")
    device_count = dialog_manager.dialog_data.get("device_count", 1)
    duration_days = dialog_manager.dialog_data.get("duration_days", 30)
    duration_type = dialog_manager.dialog_data.get("duration_type", "full")
    
    # Получаем уже рассчитанную цену из dialog_data
    calculated_price = dialog_manager.dialog_data.get("calculated_price")
    
    if calculated_price is None:
        # Если цена не была рассчитана, используем старую логику (fallback)
        from src.core.utils.pricing import calculate_prorated_device_price
        device_price_monthly = await settings_service.get_extra_device_price()
        if user.current_subscription:
            device_price = calculate_prorated_device_price(
                monthly_price=device_price_monthly,
                subscription_expire_at=user.current_subscription.expire_at,
            )
        else:
            device_price = device_price_monthly
        calculated_price = device_price * device_count
    
    # Получаем глобальную скидку
    global_discount = await settings_service.get_global_discount_settings()
    
    # Вычисляем цену со скидкой используя PricingService (учитывает все скидки)
    price_details = pricing_service.calculate(
        user=user,
        price=Decimal(calculated_price),
        currency=Currency.RUB,
        global_discount=global_discount,
        context="extra_devices",
    )
    
    total_price = int(price_details.final_amount)
    discount_value = price_details.discount_percent
    
    logger.info(f"{log(user)} Confirmed adding {device_count} devices with payment method '{selected_payment_method}', discount={discount_value}%, price={total_price}, duration={duration_days} days, type={duration_type}")
    
    if not user.current_subscription:
        logger.error(f"{log(user)} No active subscription for adding device")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-subscription-required"),
        )
        return
    
    # Оплата с баланса
    if selected_payment_method == PaymentGatewayType.BALANCE:
        # Проверяем баланс
        fresh_user = await user_service.get(user.telegram_id)
        
        # В режиме COMBINED учитываем и бонусный баланс
        is_balance_combined = await settings_service.is_balance_combined()
        referral_balance = await referral_service.get_pending_rewards_amount(
            telegram_id=user.telegram_id,
            reward_type=ReferralRewardType.MONEY,
        )
        available_balance = fresh_user.balance + referral_balance if is_balance_combined else fresh_user.balance
        
        if not fresh_user or available_balance < total_price:
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(i18n_key="ntf-subscription-insufficient-balance"),
            )
            return
        
        # Списываем с баланса (with COMBINED mode support)
        from_main, from_bonus = await user_service.subtract_from_combined_balance(
            user=fresh_user,
            amount=total_price,
            referral_balance=referral_balance,
            is_combined=is_balance_combined,
        )
        
        # Если списали с бонусного, отмечаем награды как использованные
        if from_bonus > 0:
            await referral_service.withdraw_pending_rewards(
                telegram_id=fresh_user.telegram_id,
                reward_type=ReferralRewardType.MONEY,
                amount=from_bonus,
            )
        
        # Увеличиваем лимит устройств
        subscription = fresh_user.current_subscription
        new_extra_devices = (subscription.extra_devices or 0) + device_count
        subscription.extra_devices = new_extra_devices
        subscription.device_limit = (subscription.device_limit or 0) + device_count
        
        # Обновляем в БД
        await subscription_service.update(subscription)
        
        # Создаём запись о покупке дополнительных устройств с выбранной длительностью
        await extra_device_service.create_purchase(
            user=fresh_user,
            subscription=subscription,
            device_count=device_count,
            price=total_price,  # Сохраняем цену со скидкой
            duration_days=duration_days,
        )
        
        # Обновляем в RemnaWave
        await remnawave_service.updated_user(
            user=fresh_user,
            uuid=subscription.user_remna_id,
            subscription=subscription,
        )
        
        # Очищаем кеш
        await user_service.clear_user_cache(fresh_user.telegram_id)
        
        logger.info(f"{log(user)} Added {device_count} devices from balance (discount={discount_value}%). New device limit: {subscription.device_limit}")
        
        # Получаем детали подписки для уведомления
        from src.core.utils.formatters import (
            i18n_format_traffic_limit,
            i18n_format_expire_time,
            i18n_format_bytes_to_unit,
        )
        
        # Вычисляем device_limit_number и device_limit_bonus
        plan_device_limit = (
            subscription.plan.device_limit 
            if subscription.plan and subscription.plan.device_limit > 0 
            else 0
        )
        device_limit_number = (
            plan_device_limit 
            if plan_device_limit > 0 
            else subscription.device_limit
        )
        device_limit_bonus = max(
            0, 
            subscription.device_limit - plan_device_limit - subscription.extra_devices
        ) if plan_device_limit > 0 else 0
        
        # Уведомляем разработчика о покупке (Event-уведомление)
        from src.core.enums import SystemNotificationType
        from src.bot.keyboards import get_user_keyboard
        await notification_service.system_notify(
            payload=MessagePayload.not_deleted(
                i18n_key="ntf-event-extra-devices-balance",
                i18n_kwargs={
                    "user_id": str(fresh_user.telegram_id),
                    "user_name": fresh_user.name,
                    "username": fresh_user.username or False,
                    "device_count": device_count,
                    "price": total_price,
                    "discount_percent": discount_value,
                    # Параметры для frg-subscription-details
                    "subscription_id": str(subscription.user_remna_id),
                    "subscription_status": subscription.status,
                    "plan_name": subscription.plan.name,
                    "traffic_used": i18n_format_bytes_to_unit(0),  # TODO: получить real traffic used
                    "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
                    "device_limit_number": device_limit_number,
                    "device_limit_bonus": device_limit_bonus,
                    "extra_devices": subscription.extra_devices,
                    "expire_time": i18n_format_expire_time(subscription.expire_at),
                },
                reply_markup=get_user_keyboard(fresh_user.telegram_id),
            ),
            ntf_type=SystemNotificationType.EXTRA_DEVICES,
        )
        
        # Переходим на экран успеха добавления устройств (без отдельного уведомления)
        await dialog_manager.switch_to(state=Subscription.ADD_DEVICE_SUCCESS)
        return
    
    # Для других способов оплаты - платеж уже создан, пользователь откроет ссылку через URL-кнопку
    # Просто логируем и возвращаемся на экран устройств
    payment_id = dialog_manager.dialog_data.get("payment_id")
    payment_url = dialog_manager.dialog_data.get("payment_url")
    
    if payment_id and payment_url:
        logger.info(f"{log(user)} Payment link ready for extra devices payment '{payment_id}'")
        # Очищаем информацию о платеже из диалога
        dialog_manager.dialog_data.pop("payment_id", None)
        dialog_manager.dialog_data.pop("payment_url", None)
        # Возвращаемся на экран устройств
        await dialog_manager.switch_to(state=Subscription.DEVICES)
    else:
        logger.error(f"{log(user)} Payment information not found for extra devices")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-payment-creation-failed"),
        )
        await dialog_manager.switch_to(state=Subscription.DEVICES)


@inject
async def on_extra_devices_list(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переход к списку купленных дополнительных устройств."""
    await dialog_manager.switch_to(state=Subscription.EXTRA_DEVICES_LIST)


@inject
async def on_select_extra_device_purchase(
    callback: CallbackQuery,
    widget: Select,
    dialog_manager: DialogManager,
    item_id: str,
) -> None:
    """Выбор покупки для управления."""
    dialog_manager.dialog_data["selected_purchase_id"] = int(item_id)
    await dialog_manager.switch_to(state=Subscription.EXTRA_DEVICE_MANAGE)


@inject
async def on_disable_auto_renew(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    extra_device_service: FromDishka[ExtraDeviceService],
    notification_service: FromDishka[NotificationService],
) -> None:
    """Отключить автопродление для покупки."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    purchase_id = dialog_manager.dialog_data.get("selected_purchase_id")
    
    if not purchase_id:
        return
    
    await extra_device_service.disable_auto_renew(purchase_id)
    
    logger.info(f"{log(user)} Disabled auto-renew for extra device purchase '{purchase_id}'")
    
    await notification_service.notify_user(
        user=user,
        payload=MessagePayload(i18n_key="ntf-extra-device-auto-renew-disabled"),
    )
    
    await dialog_manager.switch_to(state=Subscription.EXTRA_DEVICES_LIST)


@inject
async def on_delete_extra_device_purchase(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    extra_device_service: FromDishka[ExtraDeviceService],
    subscription_service: FromDishka[SubscriptionService],
    remnawave_service: FromDishka[RemnawaveService],
    user_service: FromDishka[UserService],
    notification_service: FromDishka[NotificationService],
) -> None:
    """Удалить покупку дополнительных устройств (немедленное отключение)."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Получаем purchase_id из SubManager (ListGroup) или dialog_data
    if isinstance(dialog_manager, SubManager):
        purchase_id = int(dialog_manager.item_id)
    else:
        purchase_id = dialog_manager.dialog_data.get("selected_purchase_id")
    
    if not purchase_id:
        return
    
    # Получаем информацию о покупке
    purchase = await extra_device_service.get(purchase_id)
    if not purchase:
        return
    
    subscription = user.current_subscription
    if not subscription:
        return
    
    # Удаляем покупку и уменьшаем лимит устройств
    device_count_to_remove = purchase.device_count
    await extra_device_service.delete(purchase_id)
    
    # Обновляем лимит устройств в подписке
    new_extra_devices = max(0, (subscription.extra_devices or 0) - device_count_to_remove)
    # Вычитаем устройства, но не меньше базового лимита плана
    base_device_limit = (subscription.plan.device_limit if subscription.plan and subscription.plan.device_limit else 0)
    current_device_limit = subscription.device_limit if subscription.device_limit else 0
    new_device_limit = max(base_device_limit, current_device_limit - device_count_to_remove)
    
    subscription.extra_devices = new_extra_devices
    subscription.device_limit = new_device_limit
    
    await subscription_service.update(subscription)
    
    # Обновляем в Remnawave
    await remnawave_service.updated_user(
        user=user,
        uuid=subscription.user_remna_id,
        subscription=subscription,
    )
    
    # Очищаем кеш
    await user_service.clear_user_cache(user.telegram_id)
    
    logger.info(f"{log(user)} Deleted extra device purchase '{purchase_id}', removed {device_count_to_remove} devices")
    
    await notification_service.notify_user(
        user=user,
        payload=MessagePayload(i18n_key="ntf-extra-device-deleted"),
    )
    
    # Проверяем, остались ли ещё покупки доп. устройств
    remaining_purchases = await extra_device_service.get_active_by_subscription(subscription.id)
    
    await callback.answer()
    
    # Если больше нет покупок - перенаправляем на меню устройств
    if len(remaining_purchases) == 0:
        from src.bot.states import MainMenu
        await dialog_manager.start(
            state=MainMenu.DEVICES,
            mode=StartMode.RESET_STACK,
        )


@inject
async def on_back_to_devices(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Вернуться к списку устройств."""
    await dialog_manager.switch_to(state=Subscription.DEVICES)

