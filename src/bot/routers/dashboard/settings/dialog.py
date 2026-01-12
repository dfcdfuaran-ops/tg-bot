from aiogram.enums import ContentType
from aiogram_dialog import Dialog, Window, StartMode
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Column, Row, Start, SwitchTo
from aiogram_dialog.widgets.text import Format
from magic_filter import F

from src.bot.states import DashboardSettings, RemnashopNotifications, DashboardAccess, RemnashopReferral, RemnashopGateways
from src.bot.widgets import Banner, I18nFormat, IgnoreUpdate
from src.core.enums import BannerName

from .getters import (
    settings_main_getter,
    balance_settings_getter,
    transfers_settings_getter,
    extra_devices_getter,
    extra_devices_price_getter,
    global_discount_settings_getter,
    global_discount_apply_to_getter,
    global_discount_mode_getter,
    tos_settings_getter,
    community_settings_getter,
    finances_settings_getter,
    currency_rates_getter,
)
from .handlers import (
    on_accept_transfers,
    on_back_to_dashboard,
    on_back_to_main_menu,
    on_cancel_transfers,
    on_commission_value_input,
    on_commission_manual_value_input,
    on_commission_preset_select,
    on_commission_manual_input_click,
    on_commission_cancel,
    on_commission_accept,
    on_max_amount_input,
    on_max_amount_preset_select,
    on_max_amount_manual_input_click,
    on_max_amount_manual_value_input,
    on_max_amount_cancel,
    on_max_amount_accept,
    on_min_amount_input,
    on_min_amount_preset_select,
    on_min_amount_manual_input_click,
    on_min_amount_manual_value_input,
    on_min_amount_cancel,
    on_min_amount_accept,
    on_select_commission_type,
    on_select_commission_value,
    on_select_max_amount,
    on_select_min_amount,
    on_set_commission_type,
    on_transfers_click,
    on_balance_click,
    on_select_balance_min_amount,
    on_select_balance_max_amount,
    on_balance_min_amount_preset_select,
    on_balance_min_amount_manual_input_click,
    on_balance_min_amount_manual_value_input,
    on_balance_min_amount_cancel,
    on_balance_min_amount_accept,
    on_balance_max_amount_preset_select,
    on_balance_max_amount_manual_input_click,
    on_balance_max_amount_manual_value_input,
    on_balance_max_amount_cancel,
    on_balance_max_amount_accept,
    on_cancel_balance,
    on_accept_balance,
    on_community_click,
    on_set_community_url,
    on_community_url_input,
    on_accept_community,
    on_cancel_community,
    on_tos_click,
    on_toggle_balance,
    on_toggle_community,
    on_toggle_tos,
    on_toggle_extra_devices,
    on_toggle_transfers,
    on_toggle_notifications,
    on_toggle_access,
    on_toggle_referral,
    on_extra_devices_click,
    on_toggle_extra_devices_payment_type,
    on_edit_extra_devices_price,
    on_extra_devices_preset_price_select,
    on_extra_devices_manual_price_mode,
    on_extra_devices_price_input,
    on_cancel_extra_devices_price,
    on_accept_extra_devices_price,
    on_cancel_extra_devices,
    on_accept_extra_devices,
    # Глобальная скидка
    on_global_discount_click,
    on_toggle_global_discount,
    on_select_global_discount_type,
    on_select_global_discount_value,
    on_global_discount_preset_select,
    on_global_discount_manual_input_click,
    on_global_discount_manual_value_input,
    on_cancel_global_discount_manual,
    on_global_discount_value_cancel,
    on_global_discount_value_accept,
    on_cancel_global_discount,
    on_finances_cancel,
    on_finances_accept,
    on_accept_global_discount,
    on_toggle_stack_discounts,
    on_toggle_apply_to_subscription,
    on_toggle_apply_to_extra_devices,
    on_toggle_apply_to_transfer_commission,
    on_global_discount_apply_to_click,
    on_global_discount_mode_click,
    on_select_discount_mode,
    on_cancel_global_discount_apply_to,
    on_accept_global_discount_apply_to,
    on_cancel_global_discount_mode,
    on_accept_global_discount_mode,
    # ToS (Terms of Service)
    on_tos_url_click,
    on_tos_url_input,
    on_toggle_tos_enabled,
    on_accept_tos,
    on_cancel_tos,
    # Finances
    on_finances_click,
    on_finances_currency_rates_click,
    on_finances_back,
    on_toggle_finances_sync,
    on_balance_mode_combined,
    on_balance_mode_separate,
    # Currency Rates
    on_currency_rates_click,
    on_toggle_currency_rates_auto,
    on_toggle_currency_auto_update,
    on_usd_rate_click,
    on_eur_rate_click,
    on_stars_rate_click,
    on_usd_rate_input,
    on_eur_rate_input,
    on_stars_rate_input,
    on_accept_rates,
    on_cancel_rates,
)


# Главное меню настроек
settings_main = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-dashboard-settings"),
    Row(
        Button(
            text=I18nFormat("btn-settings-extra-devices"),
            id="extra_devices",
            on_click=on_extra_devices_click,
        ),
        Button(
            text=I18nFormat(
                "btn-settings-toggle",
                enabled=F["extra_devices_enabled"],
            ),
            id="toggle_extra_devices",
            on_click=on_toggle_extra_devices,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-settings-balance"),
            id="balance",
            on_click=on_balance_click,
        ),
        Button(
            text=I18nFormat(
                "btn-settings-toggle",
                enabled=F["balance_enabled"],
            ),
            id="toggle_balance",
            on_click=on_toggle_balance,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-settings-transfers"),
            id="transfers",
            on_click=on_transfers_click,
        ),
        Button(
            text=I18nFormat(
                "btn-settings-toggle",
                enabled=F["transfers_enabled"],
            ),
            id="toggle_transfers",
            on_click=on_toggle_transfers,
        ),
    ),
    Row(
        Start(
            text=I18nFormat("btn-settings-notifications"),
            id="notifications",
            state=RemnashopNotifications.MAIN,
        ),
        Button(
            text=I18nFormat(
                "btn-settings-toggle",
                enabled=F["notifications_enabled"],
            ),
            id="toggle_notifications",
            on_click=on_toggle_notifications,
        ),
    ),
    Row(
        Start(
            text=I18nFormat("btn-settings-access"),
            id="access",
            state=DashboardAccess.MAIN,
            mode=StartMode.RESET_STACK,
        ),
        Button(
            text=I18nFormat(
                "btn-settings-toggle",
                enabled=F["access_enabled"],
            ),
            id="toggle_access",
            on_click=on_toggle_access,
        ),
    ),
    Row(
        Start(
            text=I18nFormat("btn-settings-referral"),
            id="referral",
            state=RemnashopReferral.MAIN,
        ),
        Button(
            text=I18nFormat(
                "btn-settings-toggle",
                enabled=F["referral_enabled"],
            ),
            id="toggle_referral",
            on_click=on_toggle_referral,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-settings-community"),
            id="community",
            on_click=on_community_click,
        ),
        Button(
            text=I18nFormat(
                "btn-settings-toggle",
                enabled=F["community_enabled"],
            ),
            id="toggle_community",
            on_click=on_toggle_community,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-settings-tos"),
            id="tos",
            on_click=on_tos_click,
        ),
        Button(
            text=I18nFormat(
                "btn-settings-toggle",
                enabled=F["tos_enabled"],
            ),
            id="toggle_tos",
            on_click=on_toggle_tos,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-settings-global-discount"),
            id="global_discount",
            on_click=on_global_discount_click,
        ),
        Button(
            text=I18nFormat(
                "btn-settings-toggle",
                enabled=F["global_discount_enabled"],
            ),
            id="toggle_global_discount",
            on_click=on_toggle_global_discount,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-settings-finances"),
            id="finances",
            on_click=on_finances_click,
        ),
        Button(
            text=I18nFormat(
                "btn-settings-toggle",
                enabled=F["finances_sync_enabled"],
            ),
            id="toggle_finances_sync",
            on_click=on_toggle_finances_sync,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-back"),
            id="back",
            on_click=on_back_to_dashboard,
        ),
        Button(
            text=I18nFormat("btn-back-main-menu"),
            id="main_menu",
            on_click=on_back_to_main_menu,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.MAIN,
    getter=settings_main_getter,
)


# Настройки баланса
balance_settings = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-dashboard-settings-balance"),
    Row(
        Button(
            text=I18nFormat("btn-balance-mode-combined", selected=F["balance_mode_combined"]),
            id="balance_mode_combined",
            on_click=on_balance_mode_combined,
        ),
        Button(
            text=I18nFormat("btn-balance-mode-separate", selected=F["balance_mode_separate"]),
            id="balance_mode_separate",
            on_click=on_balance_mode_separate,
        ),
    ),
    Row(
        Button(
            text=I18nFormat(
                "btn-setting-value",
                name="Минимум",
                value=F["balance_min_amount"],
            ),
            id="balance_min_amount",
            on_click=on_select_balance_min_amount,
        ),
        Button(
            text=I18nFormat(
                "btn-setting-value",
                name="Максимум",
                value=F["balance_max_amount"],
            ),
            id="balance_max_amount",
            on_click=on_select_balance_max_amount,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_cancel_balance,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_accept_balance,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.BALANCE,
    getter=balance_settings_getter,
)


# Ввод минимальной суммы пополнения баланса
balance_min_amount = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat(
        "msg-dashboard-settings-balance-min-amount",
        current_display=F["balance_min_current_display"],
        selected_display=F["balance_min_selected_display"],
    ),
    # Кнопка "Без ограничений"
    Button(
        text=I18nFormat("btn-amount-no-limit", selected=F["amount_no_limit_balance_min_selected"]),
        id="amount_no_limit",
        on_click=on_balance_min_amount_preset_select,
    ),
    # Preset кнопки
    Row(
        Button(
            text=I18nFormat("btn-amount-10", selected=F["amount_10_balance_min_selected"]),
            id="amount_10",
            on_click=on_balance_min_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-50", selected=F["amount_50_balance_min_selected"]),
            id="amount_50",
            on_click=on_balance_min_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-100", selected=F["amount_100_balance_min_selected"]),
            id="amount_100",
            on_click=on_balance_min_amount_preset_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-amount-500", selected=F["amount_500_balance_min_selected"]),
            id="amount_500",
            on_click=on_balance_min_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-1000", selected=F["amount_1000_balance_min_selected"]),
            id="amount_1000",
            on_click=on_balance_min_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-5000", selected=F["amount_5000_balance_min_selected"]),
            id="amount_5000",
            on_click=on_balance_min_amount_preset_select,
        ),
    ),
    # Кнопка ручного ввода
    Button(
        text=I18nFormat("btn-manual-input"),
        id="manual_input",
        on_click=on_balance_min_amount_manual_input_click,
    ),
    # Кнопки Отмена и Принять
    Row(
        Button(
            text=I18nFormat("btn-amount-cancel"),
            id="cancel",
            on_click=on_balance_min_amount_cancel,
        ),
        Button(
            text=I18nFormat("btn-amount-accept"),
            id="accept",
            on_click=on_balance_min_amount_accept,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.BALANCE_MIN_AMOUNT,
    getter=balance_settings_getter,
)

# Окно ручного ввода минимальной суммы пополнения баланса
balance_min_amount_manual = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-min-amount-manual-input"),
    MessageInput(func=on_balance_min_amount_manual_value_input),
    SwitchTo(
        text=I18nFormat("btn-amount-cancel"),
        id="back",
        state=DashboardSettings.BALANCE_MIN_AMOUNT,
    ),
    IgnoreUpdate(),
    state=DashboardSettings.BALANCE_MIN_AMOUNT_MANUAL,
    getter=balance_settings_getter,
)


# Ввод максимальной суммы пополнения баланса
balance_max_amount = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat(
        "msg-dashboard-settings-balance-max-amount",
        current_display=F["balance_max_current_display"],
        selected_display=F["balance_max_selected_display"],
    ),
    # Кнопка "Без ограничений"
    Button(
        text=I18nFormat("btn-amount-no-limit", selected=F["amount_no_limit_balance_max_selected"]),
        id="amount_no_limit",
        on_click=on_balance_max_amount_preset_select,
    ),
    # Preset кнопки
    Row(
        Button(
            text=I18nFormat("btn-amount-1000", selected=F["amount_1000_balance_max_selected"]),
            id="amount_1000",
            on_click=on_balance_max_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-5000", selected=F["amount_5000_balance_max_selected"]),
            id="amount_5000",
            on_click=on_balance_max_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-10000", selected=F["amount_10000_balance_max_selected"]),
            id="amount_10000",
            on_click=on_balance_max_amount_preset_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-amount-50000", selected=F["amount_50000_balance_max_selected"]),
            id="amount_50000",
            on_click=on_balance_max_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-100000", selected=F["amount_100000_balance_max_selected"]),
            id="amount_100000",
            on_click=on_balance_max_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-500000", selected=F["amount_500000_balance_max_selected"]),
            id="amount_500000",
            on_click=on_balance_max_amount_preset_select,
        ),
    ),
    # Кнопка ручного ввода
    Button(
        text=I18nFormat("btn-manual-input"),
        id="manual_input",
        on_click=on_balance_max_amount_manual_input_click,
    ),
    # Кнопки Отмена и Принять
    Row(
        Button(
            text=I18nFormat("btn-amount-cancel"),
            id="cancel",
            on_click=on_balance_max_amount_cancel,
        ),
        Button(
            text=I18nFormat("btn-amount-accept"),
            id="accept",
            on_click=on_balance_max_amount_accept,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.BALANCE_MAX_AMOUNT,
    getter=balance_settings_getter,
)

# Окно ручного ввода максимальной суммы пополнения баланса
balance_max_amount_manual = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-max-amount-manual-input"),
    MessageInput(func=on_balance_max_amount_manual_value_input),
    SwitchTo(
        text=I18nFormat("btn-amount-cancel"),
        id="back",
        state=DashboardSettings.BALANCE_MAX_AMOUNT,
    ),
    IgnoreUpdate(),
    state=DashboardSettings.BALANCE_MAX_AMOUNT_MANUAL,
    getter=balance_settings_getter,
)



# Настройки переводов
transfers_settings = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-dashboard-settings-transfers"),
    Row(
        Button(
            text=I18nFormat("btn-commission-type-percent", selected=F["is_percent"]),
            id="commission_type_percent",
            on_click=on_select_commission_type,
        ),
        Button(
            text=I18nFormat("btn-commission-type-fixed", selected=F["is_fixed"]),
            id="commission_type_fixed",
            on_click=on_select_commission_type,
        ),
    ),
    Button(
        text=I18nFormat(
            "btn-commission-value",
            value=F["commission_value"],
            unit=I18nFormat("unit-percent-or-rub", commission_type=F["commission_type"]),
        ),
        id="commission_value",
        on_click=on_select_commission_value,
    ),
    Row(
        Button(
            text=I18nFormat(
                "btn-setting-value",
                name="Минимум",
                value=F["min_amount"],
            ),
            id="min_amount",
            on_click=on_select_min_amount,
        ),
        Button(
            text=I18nFormat(
                "btn-setting-value",
                name="Максимум",
                value=F["max_amount"],
            ),
            id="max_amount",
            on_click=on_select_max_amount,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_cancel_transfers,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_accept_transfers,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.TRANSFERS,
    getter=transfers_settings_getter,
)


# Выбор типа комиссии
transfers_commission_type = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-dashboard-settings-transfers-commission-type"),
    Column(
        Button(
            text=I18nFormat("btn-commission-type-percent"),
            id="percent",
            on_click=on_set_commission_type,
        ),
        Button(
            text=I18nFormat("btn-commission-type-fixed"),
            id="fixed",
            on_click=on_set_commission_type,
        ),
    ),
    SwitchTo(
        text=I18nFormat("btn-back"),
        id="back",
        state=DashboardSettings.TRANSFERS,
    ),
    IgnoreUpdate(),
    state=DashboardSettings.TRANSFERS_COMMISSION_TYPE,
    getter=transfers_settings_getter,
)


# Ввод значения комиссии
transfers_commission_value = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat(
        "msg-dashboard-settings-transfers-commission-value",
        commission_type_display=F["commission_type_display"],
        commission_display=F["commission_display"],
        selected_display=F["selected_display"],
    ),
    # Кнопка "Бесплатно"
    Button(
        text=I18nFormat("btn-commission-free", selected=F["commission_free_selected"]),
        id="commission_free",
        on_click=on_commission_preset_select,
    ),
    # Процентные кнопки (отображаются только для процентного типа)
    Row(
        Button(
            text=I18nFormat("btn-commission-5", selected=F["commission_5_selected"]),
            id="commission_5",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-10", selected=F["commission_10_selected"]),
            id="commission_10",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-15", selected=F["commission_15_selected"]),
            id="commission_15",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-20", selected=F["commission_20_selected"]),
            id="commission_20",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-25", selected=F["commission_25_selected"]),
            id="commission_25",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        when=F["is_percent"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-commission-30", selected=F["commission_30_selected"]),
            id="commission_30",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-35", selected=F["commission_35_selected"]),
            id="commission_35",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-40", selected=F["commission_40_selected"]),
            id="commission_40",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-45", selected=F["commission_45_selected"]),
            id="commission_45",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-50-percent", selected=F["commission_50_percent_selected"]),
            id="commission_50_percent",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        when=F["is_percent"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-commission-55", selected=F["commission_55_selected"]),
            id="commission_55",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-60", selected=F["commission_60_selected"]),
            id="commission_60",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-65", selected=F["commission_65_selected"]),
            id="commission_65",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-70", selected=F["commission_70_selected"]),
            id="commission_70",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-75", selected=F["commission_75_selected"]),
            id="commission_75",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        when=F["is_percent"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-commission-80", selected=F["commission_80_selected"]),
            id="commission_80",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-85", selected=F["commission_85_selected"]),
            id="commission_85",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-90", selected=F["commission_90_selected"]),
            id="commission_90",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-95", selected=F["commission_95_selected"]),
            id="commission_95",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-commission-100", selected=F["commission_100_selected"]),
            id="commission_100",
            on_click=on_commission_preset_select,
            when=F["is_percent"],
        ),
        when=F["is_percent"],
    ),
    # Фиксированные кнопки (отображаются только для фиксированного типа)
    Row(
        Button(
            text=I18nFormat("btn-commission-50-rub", selected=F["commission_50_selected"]),
            id="commission_50",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-100-rub", selected=F["commission_100_selected"]),
            id="commission_100",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-150-rub", selected=F["commission_150_selected"]),
            id="commission_150",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-200-rub", selected=F["commission_200_selected"]),
            id="commission_200",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-250-rub", selected=F["commission_250_selected"]),
            id="commission_250",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        when=F["is_fixed"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-commission-300-rub", selected=F["commission_300_selected"]),
            id="commission_300",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-350-rub", selected=F["commission_350_selected"]),
            id="commission_350",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-400-rub", selected=F["commission_400_selected"]),
            id="commission_400",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-450-rub", selected=F["commission_450_selected"]),
            id="commission_450",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-500-rub", selected=F["commission_500_selected"]),
            id="commission_500",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        when=F["is_fixed"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-commission-550-rub", selected=F["commission_550_selected"]),
            id="commission_550",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-600-rub", selected=F["commission_600_selected"]),
            id="commission_600",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-650-rub", selected=F["commission_650_selected"]),
            id="commission_650",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-700-rub", selected=F["commission_700_selected"]),
            id="commission_700",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-750-rub", selected=F["commission_750_selected"]),
            id="commission_750",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        when=F["is_fixed"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-commission-800-rub", selected=F["commission_800_selected"]),
            id="commission_800",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-850-rub", selected=F["commission_850_selected"]),
            id="commission_850",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-900-rub", selected=F["commission_900_selected"]),
            id="commission_900",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-950-rub", selected=F["commission_950_selected"]),
            id="commission_950",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-commission-1000-rub", selected=F["commission_1000_selected"]),
            id="commission_1000",
            on_click=on_commission_preset_select,
            when=F["is_fixed"],
        ),
        when=F["is_fixed"],
    ),
    # Строка с кнопкой "Ручной ввод"
    Button(
        text=I18nFormat("btn-manual-input"),
        id="manual_input",
        on_click=on_commission_manual_input_click,
    ),
    # MessageInput для ручного ввода (всегда видим)
    MessageInput(func=on_commission_value_input),
    # Кнопки Отмена и Принять
    Row(
        Button(
            text=I18nFormat("btn-commission-cancel"),
            id="cancel",
            on_click=on_commission_cancel,
        ),
        Button(
            text=I18nFormat("btn-commission-accept"),
            id="accept",
            on_click=on_commission_accept,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.TRANSFERS_COMMISSION_VALUE,
    getter=transfers_settings_getter,
)


# Ввод минимальной суммы
transfers_min_amount = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat(
        "msg-dashboard-settings-transfers-min-amount",
        current_display=F["min_current_display"],
        selected_display=F["min_selected_display"],
    ),
    # Кнопка "Без ограничений"
    Button(
        text=I18nFormat("btn-amount-no-limit", selected=F["amount_no_limit_min_selected"]),
        id="amount_no_limit",
        on_click=on_min_amount_preset_select,
    ),
    # Preset кнопки
    Row(
        Button(
            text=I18nFormat("btn-amount-10", selected=F["amount_10_min_selected"]),
            id="amount_10",
            on_click=on_min_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-50", selected=F["amount_50_min_selected"]),
            id="amount_50",
            on_click=on_min_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-100", selected=F["amount_100_min_selected"]),
            id="amount_100",
            on_click=on_min_amount_preset_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-amount-500", selected=F["amount_500_min_selected"]),
            id="amount_500",
            on_click=on_min_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-1000", selected=F["amount_1000_min_selected"]),
            id="amount_1000",
            on_click=on_min_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-5000", selected=F["amount_5000_min_selected"]),
            id="amount_5000",
            on_click=on_min_amount_preset_select,
        ),
    ),
    # Кнопка ручного ввода
    Button(
        text=I18nFormat("btn-manual-input"),
        id="manual_input",
        on_click=on_min_amount_manual_input_click,
    ),
    # MessageInput для прямого ввода
    MessageInput(func=on_min_amount_input),
    # Кнопки Отмена и Принять
    Row(
        Button(
            text=I18nFormat("btn-amount-cancel"),
            id="cancel",
            on_click=on_min_amount_cancel,
        ),
        Button(
            text=I18nFormat("btn-amount-accept"),
            id="accept",
            on_click=on_min_amount_accept,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.TRANSFERS_MIN_AMOUNT,
    getter=transfers_settings_getter,
)

# Окно ручного ввода минимальной суммы
transfers_min_amount_manual = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-min-amount-manual-input"),
    MessageInput(func=on_min_amount_manual_value_input),
    SwitchTo(
        text=I18nFormat("btn-amount-cancel"),
        id="back",
        state=DashboardSettings.TRANSFERS_MIN_AMOUNT,
    ),
    IgnoreUpdate(),
    state=DashboardSettings.TRANSFERS_MIN_AMOUNT_MANUAL,
    getter=transfers_settings_getter,
)


# Ввод максимальной суммы
transfers_max_amount = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat(
        "msg-dashboard-settings-transfers-max-amount",
        current_display=F["max_current_display"],
        selected_display=F["max_selected_display"],
    ),
    # Кнопка "Без ограничений"
    Button(
        text=I18nFormat("btn-amount-no-limit", selected=F["amount_no_limit_max_selected"]),
        id="amount_no_limit",
        on_click=on_max_amount_preset_select,
    ),
    # Preset кнопки
    Row(
        Button(
            text=I18nFormat("btn-amount-1000", selected=F["amount_1000_max_selected"]),
            id="amount_1000",
            on_click=on_max_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-5000", selected=F["amount_5000_max_selected"]),
            id="amount_5000",
            on_click=on_max_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-10000", selected=F["amount_10000_max_selected"]),
            id="amount_10000",
            on_click=on_max_amount_preset_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-amount-50000", selected=F["amount_50000_max_selected"]),
            id="amount_50000",
            on_click=on_max_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-100000", selected=F["amount_100000_max_selected"]),
            id="amount_100000",
            on_click=on_max_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-amount-500000", selected=F["amount_500000_max_selected"]),
            id="amount_500000",
            on_click=on_max_amount_preset_select,
        ),
    ),
    # Кнопка ручного ввода
    Button(
        text=I18nFormat("btn-manual-input"),
        id="manual_input",
        on_click=on_max_amount_manual_input_click,
    ),
    # MessageInput для прямого ввода
    MessageInput(func=on_max_amount_input),
    # Кнопки Отмена и Принять
    Row(
        Button(
            text=I18nFormat("btn-amount-cancel"),
            id="cancel",
            on_click=on_max_amount_cancel,
        ),
        Button(
            text=I18nFormat("btn-amount-accept"),
            id="accept",
            on_click=on_max_amount_accept,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.TRANSFERS_MAX_AMOUNT,
    getter=transfers_settings_getter,
)

# Окно ручного ввода максимальной суммы
transfers_max_amount_manual = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-max-amount-manual-input"),
    MessageInput(func=on_max_amount_manual_value_input),
    SwitchTo(
        text=I18nFormat("btn-amount-cancel"),
        id="back",
        state=DashboardSettings.TRANSFERS_MAX_AMOUNT,
    ),
    IgnoreUpdate(),
    state=DashboardSettings.TRANSFERS_MAX_AMOUNT_MANUAL,
    getter=transfers_settings_getter,
)


# Окно настроек доп. устройств
extra_devices = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat(
        "msg-dashboard-extra-devices-settings",
        enabled=F["enabled"],
        payment_type_display=F["payment_type_display"],
        extra_devices_price=F["extra_devices_price"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-extra-devices-one-time", selected=F["is_one_time"]),
            id="toggle_one_time",
            on_click=on_toggle_extra_devices_payment_type,
        ),
        Button(
            text=I18nFormat("btn-extra-devices-monthly", selected=F["is_monthly"]),
            id="toggle_monthly",
            on_click=on_toggle_extra_devices_payment_type,
        ),
    ),
    Button(
        text=I18nFormat("btn-extra-devices-price", price=F["extra_devices_price"]),
        id="edit_price",
        on_click=on_edit_extra_devices_price,
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_cancel_extra_devices,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_accept_extra_devices,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.EXTRA_DEVICES,
    getter=extra_devices_getter,
)


# Окно изменения стоимости доп. устройства - выбор предустановленных цен
extra_devices_price = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat(
        "msg-dashboard-extra-devices-price",
        current_price=F["current_price"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-price-free", selected=F["selected_price"] == 0),
            id="preset_0",
            on_click=on_extra_devices_preset_price_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-price-100", selected=F["selected_price"] == 100),
            id="preset_100",
            on_click=on_extra_devices_preset_price_select,
        ),
        Button(
            text=I18nFormat("btn-price-200", selected=F["selected_price"] == 200),
            id="preset_200",
            on_click=on_extra_devices_preset_price_select,
        ),
        Button(
            text=I18nFormat("btn-price-300", selected=F["selected_price"] == 300),
            id="preset_300",
            on_click=on_extra_devices_preset_price_select,
        ),
        Button(
            text=I18nFormat("btn-price-400", selected=F["selected_price"] == 400),
            id="preset_400",
            on_click=on_extra_devices_preset_price_select,
        ),
        Button(
            text=I18nFormat("btn-price-500", selected=F["selected_price"] == 500),
            id="preset_500",
            on_click=on_extra_devices_preset_price_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-price-600", selected=F["selected_price"] == 600),
            id="preset_600",
            on_click=on_extra_devices_preset_price_select,
        ),
        Button(
            text=I18nFormat("btn-price-700", selected=F["selected_price"] == 700),
            id="preset_700",
            on_click=on_extra_devices_preset_price_select,
        ),
        Button(
            text=I18nFormat("btn-price-800", selected=F["selected_price"] == 800),
            id="preset_800",
            on_click=on_extra_devices_preset_price_select,
        ),
        Button(
            text=I18nFormat("btn-price-900", selected=F["selected_price"] == 900),
            id="preset_900",
            on_click=on_extra_devices_preset_price_select,
        ),
        Button(
            text=I18nFormat("btn-price-1000", selected=F["selected_price"] == 1000),
            id="preset_1000",
            on_click=on_extra_devices_preset_price_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-manual-input"),
            id="manual_input",
            on_click=on_extra_devices_manual_price_mode,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_cancel_extra_devices_price,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_accept_extra_devices_price,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.EXTRA_DEVICES_PRICE,
    getter=extra_devices_price_getter,
)


# Окно для ручного ввода стоимости доп. устройства
extra_devices_price_manual = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-dashboard-extra-devices-price-manual"),
    MessageInput(
        func=on_extra_devices_price_input,
        content_types=ContentType.TEXT,
    ),
    SwitchTo(
        text=I18nFormat("btn-cancel"),
        id="cancel",
        state=DashboardSettings.EXTRA_DEVICES_PRICE,
    ),
    IgnoreUpdate(),
    state=DashboardSettings.EXTRA_DEVICES_PRICE_MANUAL,
    getter=extra_devices_price_getter,
)



# Ручной ввод значения комиссии
transfers_commission_manual = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-commission-manual-input"),
    MessageInput(func=on_commission_manual_value_input),
    SwitchTo(
        text=I18nFormat("btn-commission-cancel"),
        id="cancel",
        state=DashboardSettings.TRANSFERS_COMMISSION_VALUE,
    ),
    IgnoreUpdate(),
    state=DashboardSettings.TRANSFERS_COMMISSION_MANUAL,
    getter=transfers_settings_getter,
)


# === Глобальная скидка ===

# Настройки глобальной скидки (главное окно)
global_discount_settings = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-dashboard-settings-global-discount"),
    # Кнопка перехода в меню "Влияние" и "Режим"
    Row(
        Button(
            text=I18nFormat("btn-global-discount-apply-to", apply_to=F["apply_to_display"]),
            id="apply_to",
            on_click=on_global_discount_apply_to_click,
        ),
        Button(
            text=I18nFormat("btn-global-discount-mode", mode=F["stack_mode_display"]),
            id="mode",
            on_click=on_global_discount_mode_click,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-discount-type-percent", selected=F["is_percent"]),
            id="discount_type_percent",
            on_click=on_select_global_discount_type,
        ),
        Button(
            text=I18nFormat("btn-discount-type-fixed", selected=F["is_fixed"]),
            id="discount_type_fixed",
            on_click=on_select_global_discount_type,
        ),
    ),
    Button(
        text=I18nFormat(
            "btn-discount-value",
            value=F["discount_value"],
            unit=I18nFormat("unit-discount-percent-or-rub", discount_type=F["discount_type"]),
        ),
        id="discount_value",
        on_click=on_select_global_discount_value,
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_cancel_global_discount,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_accept_global_discount,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.GLOBAL_DISCOUNT,
    getter=global_discount_settings_getter,
)


# Ввод значения скидки
global_discount_value = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat(
        "msg-dashboard-settings-global-discount-value",
        discount_type_display=F["discount_type_display"],
        db_discount_display=F["db_discount_display"],
        selected_display=F["selected_display"],
    ),
    # Кнопка "Нет скидки"
    Button(
        text=I18nFormat("btn-discount-free", selected=F["discount_free_selected"]),
        id="discount_free",
        on_click=on_global_discount_preset_select,
    ),
    # Процентные кнопки (отображаются только для процентного типа)
    Row(
        Button(
            text=I18nFormat("btn-discount-5", selected=F["discount_5_selected"]),
            id="discount_5",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-10", selected=F["discount_10_selected"]),
            id="discount_10",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-15", selected=F["discount_15_selected"]),
            id="discount_15",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-20", selected=F["discount_20_selected"]),
            id="discount_20",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-25", selected=F["discount_25_selected"]),
            id="discount_25",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        when=F["is_percent"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-discount-30", selected=F["discount_30_selected"]),
            id="discount_30",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-35", selected=F["discount_35_selected"]),
            id="discount_35",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-40", selected=F["discount_40_selected"]),
            id="discount_40",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-45", selected=F["discount_45_selected"]),
            id="discount_45",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-50-percent", selected=F["discount_50_percent_selected"]),
            id="discount_50_percent",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        when=F["is_percent"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-discount-55", selected=F["discount_55_selected"]),
            id="discount_55",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-60", selected=F["discount_60_selected"]),
            id="discount_60",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-65", selected=F["discount_65_selected"]),
            id="discount_65",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-70", selected=F["discount_70_selected"]),
            id="discount_70",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-75", selected=F["discount_75_selected"]),
            id="discount_75",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        when=F["is_percent"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-discount-80", selected=F["discount_80_selected"]),
            id="discount_80",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-85", selected=F["discount_85_selected"]),
            id="discount_85",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-90", selected=F["discount_90_selected"]),
            id="discount_90",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-95", selected=F["discount_95_selected"]),
            id="discount_95",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        Button(
            text=I18nFormat("btn-discount-100", selected=F["discount_100_selected"]),
            id="discount_100",
            on_click=on_global_discount_preset_select,
            when=F["is_percent"],
        ),
        when=F["is_percent"],
    ),
    # Фиксированные кнопки (отображаются только для фиксированного типа)
    Row(
        Button(
            text=I18nFormat("btn-discount-50-rub", selected=F["discount_50_selected"]),
            id="discount_50",
            on_click=on_global_discount_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-discount-100-rub", selected=F["discount_100_selected"]),
            id="discount_100",
            on_click=on_global_discount_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-discount-150-rub", selected=F["discount_150_selected"]),
            id="discount_150",
            on_click=on_global_discount_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-discount-200-rub", selected=F["discount_200_selected"]),
            id="discount_200",
            on_click=on_global_discount_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-discount-250-rub", selected=F["discount_250_selected"]),
            id="discount_250",
            on_click=on_global_discount_preset_select,
            when=F["is_fixed"],
        ),
        when=F["is_fixed"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-discount-300-rub", selected=F["discount_300_selected"]),
            id="discount_300",
            on_click=on_global_discount_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-discount-350-rub", selected=F["discount_350_selected"]),
            id="discount_350",
            on_click=on_global_discount_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-discount-400-rub", selected=F["discount_400_selected"]),
            id="discount_400",
            on_click=on_global_discount_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-discount-450-rub", selected=F["discount_450_selected"]),
            id="discount_450",
            on_click=on_global_discount_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-discount-500-rub", selected=F["discount_500_selected"]),
            id="discount_500",
            on_click=on_global_discount_preset_select,
            when=F["is_fixed"],
        ),
        when=F["is_fixed"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-discount-600-rub", selected=F["discount_600_selected"]),
            id="discount_600",
            on_click=on_global_discount_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-discount-700-rub", selected=F["discount_700_selected"]),
            id="discount_700",
            on_click=on_global_discount_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-discount-800-rub", selected=F["discount_800_selected"]),
            id="discount_800",
            on_click=on_global_discount_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-discount-900-rub", selected=F["discount_900_selected"]),
            id="discount_900",
            on_click=on_global_discount_preset_select,
            when=F["is_fixed"],
        ),
        Button(
            text=I18nFormat("btn-discount-1000-rub", selected=F["discount_1000_selected"]),
            id="discount_1000",
            on_click=on_global_discount_preset_select,
            when=F["is_fixed"],
        ),
        when=F["is_fixed"],
    ),
    # Кнопка ручного ввода
    Button(
        text=I18nFormat("btn-manual-input"),
        id="manual_input",
        on_click=on_global_discount_manual_input_click,
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_global_discount_value_cancel,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_global_discount_value_accept,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.GLOBAL_DISCOUNT_VALUE,
    getter=global_discount_settings_getter,
)


# Ручной ввод значения скидки
global_discount_manual = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-global-discount-manual-input"),
    MessageInput(func=on_global_discount_manual_value_input),
    Button(
        text=I18nFormat("btn-cancel"),
        id="cancel",
        on_click=on_cancel_global_discount_manual,
    ),
    IgnoreUpdate(),
    state=DashboardSettings.GLOBAL_DISCOUNT_MANUAL,
    getter=global_discount_settings_getter,
)


# Меню "На что влияет скидка"
global_discount_apply_to = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-global-discount-apply-to"),
    Button(
        text=I18nFormat("btn-apply-to-subscription", enabled=F["apply_to_subscription"]),
        id="apply_to_subscription",
        on_click=on_toggle_apply_to_subscription,
    ),
    Button(
        text=I18nFormat("btn-apply-to-extra-devices", enabled=F["apply_to_extra_devices"]),
        id="apply_to_extra_devices",
        on_click=on_toggle_apply_to_extra_devices,
    ),
    Button(
        text=I18nFormat("btn-apply-to-transfer-commission", enabled=F["apply_to_transfer_commission"]),
        id="apply_to_transfer_commission",
        on_click=on_toggle_apply_to_transfer_commission,
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_cancel_global_discount_apply_to,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_accept_global_discount_apply_to,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.GLOBAL_DISCOUNT_APPLY_TO,
    getter=global_discount_apply_to_getter,
)


# Меню "Режим применения скидок"
global_discount_mode = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-global-discount-mode"),
    Row(
        Button(
            text=I18nFormat("btn-discount-mode-max", selected=F["mode_max_selected"]),
            id="mode_max",
            on_click=on_select_discount_mode,
        ),
        Button(
            text=I18nFormat("btn-discount-mode-stack", selected=F["mode_stack_selected"]),
            id="mode_stack",
            on_click=on_select_discount_mode,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_cancel_global_discount_mode,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_accept_global_discount_mode,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.GLOBAL_DISCOUNT_MODE,
    getter=global_discount_mode_getter,
)


# Соглашение (Terms of Service)
tos_settings = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat(
        "msg-dashboard-settings-tos",
        status=F["status_text"],
        source=F["url_display"],
    ),
    Button(
        text=I18nFormat(
            "btn-tos-set-url",
        ),
        id="tos_url",
        on_click=on_tos_url_click,
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_cancel_tos,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_accept_tos,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.TOS,
    getter=tos_settings_getter,
)


# Ввод URL соглашения
tos_url_manual = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-dashboard-settings-tos-url"),
    MessageInput(
        func=on_tos_url_input,
        content_types=[ContentType.TEXT],
    ),
    SwitchTo(
        text=I18nFormat("btn-cancel"),
        id="back",
        state=DashboardSettings.TOS,
    ),
    IgnoreUpdate(),
    state=DashboardSettings.TOS_URL_MANUAL,
    getter=tos_settings_getter,
)


# ═══════════════════════════════════════════════════════════════
# Сообщество
# ═══════════════════════════════════════════════════════════════

community_settings = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-dashboard-settings-community", status=F["status"], url_display=F["url_display"]),
    Row(
        Button(
            text=I18nFormat("btn-settings-community-set-url"),
            id="set_url",
            on_click=on_set_community_url,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_cancel_community,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_accept_community,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.COMMUNITY,
    getter=community_settings_getter,
)


# Ввод URL сообщества
community_url_manual = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-dashboard-settings-community-url"),
    MessageInput(
        func=on_community_url_input,
        content_types=[ContentType.TEXT],
    ),
    SwitchTo(
        text=I18nFormat("btn-cancel"),
        id="back",
        state=DashboardSettings.COMMUNITY,
    ),
    IgnoreUpdate(),
    state=DashboardSettings.COMMUNITY_URL_MANUAL,
    getter=community_settings_getter,
)


# ═══════════════════════════════════════════════════════════════
# Финансы
# ═══════════════════════════════════════════════════════════════

finances_settings = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-dashboard-settings-finances", default_currency=F["default_currency"], default_currency_name=F["default_currency_name"]),
    Row(
        Button(
            text=I18nFormat("btn-finances-sync", enabled=F["sync_enabled"]),
            id="toggle_sync",
            on_click=on_toggle_finances_sync,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-finances-currency-rates"),
            id="currency_rates",
            on_click=on_finances_currency_rates_click,
        ),
    ),
    Row(
        Start(
            text=I18nFormat("btn-finances-gateways"),
            id="gateways",
            state=RemnashopGateways.MAIN,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_finances_cancel,
        ),
        SwitchTo(
            text=I18nFormat("btn-accept"),
            id="accept",
            state=DashboardSettings.MAIN,
            on_click=on_finances_accept,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.FINANCES,
    getter=finances_settings_getter,
)


# ═══════════════════════════════════════════════════════════════
# Курс валют
# ═══════════════════════════════════════════════════════════════

currency_rates_settings = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-dashboard-settings-currency-rates"),
    Row(
        Button(
            text=Format("{usd_display}"),
            id="usd_rate",
            on_click=on_usd_rate_click,
        ),
    ),
    Row(
        Button(
            text=Format("{eur_display}"),
            id="eur_rate",
            on_click=on_eur_rate_click,
        ),
    ),
    Row(
        Button(
            text=Format("{stars_display}"),
            id="stars_rate",
            on_click=on_stars_rate_click,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_cancel_rates,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_accept_rates,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardSettings.CURRENCY_RATES,
    getter=currency_rates_getter,
)

currency_rate_usd = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-dashboard-settings-currency-rate-input", currency="USD", symbol="$"),
    SwitchTo(
        text=I18nFormat("btn-cancel"),
        id="back",
        state=DashboardSettings.CURRENCY_RATES,
    ),
    MessageInput(func=on_usd_rate_input, content_types=ContentType.TEXT),
    IgnoreUpdate(),
    state=DashboardSettings.CURRENCY_RATE_USD,
    getter=currency_rates_getter,
)

currency_rate_eur = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-dashboard-settings-currency-rate-input", currency="EUR", symbol="€"),
    SwitchTo(
        text=I18nFormat("btn-cancel"),
        id="back",
        state=DashboardSettings.CURRENCY_RATES,
    ),
    MessageInput(func=on_eur_rate_input, content_types=ContentType.TEXT),
    IgnoreUpdate(),
    state=DashboardSettings.CURRENCY_RATE_EUR,
    getter=currency_rates_getter,
)

currency_rate_stars = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-dashboard-settings-currency-rate-input", currency="Stars", symbol="★"),
    SwitchTo(
        text=I18nFormat("btn-cancel"),
        id="back",
        state=DashboardSettings.CURRENCY_RATES,
    ),
    MessageInput(func=on_stars_rate_input, content_types=ContentType.TEXT),
    IgnoreUpdate(),
    state=DashboardSettings.CURRENCY_RATE_STARS,
    getter=currency_rates_getter,
)


router = Dialog(
    settings_main,
    balance_settings,
    balance_min_amount,
    balance_min_amount_manual,
    balance_max_amount,
    balance_max_amount_manual,
    transfers_settings,
    transfers_commission_type,
    transfers_commission_value,
    transfers_commission_manual,
    transfers_min_amount,
    transfers_min_amount_manual,
    transfers_max_amount,
    transfers_max_amount_manual,
    extra_devices,
    extra_devices_price,
    extra_devices_price_manual,
    global_discount_settings,
    global_discount_value,
    global_discount_manual,
    global_discount_apply_to,
    global_discount_mode,
    tos_settings,
    tos_url_manual,
    community_settings,
    community_url_manual,
    finances_settings,
    currency_rates_settings,
    currency_rate_usd,
    currency_rate_eur,
    currency_rate_stars,
)
