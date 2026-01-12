from typing import Any

from aiogram import Bot
from fluentogram import TranslatorHub
from loguru import logger
from redis.asyncio import Redis

from src.core.config import AppConfig
from src.core.constants import TIME_10M
from src.core.enums import AccessMode, Currency, SystemNotificationType, UserNotificationType
from src.core.storage.key_builder import build_key
from src.core.utils.types import AnyNotification
from src.infrastructure.database import UnitOfWork
from src.infrastructure.database.models.dto import ExtraDeviceSettingsDto, FeatureSettingsDto, ReferralSettingsDto, SettingsDto
from src.infrastructure.database.models.sql import Settings
from src.infrastructure.redis import RedisRepository
from src.infrastructure.redis.cache import redis_cache

from .base import BaseService


class SettingsService(BaseService):
    uow: UnitOfWork

    def __init__(
        self,
        config: AppConfig,
        bot: Bot,
        redis_client: Redis,
        redis_repository: RedisRepository,
        translator_hub: TranslatorHub,
        #
        uow: UnitOfWork,
    ) -> None:
        super().__init__(config, bot, redis_client, redis_repository, translator_hub)
        self.uow = uow

    async def create(self) -> SettingsDto:
        settings = SettingsDto()
        db_settings = Settings(**settings.prepare_init_data())
        db_settings = await self.uow.repository.settings.create(db_settings)

        await self._clear_cache()
        logger.info("Default settings created in DB")
        return SettingsDto.from_model(db_settings)  # type: ignore[return-value]

    @redis_cache(prefix="get_settings", ttl=TIME_10M)
    async def get(self) -> SettingsDto:
        db_settings = await self.uow.repository.settings.get()
        if not db_settings:
            return await self.create()
        else:
            logger.debug("Retrieved settings from DB")

        return SettingsDto.from_model(db_settings)  # type: ignore[return-value]

    async def update(self, settings: SettingsDto) -> SettingsDto:
        if settings.user_notifications.changed_data:
            settings.user_notifications = settings.user_notifications  # FIXME: Fix this shit

        if settings.system_notifications.changed_data:
            settings.system_notifications = settings.system_notifications

        if settings.referral.changed_data or settings.referral.reward:
            settings.referral = settings.referral

        if settings.features.changed_data:
            settings.features = settings.features
        
        # Проверяем вложенные объекты в features
        if settings.features.currency_rates.changed_data:
            settings.features = settings.features

        changed_data = settings.prepare_changed_data()
        db_updated_settings = await self.uow.repository.settings.update(**changed_data)
        await self._clear_cache()

        if changed_data:
            logger.info("Settings updated in DB")
        else:
            logger.warning("Settings update called, but no fields were actually changed")

        return SettingsDto.from_model(db_updated_settings)  # type: ignore[return-value]

    #

    async def is_rules_required(self) -> bool:
        settings = await self.get()
        return settings.rules_required

    async def is_channel_required(self) -> bool:
        settings = await self.get()
        return settings.channel_required

    #

    async def get_access_mode(self) -> AccessMode:
        settings = await self.get()
        mode = settings.access_mode
        logger.debug(f"Retrieved access mode '{mode}'")
        return mode

    async def set_access_mode(self, mode: AccessMode) -> None:
        settings = await self.get()
        settings.access_mode = mode
        await self.update(settings)
        logger.debug(f"Set access mode '{mode}'")

    #

    async def get_default_currency(self) -> Currency:
        settings = await self.get()
        currency = settings.default_currency
        logger.debug(f"Retrieved default currency '{currency}'")
        return currency

    async def set_default_currency(self, currency: Currency) -> None:
        settings = await self.get()
        settings.default_currency = currency
        await self.update(settings)
        logger.debug(f"Set default currency '{currency}'")

    #

    async def toggle_notification(self, notification_type: AnyNotification) -> bool:
        settings = await self.get()
        field_name = notification_type.value.lower()

        if isinstance(notification_type, UserNotificationType):
            current_value = getattr(settings.user_notifications, field_name, False)
            setattr(settings.user_notifications, field_name, not current_value)
            new_value = not current_value
        elif isinstance(notification_type, SystemNotificationType):
            current_value = getattr(settings.system_notifications, field_name, False)
            setattr(settings.system_notifications, field_name, not current_value)
            new_value = not current_value
        else:
            raise ValueError(f"Unknown notification type: '{notification_type}'")

        await self.update(settings)
        logger.debug(f"Toggled notification '{field_name}' -> '{new_value}'")
        return new_value

    async def is_notification_enabled(self, ntf_type: AnyNotification) -> bool:
        settings = await self.get()

        if isinstance(ntf_type, UserNotificationType):
            return settings.user_notifications.is_enabled(ntf_type)
        elif isinstance(ntf_type, SystemNotificationType):
            return settings.system_notifications.is_enabled(ntf_type)
        else:
            logger.critical(f"Unknown notification type: '{ntf_type}'")
            return False

    async def list_user_notifications(self) -> list[dict[str, Any]]:
        settings = await self.get()
        return [
            {
                "type": field.upper(),
                "enabled": value,
            }
            for field, value in settings.user_notifications.model_dump().items()
        ]

    async def list_system_notifications(self) -> list[dict[str, Any]]:
        settings = await self.get()
        return [
            {
                "type": field.upper(),
                "enabled": value,
            }
            for field, value in settings.system_notifications.model_dump().items()
        ]

    #

    async def get_referral_settings(self) -> ReferralSettingsDto:
        settings = await self.get()
        return settings.referral

    async def is_referral_enable(self) -> bool:
        settings = await self.get()
        return settings.referral.enable

    #

    async def get_feature_settings(self) -> FeatureSettingsDto:
        settings = await self.get()
        return settings.features

    async def is_community_enabled(self) -> bool:
        settings = await self.get()
        return settings.features.community_enabled

    async def is_tos_enabled(self) -> bool:
        settings = await self.get()
        return settings.features.tos_enabled

    async def is_balance_enabled(self) -> bool:
        settings = await self.get()
        return settings.features.balance_enabled

    async def get_balance_mode(self) -> "BalanceMode":
        """Get balance mode (COMBINED or SEPARATE)."""
        from src.core.enums import BalanceMode
        settings = await self.get()
        return settings.features.balance_mode

    async def is_balance_combined(self) -> bool:
        """Check if balance mode is COMBINED (no separate bonus balance)."""
        from src.core.enums import BalanceMode
        settings = await self.get()
        return settings.features.balance_mode == BalanceMode.COMBINED

    async def toggle_feature(self, feature_name: str) -> bool:
        """Toggle a feature setting. Returns the new value."""
        settings = await self.get()
        current_value = getattr(settings.features, feature_name, False)
        setattr(settings.features, feature_name, not current_value)
        settings.features = settings.features  # Trigger change tracking
        await self.update(settings)
        logger.debug(f"Toggled feature '{feature_name}' -> '{not current_value}'")
        return not current_value

    #
    
    async def get_extra_device_settings(self) -> ExtraDeviceSettingsDto:
        """Get extra device settings."""
        settings = await self.get()
        return settings.features.extra_devices
    
    async def is_extra_devices_enabled(self) -> bool:
        """Check if extra devices feature is enabled."""
        settings = await self.get()
        return settings.features.extra_devices.enabled
    
    async def get_extra_device_price(self) -> int:
        """Get price per extra device per month."""
        settings = await self.get()
        return settings.features.extra_devices.price_per_device
    
    async def toggle_extra_devices(self) -> bool:
        """Toggle extra devices feature. Returns new value."""
        settings = await self.get()
        new_value = not settings.features.extra_devices.enabled
        settings.features.extra_devices.enabled = new_value
        settings.features = settings.features  # Trigger change tracking
        await self.update(settings)
        logger.debug(f"Toggled extra_devices enabled -> '{new_value}'")
        return new_value
    
    async def set_extra_device_price(self, price: int) -> None:
        """Set price per extra device per month."""
        settings = await self.get()
        settings.features.extra_devices.price_per_device = price
        settings.features = settings.features  # Trigger change tracking
        await self.update(settings)
        logger.debug(f"Set extra_device price -> '{price}'")

    async def toggle_extra_devices_payment_type(self) -> bool:
        """Toggle extra devices payment type (one-time vs monthly). Returns new is_one_time value."""
        settings = await self.get()
        new_value = not settings.features.extra_devices.is_one_time
        settings.features.extra_devices.is_one_time = new_value
        settings.features = settings.features  # Trigger change tracking
        await self.update(settings)
        logger.debug(f"Toggled extra_devices is_one_time -> '{new_value}'")
        return new_value

    async def is_extra_devices_one_time(self) -> bool:
        """Check if extra devices are paid one-time (vs monthly)."""
        settings = await self.get()
        return settings.features.extra_devices.is_one_time

    # === Transfers Settings ===

    async def toggle_transfers(self) -> bool:
        """Toggle transfers feature. Returns new value."""
        settings = await self.get()
        new_value = not settings.features.transfers.enabled
        settings.features.transfers.enabled = new_value
        settings.features = settings.features  # Trigger change tracking
        await self.update(settings)
        logger.debug(f"Toggled transfers enabled -> '{new_value}'")
        return new_value

    async def get_transfer_settings(self):
        """Get transfer settings."""
        settings = await self.get()
        return settings.features.transfers

    async def is_transfers_enabled(self) -> bool:
        """Check if transfers feature is enabled."""
        settings = await self.get()
        return settings.features.transfers.enabled

    async def update_transfer_settings(
        self,
        enabled: bool | None = None,
        commission_type: str | None = None,
        commission_value: float | None = None,
        min_amount: float | None = None,
        max_amount: float | None = None,
    ) -> None:
        """Update transfer settings."""
        settings = await self.get()
        
        if enabled is not None:
            settings.features.transfers.enabled = enabled
        if commission_type is not None:
            settings.features.transfers.commission_type = commission_type
        if commission_value is not None:
            settings.features.transfers.commission_value = commission_value
        if min_amount is not None:
            settings.features.transfers.min_amount = min_amount
        if max_amount is not None:
            settings.features.transfers.max_amount = max_amount
        
        settings.features = settings.features  # Trigger change tracking
        await self.update(settings)
        logger.debug("Updated transfer settings")

    async def update_balance_settings(
        self,
        balance_min_amount: int | None = ...,  # type: ignore[assignment]
        balance_max_amount: int | None = ...,  # type: ignore[assignment]
    ) -> None:
        """Update balance settings."""
        settings = await self.get()
        
        # Используем Ellipsis (...) как значение по умолчанию, чтобы отличить
        # явно переданный None (без ограничений) от отсутствующего параметра
        if balance_min_amount is not ...:
            settings.features.balance_min_amount = balance_min_amount
        if balance_max_amount is not ...:
            settings.features.balance_max_amount = balance_max_amount
        
        settings.features = settings.features  # Trigger change tracking
        await self.update(settings)
        logger.debug(f"Updated balance settings: min={balance_min_amount}, max={balance_max_amount}")

    # === Global Discount Settings ===

    async def toggle_global_discount(self) -> bool:
        """Toggle global discount feature. Returns new value."""
        settings = await self.get()
        new_value = not settings.features.global_discount.enabled
        settings.features.global_discount.enabled = new_value
        settings.features = settings.features  # Trigger change tracking
        await self.update(settings)
        logger.debug(f"Toggled global_discount enabled -> '{new_value}'")
        return new_value

    async def get_global_discount_settings(self):
        """Get global discount settings."""
        settings = await self.get()
        return settings.features.global_discount

    async def is_global_discount_enabled(self) -> bool:
        """Check if global discount feature is enabled."""
        settings = await self.get()
        return settings.features.global_discount.enabled

    async def update_global_discount_settings(
        self,
        enabled: bool | None = None,
        discount_type: str | None = None,
        discount_value: float | None = None,
        stack_discounts: bool | None = None,
        apply_to_subscription: bool | None = None,
        apply_to_extra_devices: bool | None = None,
        apply_to_transfer_commission: bool | None = None,
    ) -> None:
        """Update global discount settings."""
        settings = await self.get()
        
        if enabled is not None:
            settings.features.global_discount.enabled = enabled
        if discount_type is not None:
            settings.features.global_discount.discount_type = discount_type
        if discount_value is not None:
            settings.features.global_discount.discount_value = discount_value
        if stack_discounts is not None:
            settings.features.global_discount.stack_discounts = stack_discounts
        if apply_to_subscription is not None:
            settings.features.global_discount.apply_to_subscription = apply_to_subscription
        if apply_to_extra_devices is not None:
            settings.features.global_discount.apply_to_extra_devices = apply_to_extra_devices
        if apply_to_transfer_commission is not None:
            settings.features.global_discount.apply_to_transfer_commission = apply_to_transfer_commission
        
        settings.features = settings.features  # Trigger change tracking
        await self.update(settings)
        logger.debug("Updated global discount settings")

    #

    async def _clear_cache(self) -> None:
        settings_cache_key: str = build_key("cache", "get_settings")
        logger.debug(f"Cache '{settings_cache_key}' cleared")
        await self.redis_client.delete(settings_cache_key)
