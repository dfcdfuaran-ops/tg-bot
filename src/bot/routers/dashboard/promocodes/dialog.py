from aiogram_dialog import Dialog, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import (
    Button,
    Column,
    Group,
    Row,
    ScrollingGroup,
    Select,
    Start,
    SwitchTo,
    ListGroup,
)
from aiogram_dialog.widgets.text import Format, Const
from magic_filter import F

from src.bot.keyboards import main_menu_button
from src.bot.states import Dashboard, DashboardPromocodes
from src.bot.widgets import Banner, I18nFormat, IgnoreUpdate
from src.core.enums import BannerName

from .getters import (
    configurator_getter,
    list_getter,
    type_getter,
    access_getter,
)
from .handlers import (
    on_active_toggle,
    on_code_generate,
    on_code_input,
    on_confirm_save,
    on_create_promocode,
    on_input_cancel,
    on_lifetime_input,
    on_lifetime_preset,
    on_list_promocodes,
    on_name_input,
    on_promocode_delete_from_list,
    on_promocode_search,
    on_promocode_select,
    on_promocode_toggle_active,
    on_quantity_input,
    on_quantity_preset,
    on_reward_input,
    on_reward_preset,
    on_type_accept,
    on_type_cancel,
    on_type_enter,
    on_type_select,
    on_access_enter,
    on_access_select,
    on_access_select_all,
    on_access_cancel,
    on_access_accept,
    on_configurator_cancel,
)

# ==================== Главное меню промокодов ====================

promocodes = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-promocodes-main"),
    Row(
        Button(
            text=I18nFormat("btn-promocodes-create"),
            id="create",
            on_click=on_create_promocode,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-promocodes-list"),
            id="list",
            on_click=on_list_promocodes,
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
    state=DashboardPromocodes.MAIN,
)

# ==================== Поиск промокода ====================

search = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-promocodes-search"),
    Row(
        SwitchTo(
            text=I18nFormat("btn-back"),
            id="back",
            state=DashboardPromocodes.MAIN,
        ),
        *main_menu_button,
    ),
    MessageInput(func=on_promocode_search),
    IgnoreUpdate(),
    state=DashboardPromocodes.SEARCH,
)

# ==================== Список промокодов ====================

promocodes_list = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-promocodes-list", count=F["count"]),
    ListGroup(
        Row(
            Button(
                text=Format("{item.status_emoji}"),
                id="toggle_active",
                on_click=on_promocode_toggle_active,
            ),
            Button(
                text=Format("{item.display_text}"),
                id="select_promo",
                on_click=on_promocode_select,
            ),
            Button(
                text=Const("❌"),
                id="delete_promo",
                on_click=on_promocode_delete_from_list,
            ),
        ),
        id="promo_list",
        item_id_getter=lambda item: item.id,
        items="promocodes",
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-back"),
            id="back",
            state=DashboardPromocodes.MAIN,
        ),
        *main_menu_button,
    ),
    IgnoreUpdate(),
    state=DashboardPromocodes.LIST,
    getter=list_getter,
)

# ==================== Конфигуратор промокода ====================

configurator = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-promocode-configurator"),
    Row(
        SwitchTo(
            text=I18nFormat("btn-promocode-name"),
            id="name",
            state=DashboardPromocodes.NAME,
        ),
        SwitchTo(
            text=I18nFormat("btn-promocode-code"),
            id="code",
            state=DashboardPromocodes.CODE,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-promocode-type"),
            id="type",
            on_click=on_type_enter,
        ),
        SwitchTo(
            text=I18nFormat("btn-promocode-reward"),
            id="reward",
            state=DashboardPromocodes.REWARD,
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-promocode-lifetime"),
            id="lifetime",
            state=DashboardPromocodes.LIFETIME,
        ),
        SwitchTo(
            text=I18nFormat("btn-promocode-quantity"),
            id="quantity",
            state=DashboardPromocodes.QUANTITY,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-promocode-access"),
            id="access",
            on_click=on_access_enter,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_configurator_cancel,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_confirm_save,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardPromocodes.CONFIGURATOR,
    getter=configurator_getter,
)

# ==================== Ввод названия ====================

name = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-promocode-name"),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_input_cancel,
        ),
    ),
    MessageInput(func=on_name_input),
    IgnoreUpdate(),
    state=DashboardPromocodes.NAME,
)

# ==================== Ввод кода ====================

code = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-promocode-code"),
    Row(
        Button(
            text=I18nFormat("btn-promocode-generate"),
            id="generate",
            on_click=on_code_generate,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_input_cancel,
        ),
    ),
    MessageInput(func=on_code_input),
    IgnoreUpdate(),
    state=DashboardPromocodes.CODE,
)

# ==================== Выбор типа ====================

type_select = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-promocode-type"),
    Column(
        Select(
            text=I18nFormat(
                "btn-promocode-type-choice",
                name=F["item"]["name"],
                selected=F["item"]["selected"],
            ),
            id="type_select",
            item_id_getter=lambda item: item["type"].value,
            items="types",
            type_factory=str,
            on_click=on_type_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_type_cancel,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_type_accept,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardPromocodes.TYPE,
    getter=type_getter,
)

# ==================== Ввод награды ====================

reward = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-promocode-reward"),
    # Кнопки для скидок (PERSONAL_DISCOUNT или PURCHASE_DISCOUNT)
    Group(
        Row(
            Button(
                text=Const("0%"),
                id="reward_0",
                on_click=on_reward_preset,
            ),
            Button(
                text=Const("5%"),
                id="reward_5",
                on_click=on_reward_preset,
            ),
            Button(
                text=Const("10%"),
                id="reward_10",
                on_click=on_reward_preset,
            ),
        ),
        Row(
            Button(
                text=Const("25%"),
                id="reward_25",
                on_click=on_reward_preset,
            ),
            Button(
                text=Const("40%"),
                id="reward_40",
                on_click=on_reward_preset,
            ),
            Button(
                text=Const("50%"),
                id="reward_50",
                on_click=on_reward_preset,
            ),
        ),
        Row(
            Button(
                text=Const("70%"),
                id="reward_70",
                on_click=on_reward_preset,
            ),
            Button(
                text=Const("80%"),
                id="reward_80",
                on_click=on_reward_preset,
            ),
            Button(
                text=Const("100%"),
                id="reward_100",
                on_click=on_reward_preset,
            ),
        ),
        when=F["promocode_type"].in_(["PERSONAL_DISCOUNT", "PURCHASE_DISCOUNT"]),
    ),
    # Кнопки для дней (DURATION)
    Group(
        Row(
            Button(
                text=Const("1"),
                id="reward_1",
                on_click=on_reward_preset,
            ),
            Button(
                text=Const("3"),
                id="reward_3",
                on_click=on_reward_preset,
            ),
            Button(
                text=Const("7"),
                id="reward_7",
                on_click=on_reward_preset,
            ),
        ),
        Row(
            Button(
                text=Const("10"),
                id="reward_10",
                on_click=on_reward_preset,
            ),
            Button(
                text=Const("14"),
                id="reward_14",
                on_click=on_reward_preset,
            ),
            Button(
                text=Const("30"),
                id="reward_30",
                on_click=on_reward_preset,
            ),
        ),
        Row(
            Button(
                text=Const("90"),
                id="reward_90",
                on_click=on_reward_preset,
            ),
            Button(
                text=Const("180"),
                id="reward_180",
                on_click=on_reward_preset,
            ),
            Button(
                text=Const("365"),
                id="reward_365",
                on_click=on_reward_preset,
            ),
        ),
        when=F["promocode_type"] == "DURATION",
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_input_cancel,
        ),
    ),
    MessageInput(func=on_reward_input),
    IgnoreUpdate(),
    state=DashboardPromocodes.REWARD,
    getter=configurator_getter,
)

# ==================== Ввод срока действия ====================

lifetime = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-promocode-lifetime"),
    Row(
        Button(
            text=I18nFormat("btn-lifetime-infinite"),
            id="lifetime_0",
            on_click=on_lifetime_preset,
        ),
    ),
    Row(
        Button(
            text=Const("1"),
            id="lifetime_1",
            on_click=on_lifetime_preset,
        ),
        Button(
            text=Const("3"),
            id="lifetime_3",
            on_click=on_lifetime_preset,
        ),
        Button(
            text=Const("5"),
            id="lifetime_5",
            on_click=on_lifetime_preset,
        ),
    ),
    Row(
        Button(
            text=Const("7"),
            id="lifetime_7",
            on_click=on_lifetime_preset,
        ),
        Button(
            text=Const("14"),
            id="lifetime_14",
            on_click=on_lifetime_preset,
        ),
        Button(
            text=Const("30"),
            id="lifetime_30",
            on_click=on_lifetime_preset,
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-manual-input"),
            id="manual_input",
            state=DashboardPromocodes.LIFETIME_INPUT,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_input_cancel,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardPromocodes.LIFETIME,
)

# ==================== Ручной ввод срока действия ====================

lifetime_input = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-promocode-lifetime-input"),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_input_cancel,
        ),
    ),
    MessageInput(func=on_lifetime_input),
    IgnoreUpdate(),
    state=DashboardPromocodes.LIFETIME_INPUT,
)

# ==================== Ввод количества ====================

quantity = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-promocode-quantity"),
    Row(
        Button(
            text=I18nFormat("btn-quantity-infinite"),
            id="quantity_0",
            on_click=on_quantity_preset,
        ),
    ),
    Row(
        Button(
            text=Const("1"),
            id="quantity_1",
            on_click=on_quantity_preset,
        ),
        Button(
            text=Const("5"),
            id="quantity_5",
            on_click=on_quantity_preset,
        ),
        Button(
            text=Const("10"),
            id="quantity_10",
            on_click=on_quantity_preset,
        ),
    ),
    Row(
        Button(
            text=Const("25"),
            id="quantity_25",
            on_click=on_quantity_preset,
        ),
        Button(
            text=Const("50"),
            id="quantity_50",
            on_click=on_quantity_preset,
        ),
        Button(
            text=Const("100"),
            id="quantity_100",
            on_click=on_quantity_preset,
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-manual-input"),
            id="manual_input",
            state=DashboardPromocodes.QUANTITY_INPUT,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_input_cancel,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardPromocodes.QUANTITY,
)

# ==================== Ручной ввод количества ====================

quantity_input = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-promocode-quantity-input"),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_input_cancel,
        ),
    ),
    MessageInput(func=on_quantity_input),
    IgnoreUpdate(),
    state=DashboardPromocodes.QUANTITY_INPUT,
)

# ==================== Выбор доступных тарифов ====================

access = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-promocode-access"),
    Row(
        Button(
            text=I18nFormat("btn-select-all-toggle", all_selected=F["all_selected"]),
            id="select_all",
            on_click=on_access_select_all,
        ),
    ),
    Column(
        Select(
            text=I18nFormat(
                "btn-plan-access-choice",
                plan_name=F["item"]["plan_name"],
                selected=F["item"]["selected"],
            ),
            id="plans_access",
            item_id_getter=lambda item: item["plan_id"],
            items="plans",
            type_factory=int,
            on_click=on_access_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_access_cancel,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_access_accept,
        ),
    ),
    IgnoreUpdate(),
    state=DashboardPromocodes.ALLOWED,
    getter=access_getter,
)

router = Dialog(
    promocodes,
    search,
    promocodes_list,
    configurator,
    name,
    code,
    type_select,
    reward,
    lifetime,
    lifetime_input,
    quantity,
    quantity_input,
    access,
)
