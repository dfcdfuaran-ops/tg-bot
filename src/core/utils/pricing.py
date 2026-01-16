"""Pricing utility functions for subscription calculations."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Tuple

# Минимальное количество дней для оплаты дополнительных устройств
MIN_EXTRA_DEVICE_DAYS = 10


def calculate_prorated_device_price(
    monthly_price: int,
    subscription_expire_at: datetime,
    min_days: int = MIN_EXTRA_DEVICE_DAYS,
) -> int:
    """
    Вычисляет пропорциональную стоимость дополнительного устройства
    на основе оставшихся дней до окончания подписки.
    
    Args:
        monthly_price: Полная месячная стоимость устройства в рублях
        subscription_expire_at: Дата окончания текущей подписки
        min_days: Минимальное количество дней для оплаты (по умолчанию 10)
    
    Returns:
        Пропорциональная стоимость за оставшиеся дни (минимум за min_days дней)
    
    Formula:
        (monthly_price / 30) * max(remaining_days, min_days)
    """
    now = datetime.now(timezone.utc)
    
    # Если подписка уже истекла, возвращаем полную цену
    if subscription_expire_at <= now:
        return monthly_price
    
    # Вычисляем оставшиеся дни (округляем вверх)
    remaining_delta = subscription_expire_at - now
    remaining_days = remaining_delta.days + (1 if remaining_delta.seconds > 0 else 0)
    
    # Если меньше дня - считаем как 1 день
    if remaining_days < 1:
        remaining_days = 1
    
    # Применяем минимум дней
    billable_days = max(remaining_days, min_days)
    
    # Вычисляем пропорциональную стоимость
    # Используем Decimal для точных вычислений
    daily_price = Decimal(monthly_price) / Decimal(30)
    prorated_price = daily_price * Decimal(billable_days)
    
    # Округляем до целого числа (вверх, чтобы не терять копейки)
    return int(prorated_price.quantize(Decimal("1"), rounding="ROUND_HALF_UP"))


def calculate_device_price_until_subscription_end(
    monthly_price: int,
    subscription_expire_at: datetime,
    min_days: int = MIN_EXTRA_DEVICE_DAYS,
) -> Tuple[int, int]:
    """
    Вычисляет стоимость дополнительного устройства до конца подписки.
    
    Args:
        monthly_price: Полная месячная стоимость устройства в рублях
        subscription_expire_at: Дата окончания текущей подписки
        min_days: Минимальное количество дней для оплаты
    
    Returns:
        Tuple[int, int]: (стоимость, количество дней)
    """
    now = datetime.now(timezone.utc)
    
    # Если подписка уже истекла
    if subscription_expire_at <= now:
        return monthly_price, 30
    
    # Вычисляем оставшиеся дни
    remaining_delta = subscription_expire_at - now
    remaining_days = remaining_delta.days + (1 if remaining_delta.seconds > 0 else 0)
    
    if remaining_days < 1:
        remaining_days = 1
    
    # Применяем минимум дней
    billable_days = max(remaining_days, min_days)
    
    # Вычисляем стоимость
    daily_price = Decimal(monthly_price) / Decimal(30)
    price = daily_price * Decimal(billable_days)
    
    return int(price.quantize(Decimal("1"), rounding="ROUND_HALF_UP")), billable_days


def calculate_device_price_until_month_end(
    monthly_price: int,
    subscription_expire_at: datetime,
    min_days: int = MIN_EXTRA_DEVICE_DAYS,
) -> Tuple[int, int]:
    """
    Вычисляет стоимость дополнительного устройства до конца текущего месяца подписки.
    
    "Месяц подписки" - это период от expire_at минус N*30 дней до expire_at.
    Например, если подписка истекает 15 марта, месяцы подписки:
    - 15 янв - 15 фев (1-й месяц)
    - 15 фев - 15 мар (2-й месяц)
    
    Args:
        monthly_price: Полная месячная стоимость устройства в рублях
        subscription_expire_at: Дата окончания текущей подписки
        min_days: Минимальное количество дней для оплаты
    
    Returns:
        Tuple[int, int]: (стоимость, количество дней до конца месяца)
    """
    now = datetime.now(timezone.utc)
    
    # Если подписка уже истекла
    if subscription_expire_at <= now:
        return monthly_price, 30
    
    # Вычисляем полные оставшиеся дни до конца подписки
    remaining_delta = subscription_expire_at - now
    total_remaining_days = remaining_delta.days + (1 if remaining_delta.seconds > 0 else 0)
    
    if total_remaining_days < 1:
        total_remaining_days = 1
    
    # Находим конец текущего "месяца подписки"
    # Это ближайшая дата, которая = expire_at - N*30 дней, где N >= 0
    # и эта дата >= now
    
    # Количество полных 30-дневных периодов, оставшихся до expire_at
    full_months_remaining = total_remaining_days // 30
    
    # Дней до конца текущего месяца = остаток от деления на 30
    # Но если остаток 0, значит мы ровно на границе месяца, берём 30
    days_in_current_month = total_remaining_days % 30
    if days_in_current_month == 0:
        days_in_current_month = 30
    
    # Применяем минимум дней
    billable_days = max(days_in_current_month, min_days)
    
    # Вычисляем стоимость
    daily_price = Decimal(monthly_price) / Decimal(30)
    price = daily_price * Decimal(billable_days)
    
    return int(price.quantize(Decimal("1"), rounding="ROUND_HALF_UP")), billable_days


def get_remaining_days(expire_at: datetime) -> int:
    """
    Возвращает количество оставшихся дней до истечения срока.
    
    Args:
        expire_at: Дата истечения
    
    Returns:
        Количество дней (минимум 0)
    """
    now = datetime.now(timezone.utc)
    
    if expire_at <= now:
        return 0
    
    remaining_delta = expire_at - now
    remaining_days = remaining_delta.days + (1 if remaining_delta.seconds > 0 else 0)
    
    return max(0, remaining_days)
