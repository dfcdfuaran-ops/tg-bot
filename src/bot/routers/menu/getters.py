from typing import Any
import html

from aiogram_dialog import DialogManager
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from fluentogram import TranslatorRunner
from loguru import logger

from src.core.config import AppConfig
from src.core.exceptions import MenuRenderingError
from src.core.utils.formatters import (
    format_username_to_url,
    i18n_format_device_limit,
    i18n_format_expire_time,
    i18n_format_traffic_limit,
)
from src.infrastructure.database.models.dto import UserDto
from src.services.balance_transfer import BalanceTransferService
from src.services.payment_gateway import PaymentGatewayService
from src.services.plan import PlanService
from src.services.referral import ReferralService
from src.services.remnawave import RemnawaveService
from src.services.settings import SettingsService
from src.services.subscription import SubscriptionService


def get_display_balance(user_balance: int, referral_balance: int, is_combined: bool) -> int:
    """
    Вычисляет отображаемый баланс в зависимости от режима.
    
    В режиме COMBINED возвращает сумму основного и бонусного баланса.
    В режиме SEPARATE возвращает только основной баланс.
    """
    return user_balance + referral_balance if is_combined else user_balance


from src.services.extra_device import ExtraDeviceService


@inject
async def menu_getter(
    dialog_manager: DialogManager,
    config: AppConfig,
    user: UserDto,
    i18n: FromDishka[TranslatorRunner],
    plan_service: FromDishka[PlanService],
    subscription_service: FromDishka[SubscriptionService],
    settings_service: FromDishka[SettingsService],
    referral_service: FromDishka[ReferralService],
    extra_device_service: FromDishka[ExtraDeviceService],
    **kwargs: Any,
) -> dict[str, Any]:
    from src.core.enums import ReferralRewardType
    
    try:
        # Определяем, является ли пользователь приглашённым
        referral = await referral_service.get_referral_by_referred(user.telegram_id)
        is_invited = bool(referral)
        
        # Используем новый метод, который учитывает приглашение пользователя
        plan = await plan_service.get_appropriate_trial_plan(user, is_invited=is_invited)
        has_used_trial = await subscription_service.has_used_trial(user.telegram_id)
        support_username = config.bot.support_username.get_secret_value()
        ref_link = await referral_service.get_ref_link(user.referral_code)
        support_link = format_username_to_url(support_username, i18n.get("contact-support-help"))
        
        # Get invite message from settings
        settings = await settings_service.get()
        # Replace placeholders with actual values
        try:
            invite_message = str(settings.referral.invite_message) if settings.referral.invite_message else None
        except Exception:
            invite_message = None
        
        if invite_message:
            # Support both Python format {url}/{name} and legacy $url/$name
            # Also support {space} for newline
            invite_message = invite_message.format(url=ref_link, name="VPN", space="\n") if "{url}" in invite_message else invite_message.replace("$url", ref_link).replace("$name", "VPN")
        else:
            invite_message = f"Join us! {ref_link}"
        
        # Get referral balance
        referral_balance = await referral_service.get_pending_rewards_amount(
            user.telegram_id,
            ReferralRewardType.MONEY,
        )

        # Вычисляем максимальную скидку для отображения
        from datetime import datetime, timezone
        
        purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
        personal_disc = user.personal_discount if user.personal_discount is not None else 0
        discount_remaining = 0  # Оставшееся время в днях
        is_temporary_discount = False  # Временная скидка (одноразовая с истечением)
        is_permanent_discount = False  # Постоянная скидка (персональная)
        
        # Проверяем срок действия одноразовой скидки
        if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
            now = datetime.now(timezone.utc)
            if user.purchase_discount_expires_at <= now:
                # Скидка истекла - обнуляем её
                purchase_disc = 0
            else:
                # Вычисляем оставшееся время в днях
                remaining = user.purchase_discount_expires_at - now
                discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
                is_temporary_discount = True
        
        # Определяем какую скидку показывать (большую)
        if purchase_disc > 0 or personal_disc > 0:
            if purchase_disc > personal_disc:
                # Одноразовая скидка больше - показываем её
                discount_value = purchase_disc
                # Если это одноразовая скидка, устанавливаем is_temporary_discount
                # (даже если нет срока истечения)
                if not is_temporary_discount:
                    is_temporary_discount = True
            elif personal_disc > 0:
                # Постоянная скидка больше или равна и она есть - показываем постоянную
                discount_value = personal_disc
                is_temporary_discount = False
                is_permanent_discount = True
                discount_remaining = 0
            else:
                # Только одноразовая без срока (purchase_disc > 0, personal_disc = 0)
                discount_value = purchase_disc
                is_temporary_discount = True
        else:
            discount_value = 0

        # Проверяем режим баланса
        is_balance_combined = await settings_service.is_balance_combined()
        display_balance = get_display_balance(user.balance, referral_balance, is_balance_combined)
        
        # Проверяем наличие дополнительных устройств для показа кнопки "Мои устройства"
        has_extra_devices_purchases = False
        subscription = user.current_subscription
        if subscription:
            # Проверяем есть ли покупки доп. устройств (включая неактивные)
            purchases = await extra_device_service.get_by_subscription(subscription.id)
            has_extra_devices_purchases = len(purchases) > 0

        base_data = {
            "user_id": str(user.telegram_id),
            "user_name": user.name,
            "discount_value": discount_value,
            "discount_is_temporary": 1 if is_temporary_discount else 0,
            "discount_is_permanent": 1 if is_permanent_discount else 0,
            "discount_remaining": discount_remaining,
            "balance": display_balance,
            "referral_balance": referral_balance,
            "referral_code": user.referral_code,
            "support": support_link,
            "invite": invite_message,
            "has_subscription": user.has_subscription,
            "is_app": config.bot.is_mini_app,
            "is_referral_enable": await settings_service.is_referral_enable(),
            # Настройки функционала
            "community_url": (await settings_service.get()).features.community_url or "",
            "is_community_enabled": await settings_service.is_community_enabled() and bool((await settings_service.get()).features.community_url),
            "is_tos_enabled": await settings_service.is_tos_enabled(),
            "tos_url": (await settings_service.get()).rules_link.get_secret_value() or "https://telegra.ph/",
            "is_balance_enabled": 1 if await settings_service.is_balance_enabled() else 0,
            "is_balance_separate": 1 if not is_balance_combined else 0,
            # Показывать кнопку "Мои устройства" если есть подписка с лимитом устройств или купленные доп. устройства
            "show_devices_button": has_extra_devices_purchases or (subscription and subscription.has_devices_limit),
        }

        if not subscription:
            base_data.update(
                {
                    "status": None,
                    "is_trial": False,
                    "trial_available": not has_used_trial and plan,
                    "has_device_limit": False,
                    "connectable": False,
                    "device_limit_bonus": 0,
                    "show_devices_button": False,
                }
            )
            return base_data

        extra_devices = subscription.extra_devices or 0
        
        # Вычисляем бонус устройств (разница между реальным лимитом из Remnawave и планом, БЕЗ купленных доп.)
        plan_device_limit = subscription.plan.device_limit if subscription.plan.device_limit > 0 else 0
        actual_device_limit = subscription.device_limit
        device_limit_bonus = max(0, actual_device_limit - plan_device_limit - extra_devices) if plan_device_limit > 0 else 0
        
        base_data.update(
            {
                "status": subscription.get_status,
                "type": subscription.get_subscription_type,
                "plan_name": subscription.plan.name,
                "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
                "device_limit": i18n_format_device_limit(plan_device_limit if plan_device_limit > 0 else subscription.device_limit),
                "device_limit_number": plan_device_limit if plan_device_limit > 0 else subscription.device_limit,
                "device_limit_bonus": device_limit_bonus,
                "extra_devices": extra_devices,
                "expire_time": i18n_format_expire_time(subscription.expire_at),
                "is_trial": subscription.is_trial,
                "traffic_strategy": subscription.traffic_limit_strategy,
                "reset_time": subscription.get_expire_time,
                "has_device_limit": subscription.has_devices_limit
                if subscription.is_active
                else False,
                "connectable": subscription.is_active,
                "url": config.bot.mini_app_url or subscription.url,
            }
        )

        return base_data
    except Exception as exception:
        raise MenuRenderingError(str(exception)) from exception


# Ссылки для скачивания приложений по платформам
DOWNLOAD_URLS = {
    "android": "https://play.google.com/store/apps/details?id=com.happproxy",
    "windows": "https://github.com/Happ-proxy/happ-desktop/releases/latest/download/setup-Happ.x64.exe",
    "iphone": "https://apps.apple.com/ru/app/happ-proxy-utility-plus/id6746188973",
    "macos": "https://github.com/Happ-proxy/happ-desktop/releases/",
}

PLATFORM_NAMES = {
    "android": "📱 Android",
    "windows": "🖥 Windows",
    "iphone": "🍏 iPhone",
    "macos": "💻 macOS",
}


@inject
async def connect_getter(
    dialog_manager: DialogManager,
    config: AppConfig,
    user: UserDto,
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна подключения с инструкцией."""
    from urllib.parse import quote
    
    subscription = user.current_subscription
    subscription_url = subscription.url if subscription else ""
    
    # Используем редирект через наш сервер, т.к. Telegram не поддерживает happ:// в кнопках
    if subscription_url:
        # Проверяем что URL валидный (не пустой и содержит протокол)
        if not subscription_url.strip() or not subscription_url.startswith(("http://", "https://")):
            from loguru import logger
            logger.warning(f"Invalid subscription URL for user {user.telegram_id}: '{subscription_url}'")
            happ_redirect_url = ""
        else:
            # Формируем URL редиректа: /api/v1/connect/{subscription_url}
            # URL уже должен быть закодирован Telegram при передаче в кнопке,
            # но на всякий случай оставляем как есть
            domain = config.domain.get_secret_value()
            happ_redirect_url = f"https://{domain}/api/v1/connect/{subscription_url}"
    else:
        happ_redirect_url = ""
    
    # URL для скачивания с автоопределением ОС
    domain = config.domain.get_secret_value()
    download_url = f"https://{domain}/api/v1/download"
    
    # URL страницы подписки пользователя в Remnawave
    # Берём напрямую из подписки, которая уже содержит полный URL от Remnawave API
    subscription_page_url = subscription_url
    
    return {
        "url": config.bot.mini_app_url or subscription_url,
        "happ_url": happ_redirect_url,
        "download_url": download_url,
        "subscription_url": subscription_page_url,
        "is_app": config.bot.is_mini_app,
    }


@inject
async def devices_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    remnawave_service: FromDishka[RemnawaveService],
    settings_service: FromDishka[SettingsService],
    referral_service: FromDishka[ReferralService],
    extra_device_service: FromDishka[ExtraDeviceService],
    **kwargs: Any,
) -> dict[str, Any]:
    from src.core.enums import ReferralRewardType
    
    subscription = user.current_subscription
    
    # Получаем настройки баланса
    is_balance_enabled = await settings_service.is_balance_enabled()
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    # Получаем данные для профиля (нужны для frg-user)
    referral_balance = await referral_service.get_pending_rewards_amount(
        telegram_id=user.telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )
    display_balance = get_display_balance(user.balance, referral_balance, is_balance_combined)

    # Обрабатываем скидки для frg-user
    from datetime import datetime, timezone
    
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
    
    # Определяем какую скидку показывать
    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
            if not is_temporary_discount:
                is_temporary_discount = True
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary_discount = False
            is_permanent_discount = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
            is_temporary_discount = True
    else:
        discount_value = 0
    
    # Если нет подписки - показываем пустой список устройств с возможностью управления доп. устройствами
    if not subscription:
        return {
            "current_count": 0,
            "max_count": "0",
            "devices": [],
            "devices_empty": True,
            # Данные подписки
            "plan_name": "—",
            "traffic_limit": "—",
            "device_limit_number": 0,
            "device_limit_bonus": 0,
            "extra_devices": 0,
            "expire_time": "—",
            # Флаги для кнопок
            "can_add_device": False,
            "has_subscription": False,
            "show_extra_devices_button": False,
            "is_balance_enabled": 1 if is_balance_enabled else 0,
            "is_balance_separate": 1 if is_balance_separate else 0,
            # Данные профиля для frg-user
            "user_id": str(user.telegram_id),
            "user_name": user.name,
            "discount_value": discount_value,
            "discount_is_temporary": 1 if is_temporary_discount else 0,
            "discount_is_permanent": 1 if is_permanent_discount else 0,
            "discount_remaining": discount_remaining,
            "balance": display_balance,
            "referral_balance": referral_balance,
            "referral_code": user.referral_code,
        }

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
    
    # Добавляем данные подписки для отображения в frg-subscription-devices
    extra_devices = subscription.extra_devices or 0
    plan_device_limit = subscription.plan.device_limit if subscription.plan and subscription.plan.device_limit > 0 else 0
    actual_device_limit = subscription.device_limit
    device_limit_bonus = max(0, actual_device_limit - plan_device_limit - extra_devices) if plan_device_limit > 0 else 0
    
    # Определяем показывать ли кнопку "Управление доп. устройствами"
    # Условия: есть extra_devices > 0 ИЛИ (подписка не триал и не реферальная)
    # ИЛИ есть история покупок доп. устройств (даже если подписка истекла)
    plan_name_lower = subscription.plan.name.lower() if subscription.plan else ""
    is_trial_subscription = subscription.is_trial or "пробн" in plan_name_lower
    is_referral_subscription = "реферал" in plan_name_lower
    
    # Получаем историю покупок доп. устройств
    has_extra_device_purchases = False
    try:
        purchases = await extra_device_service.get_by_subscription(subscription.id)
        has_extra_device_purchases = len(purchases) > 0
    except Exception:
        pass
    
    # Показываем кнопку если:
    # 1. Есть активные extra_devices
    # 2. ИЛИ есть история покупок доп. устройств  
    # 3. ИЛИ подписка активна и это не триал/реферальная подписка
    show_extra_devices_button = (
        extra_devices > 0 
        or has_extra_device_purchases
        or (subscription.is_active and not is_trial_subscription and not is_referral_subscription)
    )

    return {
        "current_count": len(devices),
        "max_count": i18n_format_device_limit(subscription.device_limit),
        "devices": formatted_devices,
        "devices_empty": len(devices) == 0,
        # Данные подписки
        "plan_name": subscription.plan.name if subscription.plan else "Unknown",
        "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
        "device_limit_number": plan_device_limit if plan_device_limit > 0 else subscription.device_limit,
        "device_limit_bonus": device_limit_bonus,
        "extra_devices": extra_devices,
        "expire_time": i18n_format_expire_time(subscription.expire_at),
        # Флаги для кнопок
        "can_add_device": subscription.is_active and subscription.has_devices_limit,
        "has_subscription": True,
        "show_extra_devices_button": show_extra_devices_button,
        "is_balance_enabled": 1 if is_balance_enabled else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,
        # Данные профиля для frg-user
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "balance": display_balance,
        "referral_balance": referral_balance,
        "referral_code": user.referral_code,
    }


@inject
async def invite_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    config: AppConfig,
    i18n: FromDishka[TranslatorRunner],
    settings_service: FromDishka[SettingsService],
    referral_service: FromDishka[ReferralService],
    **kwargs: Any,
) -> dict[str, Any]:
    from datetime import datetime, timezone
    from src.core.enums import ReferralRewardType
    
    settings = await settings_service.get_referral_settings()
    referrals = await referral_service.get_referral_count(user.telegram_id)
    payments = await referral_service.get_reward_count(user.telegram_id)
    ref_link = await referral_service.get_ref_link(user.referral_code)
    support_username = config.bot.support_username.get_secret_value()
    support_link = format_username_to_url(
        support_username, i18n.get("contact-support-withdraw-points")
    )
    
    # Get invite message from settings
    # Replace placeholders with actual values
    try:
        invite_message = str(settings.invite_message) if settings.invite_message else None
    except Exception:
        invite_message = None
    
    if invite_message:
        # Support both Python format {url}/{name} and legacy $url/$name
        # Also support {space} for newline
        invite_message = invite_message.format(url=ref_link, name="VPN", space="\n") if "{url}" in invite_message else invite_message.replace("$url", ref_link).replace("$name", "VPN")
    else:
        invite_message = f"Join us! {ref_link}"
    
    # Get pending referral balance (not issued rewards)
    referral_balance = await referral_service.get_pending_rewards_amount(
        user.telegram_id,
        ReferralRewardType.MONEY,
    )
    
    # Вычисляем максимальную скидку для отображения
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
    
    # Определяем какую скидку показывать (большую)
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
    
    # Prepare subscription data
    subscription = user.current_subscription
    subscription_data = {}
    
    logger.debug(f"🔍 [invite_getter] user={user.telegram_id}: subscription={subscription}, is_active={subscription.is_active if subscription else 'None'}")
    
    if subscription:
        extra_devices = subscription.extra_devices or 0
        # Вычисляем бонус устройств (БЕЗ купленных доп.)
        plan_device_limit = subscription.plan.device_limit if subscription.plan.device_limit > 0 else 0
        actual_device_limit = subscription.device_limit
        device_limit_bonus = max(0, actual_device_limit - plan_device_limit - extra_devices) if plan_device_limit > 0 else 0
        
        subscription_data = {
            "status": subscription.get_status,
            "plan_name": subscription.plan.name,
            "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
            "device_limit": i18n_format_device_limit(plan_device_limit if plan_device_limit > 0 else subscription.device_limit),
            "device_limit_number": plan_device_limit if plan_device_limit > 0 else subscription.device_limit,
            "device_limit_bonus": device_limit_bonus,
            "extra_devices": extra_devices,
            "expire_time": i18n_format_expire_time(subscription.expire_at),
            "is_trial": subscription.is_trial,
            "traffic_strategy": subscription.traffic_limit_strategy,
            "reset_time": subscription.get_expire_time,
        }
    else:
        subscription_data = {
            "status": None,
            "is_trial": False,
            "device_limit_bonus": 0,
        }
    
    # Get total bonus
    total_bonus = await referral_service.get_total_rewards_amount(
        user.telegram_id,
        ReferralRewardType.MONEY,
    )

    # Проверяем режим баланса (раздельный или объединённый)
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined

    # Prepare referral reward display for info text
    max_level = settings.level.value
    reward_config = settings.reward.config
    
    # Format rewards based on level
    from src.core.enums import ReferralLevel
    reward_level_1_value = reward_config.get(ReferralLevel.FIRST, 0)
    reward_level_2_value = reward_config.get(ReferralLevel.SECOND, 0)

    return {
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "referral_code": user.referral_code,
        "balance": get_display_balance(user.balance, referral_balance, is_balance_combined),
        "referral_balance": referral_balance if is_balance_separate else 0,  # Скрываем в режиме COMBINED
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "total_bonus": total_bonus,
        "reward_type": settings.reward.type,
        "referrals": referrals,
        "payments": payments,
        "is_points_reward": settings.reward.is_money,
        "has_balance": (referral_balance > 0) and is_balance_separate,  # Показываем только в режиме SEPARATE
        "is_balance_separate": 1 if is_balance_separate else 0,  # Флаг раздельного режима баланса
        "referral_link": ref_link,
        "invite": invite_message,
        "withdraw": support_link,
        "ref_max_level": max_level,
        "ref_reward_level_1_value": reward_level_1_value,
        "ref_reward_level_2_value": reward_level_2_value,
        "ref_reward_strategy": settings.reward.strategy,
        "ref_reward_type": settings.reward.type,
        **subscription_data,
    }


@inject
async def invite_about_getter(
    dialog_manager: DialogManager,
    i18n: FromDishka[TranslatorRunner],
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    settings = await settings_service.get_referral_settings()
    reward_config = settings.reward.config

    max_level = settings.level.value
    identical_reward = settings.reward.is_identical

    reward_levels: dict[str, str] = {}
    for lvl, val in reward_config.items():
        if lvl.value <= max_level:
            reward_levels[f"reward_level_{lvl.value}"] = i18n.get(
                "msg-invite-reward",
                value=val,
                reward_strategy_type=settings.reward.strategy,
                reward_type=settings.reward.type,
            )

    return {
        **reward_levels,
        "reward_type": settings.reward.type,
        "reward_strategy_type": settings.reward.strategy,
        "accrual_strategy": settings.accrual_strategy,
        "identical_reward": identical_reward,
        "max_level": max_level,
    }


@inject
async def balance_menu_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    plan_service: FromDishka[PlanService],
    subscription_service: FromDishka[SubscriptionService],
    referral_service: FromDishka[ReferralService],
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    from datetime import datetime, timezone
    from src.core.enums import ReferralRewardType
    
    # Определяем, является ли пользователь приглашённым
    referral = await referral_service.get_referral_by_referred(user.telegram_id)
    is_invited = bool(referral)
    
    plan = await plan_service.get_appropriate_trial_plan(user, is_invited=is_invited)
    has_used_trial = await subscription_service.has_used_trial(user.telegram_id)
    settings = await settings_service.get_referral_settings()
    
    # Get referral balance
    referral_balance = await referral_service.get_pending_rewards_amount(
        user.telegram_id,
        ReferralRewardType.MONEY,
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

    # Проверяем, включен ли функционал баланса
    is_balance_enabled = await settings_service.is_balance_enabled()
    
    # Проверяем режим баланса (раздельный или объединённый)
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    # Проверяем, включены ли переводы
    feature_settings = await settings_service.get_feature_settings()
    is_transfers_enabled = feature_settings.transfers.enabled
    
    # В режиме COMBINED показываем сумму основного и бонусного баланса
    display_balance = user.balance + referral_balance if is_balance_combined else user.balance
    
    base_data = {
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "discount_value": discount_value,
        "discount_is_temporary": 1 if is_temporary_discount else 0,
        "discount_is_permanent": 1 if is_permanent_discount else 0,
        "discount_remaining": discount_remaining,
        "balance": display_balance,  # В COMBINED режиме - сумма, в SEPARATE - только основной
        "referral_balance": referral_balance,
        "referral_code": user.referral_code,
        "has_referral_balance": referral_balance > 0 and is_balance_separate,  # Показываем только в режиме SEPARATE
        "is_points_reward": settings.reward.is_money,
        "is_balance_enabled": 1 if is_balance_enabled else 0,
        "is_transfers_enabled": 1 if is_transfers_enabled else 0,
        "is_balance_separate": 1 if is_balance_separate else 0,  # Флаг раздельного режима баланса
    }

    subscription = user.current_subscription

    if not subscription:
        base_data.update(
            {
                "status": None,
                "is_trial": False,
                "trial_available": not has_used_trial and plan,
                "device_limit_bonus": 0,
            }
        )
        return base_data

    extra_devices = subscription.extra_devices or 0
    # Вычисляем бонус устройств (БЕЗ купленных доп.)
    plan_device_limit = subscription.plan.device_limit if subscription.plan.device_limit > 0 else 0
    actual_device_limit = subscription.device_limit
    device_limit_bonus = max(0, actual_device_limit - plan_device_limit - extra_devices) if plan_device_limit > 0 else 0
    
    base_data.update(
        {
            "status": subscription.get_status,
            "plan_name": subscription.plan.name,
            "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
            "device_limit": i18n_format_device_limit(plan_device_limit if plan_device_limit > 0 else subscription.device_limit),
            "device_limit_number": plan_device_limit if plan_device_limit > 0 else subscription.device_limit,
            "device_limit_bonus": device_limit_bonus,
            "extra_devices": extra_devices,
            "expire_time": i18n_format_expire_time(subscription.expire_at),
            "is_trial": subscription.is_trial,
            "traffic_strategy": subscription.traffic_limit_strategy,
            "reset_time": subscription.get_expire_time,
        }
    )

    return base_data


@inject
async def balance_gateways_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    payment_gateway_service: FromDishka[PaymentGatewayService],
    referral_service: FromDishka[ReferralService],
    settings_service: FromDishka[SettingsService],
    i18n: FromDishka[TranslatorRunner],
    **kwargs: Any,
) -> dict[str, Any]:
    from src.core.enums import PaymentGatewayType
    
    gateways = await payment_gateway_service.filter_active()
    
    payment_methods = [
        {
            "gateway_type": gateway.type,
            "name": gateway.type.value,
        }
        for gateway in gateways
        if gateway.type != PaymentGatewayType.BALANCE  # Исключаем оплату с баланса при пополнении баланса
    ]
    
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
    
    # Проверяем, включен ли функционал баланса
    is_balance_enabled = await settings_service.is_balance_enabled()
    is_balance_combined = await settings_service.is_balance_combined()
    is_balance_separate = not is_balance_combined
    
    result = {
        "payment_methods": payment_methods,
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
            "device_limit": i18n_format_device_limit(plan_device_limit if plan_device_limit > 0 else subscription.device_limit),
            "device_limit_number": plan_device_limit if plan_device_limit > 0 else subscription.device_limit,
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
async def balance_amounts_getter(
    dialog_manager: DialogManager,
    payment_gateway_service: FromDishka[PaymentGatewayService],
    **kwargs: Any,
) -> dict[str, Any]:
    from src.core.enums import PaymentGatewayType
    
    gateway_type = dialog_manager.dialog_data.get("selected_gateway")
    currency_symbol = "₽"
    
    # Конвертируем строку в enum если нужно
    if isinstance(gateway_type, str):
        gateway_type_enum = PaymentGatewayType(gateway_type)
    elif gateway_type:
        gateway_type_enum = gateway_type
    else:
        gateway_type_enum = None
    
    # Форматируем название способа оплаты
    if gateway_type_enum == PaymentGatewayType.YOOMONEY:
        gateway_type_formatted = "💳 Банковская карта"
    elif gateway_type_enum == PaymentGatewayType.CRYPTOMUS:
        gateway_type_formatted = "₿ Cryptomus"
    elif gateway_type_enum == PaymentGatewayType.TELEGRAM_STARS:
        gateway_type_formatted = "⭐ Телеграм"
    else:
        gateway_type_formatted = gateway_type_enum.value if gateway_type_enum else "N/A"
    
    if gateway_type_enum:
        gateway = await payment_gateway_service.get_by_type(gateway_type_enum)
        if gateway:
            currency_symbol = gateway.currency.symbol
    
    return {
        "selected_gateway": gateway_type_formatted,
        "currency": currency_symbol,
    }


@inject
async def balance_amount_getter(
    dialog_manager: DialogManager,
    payment_gateway_service: FromDishka[PaymentGatewayService],
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    from src.core.enums import PaymentGatewayType
    
    gateway_type = dialog_manager.dialog_data.get("selected_gateway")
    currency_symbol = "₽"
    
    # Конвертируем строку в enum если нужно
    if isinstance(gateway_type, str):
        gateway_type_enum = PaymentGatewayType(gateway_type)
    elif gateway_type:
        gateway_type_enum = gateway_type
    else:
        gateway_type_enum = None
    
    # Форматируем название способа оплаты
    if gateway_type_enum == PaymentGatewayType.YOOMONEY:
        gateway_type_formatted = "💳 Банковская карта"
    elif gateway_type_enum == PaymentGatewayType.CRYPTOMUS:
        gateway_type_formatted = "₿ Cryptomus"
    elif gateway_type_enum == PaymentGatewayType.TELEGRAM_STARS:
        gateway_type_formatted = "⭐ Телеграм"
    else:
        gateway_type_formatted = gateway_type_enum.value if gateway_type_enum else "N/A"
    
    if gateway_type_enum:
        gateway = await payment_gateway_service.get_by_type(gateway_type_enum)
        if gateway:
            currency_symbol = gateway.currency.symbol
    
    # Получаем настройки min/max для пополнения баланса
    settings = await settings_service.get()
    min_amount = settings.features.balance_min_amount if settings.features.balance_min_amount is not None else 10
    max_amount = settings.features.balance_max_amount if settings.features.balance_max_amount is not None else 100000
    
    return {
        "selected_gateway": gateway_type_formatted,
        "currency": currency_symbol,
        "min_amount": min_amount,
        "max_amount": max_amount,
    }


@inject
async def balance_confirm_getter(
    dialog_manager: DialogManager,
    **kwargs: Any,
) -> dict[str, Any]:
    from src.core.enums import PaymentGatewayType
    
    gateway_type = dialog_manager.dialog_data.get("selected_gateway")
    amount = dialog_manager.dialog_data.get("topup_amount", 0)
    currency = dialog_manager.dialog_data.get("currency")
    payment_url = dialog_manager.dialog_data.get("payment_url", "")
    
    # Конвертируем строку в enum если нужно
    if isinstance(gateway_type, str):
        gateway_type_enum = PaymentGatewayType(gateway_type)
    elif gateway_type:
        gateway_type_enum = gateway_type
    else:
        gateway_type_enum = None
    
    # Форматируем название способа оплаты
    if gateway_type_enum == PaymentGatewayType.YOOMONEY:
        gateway_type_formatted = "💳 Банковская карта"
    elif gateway_type_enum == PaymentGatewayType.CRYPTOMUS:
        gateway_type_formatted = "₿ Cryptomus"
    elif gateway_type_enum == PaymentGatewayType.TELEGRAM_STARS:
        gateway_type_formatted = "⭐ Телеграм"
    else:
        gateway_type_formatted = gateway_type_enum.value if gateway_type_enum else "N/A"
    
    # currency может быть enum или строкой после сериализации
    if hasattr(currency, 'symbol'):
        currency_symbol = currency.symbol
    elif currency == "RUB":
        currency_symbol = "₽"
    elif currency == "USD":
        currency_symbol = "$"
    elif currency == "XTR":
        currency_symbol = "★"
    else:
        currency_symbol = currency or "₽"
    
    return {
        "selected_gateway": gateway_type_formatted,
        "topup_amount": amount,
        "currency": currency_symbol,
        "payment_url": payment_url,
    }


@inject
async def balance_success_getter(
    dialog_manager: DialogManager,
    **kwargs: Any,
) -> dict[str, Any]:
    """Getter for balance success screen."""
    start_data = dialog_manager.start_data or {}
    amount = start_data.get("amount", 0)
    currency = start_data.get("currency", "₽")
    
    return {
        "amount": amount,
        "currency": currency,
    }


@inject
async def bonus_activate_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    referral_service: FromDishka[ReferralService],
    **kwargs: Any,
) -> dict[str, Any]:
    from src.core.enums import ReferralRewardType
    
    # Get pending referral balance (bonuses)
    referral_balance = await referral_service.get_pending_rewards_amount(
        user.telegram_id,
        ReferralRewardType.MONEY,
    )
    
    # Если есть pending изменение суммы, показываем его
    pending_amount = dialog_manager.dialog_data.get("pending_bonus_amount")
    selected_amount = pending_amount if pending_amount else None
    
    # Вычисляем отображаемую сумму для current_bonus_amount
    if selected_amount == "all":
        display_amount = referral_balance
    elif selected_amount:
        display_amount = int(selected_amount)
    else:
        display_amount = 0
    
    return {
        "referral_balance": referral_balance,
        "has_balance": referral_balance > 0,
        "selected_bonus_amount": selected_amount,
        "current_bonus_amount": display_amount,
    }



@inject
async def bonus_activate_custom_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    referral_service: FromDishka[ReferralService],
    **kwargs: Any,
) -> dict[str, Any]:
    from src.core.enums import ReferralRewardType
    
    # Get pending referral balance
    referral_balance = await referral_service.get_pending_rewards_amount(
        user.telegram_id,
        ReferralRewardType.MONEY,
    )
    
    return {
        "referral_balance": referral_balance,
    }


# === Balance Transfer Getters ===


@inject
async def transfer_menu_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    settings_service: FromDishka[SettingsService],
    referral_service: FromDishka[ReferralService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для меню перевода баланса."""
    from src.core.enums import ReferralRewardType
    
    settings = await settings_service.get()
    transfer_settings = settings.features.transfers
    
    # Получаем текущие данные перевода из dialog_data
    transfer_data = dialog_manager.dialog_data.get("transfer_data", {})
    recipient_id = transfer_data.get("recipient_id")
    recipient_name = transfer_data.get("recipient_name")
    transfer_amount = transfer_data.get("amount", 0)
    
    # Получаем referral_balance для расчёта отображаемого баланса
    referral_balance = await referral_service.get_pending_rewards_amount(
        user.telegram_id,
        ReferralRewardType.MONEY,
    )
    is_balance_combined = await settings_service.is_balance_combined()
    
    # Формируем описание комиссии
    if transfer_settings.commission_type == "percent":
        commission_display = f"{int(transfer_settings.commission_value)}%"
    else:
        commission_display = f"{int(transfer_settings.commission_value)} ₽"
    
    # Формируем отображение получателя (в основном тексте)
    if recipient_id and recipient_name:
        recipient_display = f"<b>{recipient_name}</b> (<code>{recipient_id}</code>)"
    else:
        recipient_display = "<i>Не назначено</i>"
    
    # Для основного текста и кнопки - используем числовое значение
    # 0 означает "не назначено", любое другое число - назначенная сумма
    amount_display = int(transfer_amount) if transfer_amount else 0
    
    # Вычисляем комиссию для текущей суммы перевода
    transfer_commission = 0
    if transfer_amount > 0:
        if transfer_settings.commission_type == "percent":
            transfer_commission = int(transfer_amount * transfer_settings.commission_value / 100)
        else:
            transfer_commission = int(transfer_settings.commission_value)
    
    # Формируем отображение сообщения с экранированием HTML
    message = transfer_data.get("message", "")
    if message:
        # Экранируем HTML-специальные символы для безопасного отображения
        escaped_message = html.escape(message)
        message_display = f"<i>{escaped_message}</i>"
    else:
        message_display = "<i>Не назначено</i>"
    
    return {
        "balance": get_display_balance(user.balance, referral_balance, is_balance_combined),
        "commission_display": commission_display,
        "recipient_display": recipient_display,
        "amount_display": amount_display,
        "transfer_commission": transfer_commission,
        "message_display": message_display,
    }


@inject
async def transfer_recipient_getter(
    dialog_manager: DialogManager,
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна ввода получателя."""
    return {}


@inject
async def transfer_recipient_history_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    balance_transfer_service: FromDishka[BalanceTransferService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна истории получателей переводов."""
    # Получаем историю уникальных получателей переводов
    recipients = await balance_transfer_service.get_transfer_recipients(
        sender_telegram_id=user.telegram_id,
        limit=20,
    )
    
    # Формируем список для отображения
    recipients_data = [
        {
            "telegram_id": r.telegram_id,
            "name": r.name or f"ID: {r.telegram_id}",
            "username": r.username,
        }
        for r in recipients
    ]
    
    return {
        "recipients": recipients_data,
        "has_recipients": len(recipients_data) > 0,
    }


@inject
async def transfer_amount_value_getter(
    dialog_manager: DialogManager,
    user: UserDto,
    settings_service: FromDishka[SettingsService],
    referral_service: FromDishka[ReferralService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна выбора суммы перевода."""
    from src.core.enums import ReferralRewardType
    
    settings = await settings_service.get()
    transfer_settings = settings.features.transfers
    
    # Получаем данные из dialog_data
    transfer_data = dialog_manager.dialog_data.get("transfer_data", {})
    current_amount = transfer_data.get("amount", 0)  # Текущая назначенная сумма
    pending_amount = transfer_data.get("pending_amount")  # Выбранная, но не принятая сумма
    
    # Получаем referral_balance для расчёта отображаемого баланса
    referral_balance = await referral_service.get_pending_rewards_amount(
        user.telegram_id,
        ReferralRewardType.MONEY,
    )
    is_balance_combined = await settings_service.is_balance_combined()
    
    # current_display - текущая назначенная сумма
    current_display = f"{int(current_amount)} ₽" if current_amount else "Не назначено"
    
    # selected_display - выбранная сумма (если есть pending, иначе текущая)
    display_amount = pending_amount if pending_amount is not None else current_amount
    selected_display = f"{int(display_amount)} ₽" if display_amount else "Не назначено"
    
    # Создаем selected значения для всех кнопок (подсветка для pending или current)
    result = {
        "balance": get_display_balance(user.balance, referral_balance, is_balance_combined),
        "min_amount": transfer_settings.min_amount if transfer_settings.min_amount else 0,
        "max_amount": transfer_settings.max_amount if transfer_settings.max_amount else 999999,
        "current_display": current_display,
        "selected_display": selected_display,
    }
    
    # Добавляем selected для preset кнопок
    for amount in [100, 250, 500, 1000, 2000, 5000]:
        result[f"amount_{amount}_selected"] = 1 if display_amount == amount else 0
    
    return result


@inject
async def transfer_amount_manual_getter(
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна ручного ввода суммы."""
    settings = await settings_service.get()
    transfer_settings = settings.features.transfers
    
    return {
        "min_amount": transfer_settings.min_amount if transfer_settings.min_amount else 0,
        "max_amount": transfer_settings.max_amount if transfer_settings.max_amount else 999999,
    }


@inject
async def transfer_message_getter(
    dialog_manager: DialogManager,
    **kwargs: Any,
) -> dict[str, Any]:
    """Геттер для окна ввода сообщения."""
    transfer_data = dialog_manager.dialog_data.get("transfer_data", {})
    message = transfer_data.get("message", "")
    
    if message:
        # Экранируем HTML-специальные символы для безопасного отображения
        escaped_message = html.escape(message)
        message_display = f"<i>{escaped_message}</i>"
    else:
        message_display = "<i>Не назначено</i>"
    
    return {
        "message_display": message_display,
    }

