from aiogram.enums import ContentType
from aiogram_dialog import Dialog, StartMode, Window
from aiogram_dialog.widgets.kbd import Button, ListGroup, Row, Start, SwitchTo
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.text import Format
from magic_filter import F

from src.bot.keyboards import main_menu_button
from src.bot.routers.extra.test import show_dev_popup
from src.bot.states import (
    Dashboard,
    DashboardRemnashop,
    DashboardFeatures,
    RemnashopNotifications,
    RemnashopPlans,
    RemnashopReferral,
)
from src.bot.widgets import Banner, I18nFormat, IgnoreUpdate
from src.core.enums import BannerName

from .getters import admins_getter, remnashop_getter, extra_devices_getter, extra_devices_price_getter
from .handlers import (
    on_logs_request,
    on_user_role_remove,
    on_user_select,
    on_extra_devices_menu,
    on_edit_extra_devices_price,
    on_extra_devices_price_input,
    on_back_to_remnashop,
    on_toggle_extra_devices_payment_type,
    on_extra_devices_preset_price_select,
    on_extra_devices_manual_price_mode,
    on_accept_extra_devices,
    on_cancel_extra_devices,
    on_accept_extra_devices_price,
    on_cancel_extra_devices_price,
)

remnashop = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-remnashop-main"),
    Row(
        SwitchTo(
            text=I18nFormat("btn-remnashop-admins"),
            id="admins",
            state=DashboardRemnashop.ADMINS,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-remnashop-advertising"),
            id="advertising",
            on_click=show_dev_popup,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-remnashop-logs"),
            id="logs",
            on_click=on_logs_request,
        ),
        Button(
            text=I18nFormat("btn-remnashop-audit"),
            id="audit",
            on_click=show_dev_popup,
        ),
    ),
    Row(
        Start(
            text=I18nFormat("btn-back"),
            id="back",
            state=Dashboard.MAIN,
            mode=StartMode.RESET_STACK,
        ),
        *main_menu_button,
    ),
    IgnoreUpdate(),
    state=DashboardRemnashop.MAIN,
    getter=remnashop_getter,
)

admins = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-admins-main"),
    ListGroup(
        Row(
            Button(
                text=Format("{item[user_id]} ({item[user_name]})"),
                id="select_user",
                on_click=on_user_select,
            ),
            Button(
                text=Format("❌"),
                id="remove_role",
                on_click=on_user_role_remove,
                when=F["item"]["deletable"],
            ),
        ),
        id="admins_list",
        item_id_getter=lambda item: item["user_id"],
        items="admins",
    ),
    Row(
        Start(
            text=I18nFormat("btn-back"),
            id="back",
            state=DashboardRemnashop.MAIN,
            mode=StartMode.RESET_STACK,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardRemnashop.ADMINS,
    getter=admins_getter,
)


# Окно настроек доп. устройств
extra_devices = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat(
        "msg-dashboard-extra-devices-settings",
        price=F["extra_devices_price"],
        is_one_time=F["is_one_time"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-extra-devices-one-time", enabled=F["is_one_time"]),
            id="toggle_one_time",
            on_click=on_toggle_extra_devices_payment_type,
        ),
        Button(
            text=I18nFormat("btn-extra-devices-monthly", enabled=F["is_monthly"]),
            id="toggle_monthly",
            on_click=on_toggle_extra_devices_payment_type,
        ),
    ),
    Button(
        text=I18nFormat("btn-extra-devices-price"),
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
    state=DashboardRemnashop.EXTRA_DEVICES,
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
    state=DashboardRemnashop.EXTRA_DEVICES_PRICE,
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
    IgnoreUpdate(),
    state=DashboardRemnashop.EXTRA_DEVICES_PRICE_MANUAL,
    getter=extra_devices_price_getter,
)


router = Dialog(
    remnashop,
    admins,
    extra_devices,
    extra_devices_price,
    extra_devices_price_manual,
)
