from decimal import ROUND_DOWN, Decimal, InvalidOperation
from typing import Optional, Literal

from loguru import logger

from src.core.enums import Currency
from src.infrastructure.database.models.dto import PriceDetailsDto, UserDto, GlobalDiscountSettingsDto

from .base import BaseService


PriceContext = Literal["subscription", "extra_devices", "transfer_commission"]


class PricingService(BaseService):
    def calculate(
        self, 
        user: UserDto, 
        price: Decimal, 
        currency: Currency,
        global_discount: Optional[GlobalDiscountSettingsDto] = None,
        context: PriceContext = "subscription",
    ) -> PriceDetailsDto:
        logger.debug(
            f"Calculating price for amount '{price}' and currency "
            f"'{currency}' for user '{user.telegram_id}', context='{context}'"
        )

        if price <= 0:
            logger.debug("Price is zero, returning without discount")
            return PriceDetailsDto(
                original_amount=Decimal(0),
                final_amount=Decimal(0),
            )

        original_price = price
        global_discount_applied = Decimal(0)
        personal_discount_percent = min(user.purchase_discount or user.personal_discount or 0, 100)
        
        # Проверяем, применяется ли глобальная скидка к данному контексту
        should_apply_global = False
        if global_discount and global_discount.enabled and global_discount.discount_value > 0:
            if context == "subscription" and global_discount.apply_to_subscription:
                should_apply_global = True
            elif context == "extra_devices" and global_discount.apply_to_extra_devices:
                should_apply_global = True
            elif context == "transfer_commission" and global_discount.apply_to_transfer_commission:
                should_apply_global = True
        
        # Вычисляем размер глобальной скидки в процентах (для сравнения)
        global_discount_percent = Decimal(0)
        if should_apply_global:
            if global_discount.discount_type == "percent":
                global_discount_percent = Decimal(global_discount.discount_value)
            else:
                # Для фиксированной скидки вычисляем эквивалентный процент
                if price > 0:
                    global_discount_percent = (Decimal(global_discount.discount_value) / price) * 100
        
        # Определяем режим применения скидок
        if should_apply_global and global_discount.stack_discounts:
            # Режим складывания: применяем обе скидки
            logger.debug(f"Stack mode: applying both discounts (global + personal)")
            
            # Применяем глобальную скидку
            if global_discount.discount_type == "percent":
                global_discount_amount = price * Decimal(global_discount.discount_value) / Decimal(100)
            else:
                global_discount_amount = min(Decimal(global_discount.discount_value), price)
            
            price_after_global = price - global_discount_amount
            if price_after_global < 0:
                price_after_global = Decimal(0)
            global_discount_applied = global_discount_amount
            
            # Затем применяем персональную скидку к оставшейся сумме
            if personal_discount_percent > 0 and price_after_global > 0:
                personal_discount_amount = price_after_global * Decimal(personal_discount_percent) / Decimal(100)
                final_price = price_after_global - personal_discount_amount
            else:
                final_price = price_after_global
                
        elif should_apply_global:
            # Режим максимальной скидки: используем большую из двух
            logger.debug(f"Max mode: global={global_discount_percent}%, personal={personal_discount_percent}%")
            
            if global_discount_percent >= personal_discount_percent:
                # Используем глобальную скидку
                if global_discount.discount_type == "percent":
                    global_discount_amount = price * Decimal(global_discount.discount_value) / Decimal(100)
                else:
                    global_discount_amount = min(Decimal(global_discount.discount_value), price)
                
                final_price = price - global_discount_amount
                global_discount_applied = global_discount_amount
                personal_discount_percent = 0  # Не применяем персональную
                logger.debug(f"Using global discount: -{global_discount_amount}")
            else:
                # Используем персональную скидку
                final_price = price * (Decimal(100) - Decimal(personal_discount_percent)) / Decimal(100)
                logger.debug(f"Using personal discount: {personal_discount_percent}%")
        else:
            # Глобальная скидка не применяется к этому контексту
            # Применяем только персональную скидку
            if personal_discount_percent > 0:
                final_price = price * (Decimal(100) - Decimal(personal_discount_percent)) / Decimal(100)
            else:
                final_price = price
        
        # Не допускаем отрицательной цены
        if final_price < 0:
            final_price = Decimal(0)
        
        # Применяем правила валюты
        final_amount = self.apply_currency_rules(final_price, currency) if final_price > 0 else Decimal(0)

        # Пересчитываем общий процент скидки от оригинальной цены
        if original_price > 0 and final_amount < original_price:
            total_discount_percent = int((1 - final_amount / original_price) * 100)
        else:
            total_discount_percent = 0

        if final_amount >= original_price:
            total_discount_percent = 0
            final_amount = original_price

        logger.info(
            f"Price calculated: original='{original_price}', "
            f"global_discount='{global_discount_applied}', "
            f"personal_discount_percent='{personal_discount_percent}', "
            f"total_discount_percent='{total_discount_percent}', "
            f"final='{final_amount}', context='{context}'"
        )

        return PriceDetailsDto(
            original_amount=original_price,
            discount_percent=total_discount_percent,
            final_amount=final_amount,
            global_discount_amount=global_discount_applied,
        )

    def parse_price(self, input_price: str, currency: Currency) -> Decimal:
        logger.debug(f"Parsing input price '{input_price}' for currency '{currency}'")
        try:
            price = Decimal(input_price.strip())
        except InvalidOperation:
            raise ValueError(f"Invalid numeric format provided for price: '{input_price}'")

        if price < 0:
            raise ValueError(f"Negative price provided: '{input_price}'")
        if price == 0:
            return Decimal(0)

        final_price = self.apply_currency_rules(price, currency)
        logger.debug(f"Parsed price '{final_price}' after applying currency rules")
        return final_price

    def apply_currency_rules(self, amount: Decimal, currency: Currency) -> Decimal:
        """Apply currency-specific formatting rules without enforcing payment gateway minimums."""
        logger.debug(f"Applying currency rules for amount '{amount}' and currency '{currency}'")

        match currency:
            case Currency.XTR | Currency.RUB:
                # Round down to nearest integer for RUB and Telegram Stars
                amount = amount.to_integral_value(rounding=ROUND_DOWN)
                min_amount = Decimal(1)
            case _:
                # Round to 2 decimal places for other currencies (USD, EUR, etc.)
                amount = amount.quantize(Decimal("0.01"))
                min_amount = Decimal("0.01")

        if amount < min_amount:
            logger.debug(f"Amount '{amount}' less than min '{min_amount}', adjusting")
            amount = min_amount

        logger.debug(f"Final amount after currency rules: '{amount}'")
        return amount

    def convert_currency(
        self, 
        amount_rub: Decimal, 
        target_currency: Currency,
        usd_rate: float = 90.0,
        eur_rate: float = 100.0,
        stars_rate: float = 1.5,
    ) -> Decimal:
        """Конвертирует сумму в рублях в указанную валюту."""
        logger.debug(f"Converting {amount_rub} RUB to {target_currency}")
        
        if amount_rub <= 0:
            return Decimal(0)
        
        match target_currency:
            case Currency.RUB:
                result = amount_rub
            case Currency.USD:
                result = amount_rub / Decimal(str(usd_rate))
            case Currency.EUR:
                result = amount_rub / Decimal(str(eur_rate))
            case Currency.XTR:
                result = amount_rub / Decimal(str(stars_rate))
            case _:
                result = amount_rub
        
        result = self.apply_currency_rules(result, target_currency)
        logger.debug(f"Converted amount: {result} {target_currency}")
        return result

    def convert_to_rub(
        self,
        amount: Decimal,
        source_currency: Currency,
        usd_rate: float = 90.0,
        eur_rate: float = 100.0,
        stars_rate: float = 1.5,
    ) -> Decimal:
        """Конвертирует сумму из указанной валюты в рубли."""
        logger.debug(f"Converting {amount} {source_currency} to RUB")
        
        if amount <= 0:
            return Decimal(0)
        
        match source_currency:
            case Currency.RUB:
                result = amount
            case Currency.USD:
                result = amount * Decimal(str(usd_rate))
            case Currency.EUR:
                result = amount * Decimal(str(eur_rate))
            case Currency.XTR:
                result = amount * Decimal(str(stars_rate))
            case _:
                result = amount
        
        result = result.to_integral_value(rounding=ROUND_DOWN)
        logger.debug(f"Converted amount: {result} RUB")
        return result
