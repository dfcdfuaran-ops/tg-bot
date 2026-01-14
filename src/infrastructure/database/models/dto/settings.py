from typing import Optional

from pydantic import Field, SecretStr

from src.core.constants import T_ME
from src.core.enums import (
    AccessMode,
    BalanceMode,
    Currency,
    ReferralAccrualStrategy,
    ReferralLevel,
    ReferralRewardStrategy,
    ReferralRewardType,
    SystemNotificationType,
    UserNotificationType,
)

from .base import BaseDto, TrackableDto


class SystemNotificationDto(TrackableDto):  # == SystemNotificationType
    bot_lifetime: bool = True
    bot_update: bool = True
    user_registered: bool = True
    subscription: bool = True
    extra_devices: bool = True
    promocode_activated: bool = True
    trial_getted: bool = True
    node_status: bool = True
    user_first_connected: bool = True
    user_hwid: bool = True
    billing: bool = True
    balance_transfer: bool = True
    # TODO: Add torrent_block
    # TODO: Add traffic_overuse

    def is_enabled(self, ntf_type: SystemNotificationType) -> bool:
        return getattr(self, ntf_type.value.lower(), False)


class UserNotificationDto(TrackableDto):  # == UserNotificationType
    expires_in_3_days: bool = True
    expires_in_2_days: bool = True
    expires_in_1_days: bool = True
    expired: bool = True
    limited: bool = True
    expired_1_day_ago: bool = True
    referral_attached: bool = True
    referral_reward: bool = True

    def is_enabled(self, ntf_type: UserNotificationType) -> bool:
        return getattr(self, ntf_type.value.lower(), False)


class ReferralRewardSettingsDto(BaseDto):
    type: ReferralRewardType = ReferralRewardType.MONEY
    strategy: ReferralRewardStrategy = ReferralRewardStrategy.PERCENT
    config: dict[ReferralLevel, int] = {ReferralLevel.FIRST: 10}

    @property
    def is_identical(self) -> bool:
        values = list(self.config.values())
        return len(values) <= 1 or all(v == values[0] for v in values)

    @property
    def is_points(self) -> bool:
        # Legacy - now using is_money
        return self.type == ReferralRewardType.MONEY

    @property
    def is_money(self) -> bool:
        return self.type == ReferralRewardType.MONEY

    @property
    def is_extra_days(self) -> bool:
        return self.type == ReferralRewardType.EXTRA_DAYS


class ReferralSettingsDto(TrackableDto):
    enable: bool = True
    level: ReferralLevel = ReferralLevel.FIRST
    accrual_strategy: ReferralAccrualStrategy = ReferralAccrualStrategy.ON_EACH_PAYMENT
    reward: ReferralRewardSettingsDto = ReferralRewardSettingsDto()
    invite_message: str = "✨ {name} - Ваш приватный интернет!\n\n➡️ Подключиться: {url}"


class ExtraDeviceSettingsDto(TrackableDto):
    """Настройки дополнительных устройств."""
    enabled: bool = True  # Включен ли функционал доп. устройств
    price_per_device: int = 100  # Стоимость одного доп. устройства в месяц
    is_one_time: bool = False  # True = единоразовая оплата, False = ежемесячная


class TransferSettingsDto(TrackableDto):
    """Настройки переводов баланса между пользователями."""
    enabled: bool = True  # Включены ли переводы
    commission_type: str = "percent"  # "percent" или "fixed"
    commission_value: int = 5  # Значение комиссии (% или фикс. сумма)
    min_amount: int = 10  # Минимальная сумма перевода
    max_amount: int = 100000  # Максимальная сумма перевода


class InactiveUserNotificationDto(TrackableDto):
    """Настройки уведомлений о неподключенных пользователях."""
    enabled: bool = False  # Включены ли уведомления
    hours_threshold: int = 24  # Через сколько часов уведомлять


class GlobalDiscountSettingsDto(TrackableDto):
    """Настройки глобальной скидки на все планы."""
    enabled: bool = False  # Включена ли глобальная скидка
    discount_type: str = "percent"  # "percent" или "fixed"
    discount_value: int = 0  # Значение скидки (% или фикс. сумма)
    stack_discounts: bool = False  # True = складывать скидки, False = использовать максимальную
    apply_to_subscription: bool = True  # Применять к подписке
    apply_to_extra_devices: bool = False  # Применять к доп. устройствам
    apply_to_transfer_commission: bool = False  # Применять к комиссии переводов


class CurrencyRatesDto(TrackableDto):
    """Курсы валют относительно рубля."""
    auto_update: bool = False  # Автоматическое обновление курсов из ЦБ РФ
    usd_rate: float = 90.0  # 1 USD = X RUB
    eur_rate: float = 100.0  # 1 EUR = X RUB
    stars_rate: float = 1.5  # 1 Star = X RUB


class FeatureSettingsDto(TrackableDto):
    """Настройки функционала - включение/выключение различных функций."""
    community_enabled: bool = False  # Кнопка "Сообщество" в главном меню (по-умолчанию выключена)
    community_url: Optional[str] = None  # URL Telegram группы сообщества
    tos_enabled: bool = False  # Кнопка "Соглашение" в главном меню (по-умолчанию выключена)
    balance_enabled: bool = True  # Функционал баланса
    balance_mode: BalanceMode = BalanceMode.SEPARATE  # Режим баланса (раздельный/объединённый)
    balance_min_amount: Optional[int] = 10  # Минимальная сумма пополнения баланса
    balance_max_amount: Optional[int] = 100000  # Максимальная сумма пополнения баланса
    notifications_enabled: bool = True  # Отправка уведомлений пользователям
    access_enabled: bool = True  # Глобальный доступ к боту (регистрация и покупки)
    referral_enabled: bool = True  # Реферальная система
    extra_devices: ExtraDeviceSettingsDto = ExtraDeviceSettingsDto()  # Настройки доп. устройств
    transfers: TransferSettingsDto = TransferSettingsDto()  # Настройки переводов
    inactive_notifications: InactiveUserNotificationDto = InactiveUserNotificationDto()  # Уведомления о неподключенных
    global_discount: GlobalDiscountSettingsDto = GlobalDiscountSettingsDto()  # Глобальная скидка
    currency_rates: CurrencyRatesDto = CurrencyRatesDto()  # Курсы валют


class SettingsDto(TrackableDto):
    id: Optional[int] = Field(default=None, frozen=True)

    rules_required: bool = False
    channel_required: bool = False

    rules_link: SecretStr = SecretStr("https://telegram.org/tos/")
    channel_id: Optional[int] = False
    channel_link: SecretStr = SecretStr("@remna_shop")

    access_mode: AccessMode = AccessMode.PUBLIC
    purchases_allowed: bool = True
    registration_allowed: bool = True

    default_currency: Currency = Currency.XTR

    user_notifications: UserNotificationDto = UserNotificationDto()
    system_notifications: SystemNotificationDto = SystemNotificationDto()

    referral: ReferralSettingsDto = ReferralSettingsDto()
    features: FeatureSettingsDto = FeatureSettingsDto()

    @property
    def channel_has_username(self) -> bool:
        return self.channel_link.get_secret_value().startswith("@")

    @property
    def get_url_channel_link(self) -> str:
        if self.channel_has_username:
            return f"{T_ME}{self.channel_link.get_secret_value()[1:]}"
        else:
            return self.channel_link.get_secret_value()
