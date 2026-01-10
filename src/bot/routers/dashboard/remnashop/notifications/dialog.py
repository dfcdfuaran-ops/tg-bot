from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import Button, Column, Row, Select, Start, SwitchTo
from magic_filter import F

from src.bot.keyboards import main_menu_button
from src.bot.states import DashboardRemnashop, RemnashopNotifications
from src.bot.widgets import Banner, I18nFormat, IgnoreUpdate
from src.core.enums import BannerName, SystemNotificationType, UserNotificationType

from .getters import system_types_getter, user_types_getter
from .handlers import (
    on_system_type_select,
    on_user_type_select,
    on_notifications_cancel_main,
    on_notifications_accept_main,
    on_notifications_cancel_submenu,
    on_notifications_accept_submenu,
)

notifications = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-notifications-main"),
    Row(
        SwitchTo(
            text=I18nFormat("btn-notifications-user"),
            id="users",
            state=RemnashopNotifications.USER,
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-notifications-system"),
            id="system",
            state=RemnashopNotifications.SYSTEM,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_notifications_cancel_main,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_notifications_accept_main,
        ),
    ),
    IgnoreUpdate(),
    state=RemnashopNotifications.MAIN,
)

user = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-notifications-user"),
    Column(
        Select(
            text=I18nFormat(
                "btn-notifications-user-choice",
                type=F["item"]["type"],
                enabled=F["item"]["enabled"],
            ),
            id="select_type",
            item_id_getter=lambda item: item["type"],
            items="types",
            type_factory=UserNotificationType,
            on_click=on_user_type_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_notifications_cancel_submenu,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_notifications_accept_submenu,
        ),
    ),
    IgnoreUpdate(),
    state=RemnashopNotifications.USER,
    getter=user_types_getter,
)

system = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-notifications-system"),
    Column(
        Select(
            text=I18nFormat(
                "btn-notifications-system-choice",
                type=F["item"]["type"],
                enabled=F["item"]["enabled"],
            ),
            id="select_type",
            item_id_getter=lambda item: item["type"],
            items="types",
            type_factory=SystemNotificationType,
            on_click=on_system_type_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_notifications_cancel_submenu,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_notifications_accept_submenu,
        ),
    ),
    IgnoreUpdate(),
    state=RemnashopNotifications.SYSTEM,
    getter=system_types_getter,
)

router = Dialog(
    notifications,
    user,
    system,
)
