"""
Helper functions for dialog getters to reduce code duplication.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from src.core.enums import ReferralRewardType
from src.core.utils.formatters import (
    i18n_format_device_limit,
    i18n_format_expire_time,
    i18n_format_traffic_limit,
)
from src.infrastructure.database.models.dto import UserDto
from src.services.referral import ReferralService


@dataclass
class DiscountInfo:
    """User discount information."""
    discount_value: int
    discount_remaining: int
    is_temporary: bool
    is_permanent: bool


@dataclass
class DeviceLimitInfo:
    """Device limit information for subscription."""
    device_limit_number: int
    extra_devices: int


def calculate_user_discount(user: UserDto) -> DiscountInfo:
    """
    Calculate user's effective discount value and type.
    
    Args:
        user: User DTO with discount information
        
    Returns:
        DiscountInfo with calculated discount values
    """
    purchase_disc = user.purchase_discount if user.purchase_discount is not None else 0
    personal_disc = user.personal_discount if user.personal_discount is not None else 0
    discount_remaining = 0
    is_temporary = False
    is_permanent = False

    # Check purchase discount expiration
    if purchase_disc > 0 and user.purchase_discount_expires_at is not None:
        now = datetime.now(timezone.utc)
        if user.purchase_discount_expires_at <= now:
            purchase_disc = 0
        else:
            remaining = user.purchase_discount_expires_at - now
            discount_remaining = remaining.days + (1 if remaining.seconds > 0 else 0)
            is_temporary = True

    # Determine which discount to use
    if purchase_disc > 0 or personal_disc > 0:
        if purchase_disc > personal_disc:
            discount_value = purchase_disc
        elif personal_disc > 0:
            discount_value = personal_disc
            is_temporary = False
            is_permanent = True
            discount_remaining = 0
        else:
            discount_value = purchase_disc
    else:
        discount_value = 0

    return DiscountInfo(
        discount_value=discount_value,
        discount_remaining=discount_remaining,
        is_temporary=is_temporary,
        is_permanent=is_permanent,
    )


def build_user_profile_data(
    user: UserDto,
    discount_info: DiscountInfo,
    referral_balance: int,
    is_balance_enabled: bool = True,
) -> dict[str, Any]:
    """
    Build user profile data dictionary for template rendering.
    
    Args:
        user: User DTO
        discount_info: Calculated discount information
        referral_balance: User's referral balance
        is_balance_enabled: Whether balance feature is enabled
        
    Returns:
        Dictionary with user profile data for templates
    """
    return {
        "user_id": str(user.telegram_id),
        "user_name": user.name,
        "referral_code": user.referral_code,
        "discount_value": discount_info.discount_value,
        "discount_is_temporary": 1 if discount_info.is_temporary else 0,
        "discount_is_permanent": 1 if discount_info.is_permanent else 0,
        "discount_remaining": discount_info.discount_remaining,
        "balance": user.balance,
        "referral_balance": referral_balance,
        "is_balance_enabled": 1 if is_balance_enabled else 0,
    }


def build_subscription_data(user: UserDto) -> dict[str, Any]:
    """
    Build subscription data dictionary for template rendering.
    
    Args:
        user: User DTO with current_subscription
        
    Returns:
        Dictionary with subscription data for templates
    """
    subscription = user.current_subscription
    if subscription:
        extra_devices = subscription.extra_devices or 0
        plan_device_limit = subscription.plan.device_limit if subscription.plan and subscription.plan.device_limit > 0 else 0
        device_limit_bonus = max(0, subscription.device_limit - plan_device_limit - extra_devices) if plan_device_limit > 0 else 0
        return {
            "has_subscription": "true",
            "current_plan_name": subscription.plan.name,
            "plan_name": subscription.plan.name,
            "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
            "device_limit": i18n_format_device_limit(subscription.device_limit),
            "device_limit_number": plan_device_limit if plan_device_limit > 0 else subscription.device_limit,
            "device_limit_bonus": device_limit_bonus,
            "extra_devices": extra_devices,
            "expire_time": i18n_format_expire_time(subscription.expire_at),
        }
    else:
        return {
            "has_subscription": "false",
            "current_plan_name": "",
            "plan_name": "",
            "traffic_limit": "",
            "device_limit": "",
            "device_limit_number": 0,
            "device_limit_bonus": 0,
            "extra_devices": 0,
            "expire_time": "",
        }


def get_device_limits(user: UserDto) -> DeviceLimitInfo:
    """
    Calculate device limit information for a user's subscription.
    
    Args:
        user: User DTO with current_subscription
        
    Returns:
        DeviceLimitInfo with calculated values
    """
    subscription = user.current_subscription
    if subscription:
        extra_devices = subscription.extra_devices or 0
        device_limit_number = subscription.plan.device_limit
        return DeviceLimitInfo(
            device_limit_number=device_limit_number,
            extra_devices=extra_devices,
        )
    return DeviceLimitInfo(device_limit_number=0, extra_devices=0)


async def get_user_referral_balance(
    referral_service: ReferralService,
    telegram_id: int,
) -> int:
    """
    Get user's pending referral rewards amount.
    
    Args:
        referral_service: Referral service instance
        telegram_id: User's telegram ID
        
    Returns:
        Pending rewards amount
    """
    return await referral_service.get_pending_rewards_amount(
        telegram_id=telegram_id,
        reward_type=ReferralRewardType.MONEY,
    )


def build_common_getter_data(
    user: UserDto,
    referral_balance: int,
    is_balance_enabled: bool = True,
) -> dict[str, Any]:
    """
    Build common data used in most getters - combines user profile and subscription data.
    
    Args:
        user: User DTO
        referral_balance: User's referral balance
        is_balance_enabled: Whether balance feature is enabled
        
    Returns:
        Dictionary with combined user and subscription data
    """
    discount_info = calculate_user_discount(user)
    
    result = build_user_profile_data(
        user=user,
        discount_info=discount_info,
        referral_balance=referral_balance,
        is_balance_enabled=is_balance_enabled,
    )
    
    result.update(build_subscription_data(user))
    
    return result
