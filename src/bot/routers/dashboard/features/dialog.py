from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import Button, Column, Row
from magic_filter import F

from src.bot.states import DashboardFeatures
from src.bot.widgets import Banner, I18nFormat, IgnoreUpdate
from src.core.enums import BannerName

from .getters import features_getter
from .handlers import (
    on_toggle_balance,
    on_toggle_community,
    on_toggle_tos,
    on_cancel_features,
    on_accept_features,
    on_toggle_extra_devices,
    on_toggle_transfers,
)


features_main = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-dashboard-features"),
    Column(
        Button(
            text=I18nFormat(
                "btn-feature-toggle",
                name="Сообщество",
                enabled=F["community_enabled"],
            ),
            id="toggle_community",
            on_click=on_toggle_community,
        ),
        Button(
            text=I18nFormat(
                "btn-feature-toggle",
                name="Соглашение",
                enabled=F["tos_enabled"],
            ),
            id="toggle_tos",
            on_click=on_toggle_tos,
        ),
        Button(
            text=I18nFormat(
                "btn-feature-toggle",
                name="Баланс",
                enabled=F["balance_enabled"],
            ),
            id="toggle_balance",
            on_click=on_toggle_balance,
        ),
        Button(
            text=I18nFormat(
                "btn-feature-toggle",
                name="Доп. устройства",
                enabled=F["extra_devices_enabled"],
            ),
            id="toggle_extra_devices",
            on_click=on_toggle_extra_devices,
        ),
        Button(
            text=I18nFormat(
                "btn-feature-toggle",
                name="Переводы",
                enabled=F["transfers_enabled"],
            ),
            id="toggle_transfers",
            on_click=on_toggle_transfers,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_cancel_features,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_accept_features,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardFeatures.MAIN,
    getter=features_getter,
)


router = Dialog(features_main)
