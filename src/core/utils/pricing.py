"""Pricing utility functions for subscription calculations."""

from datetime import datetime, timezone
from decimal import Decimal


def calculate_prorated_device_price(
    monthly_price: int,
    subscription_expire_at: datetime,
) -> int:
    """
    Вычисляет пропорциональную стоимость дополнительного устройства
    на основе оставшихся дней до окончания подписки.
    
    Args:
        monthly_price: Полная месячная стоимость устройства в рублях
        subscription_expire_at: Дата окончания текущей подписки
    
    Returns:
        Пропорциональная стоимость за оставшиеся дни (минимум 0)
    
    Formula:
        (monthly_price / 30) * remaining_days
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
    
    # Вычисляем пропорциональную стоимость
    # Используем Decimal для точных вычислений
    daily_price = Decimal(monthly_price) / Decimal(30)
    prorated_price = daily_price * Decimal(remaining_days)
    
    # Округляем до целого числа (вверх, чтобы не терять копейки)
    return int(prorated_price.quantize(Decimal("1"), rounding="ROUND_HALF_UP"))


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
