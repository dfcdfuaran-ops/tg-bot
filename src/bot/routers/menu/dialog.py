from aiogram_dialog import Dialog, StartMode, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import (
    Button,
    Column,
    CopyText,
    Group,
    ListGroup,
    Row,
    ScrollingGroup,
    Select,
    Start,
    SwitchInlineQueryChosenChatButton,
    SwitchTo,
    Url,
    WebApp,
)
from aiogram_dialog.widgets.text import Format
from magic_filter import F

from src.bot.keyboards import connect_buttons, get_back_and_main_menu_buttons, main_menu_button
from src.bot.routers.dashboard.users.handlers import on_user_search
from src.bot.states import Dashboard, MainMenu, Subscription
from src.bot.widgets import Banner, I18nFormat, IgnoreUpdate
from src.core.constants import MIDDLEWARE_DATA_KEY, PURCHASE_PREFIX, USER_KEY
from src.core.enums import BannerName

from .getters import (
    balance_amount_getter,
    balance_amounts_getter,
    balance_confirm_getter,
    balance_gateways_getter,
    balance_menu_getter,
    balance_success_getter,
    bonus_activate_custom_getter,
    bonus_activate_getter,
    connect_getter,
    devices_getter,
    invite_about_getter,
    invite_getter,
    menu_getter,
    transfer_amount_manual_getter,
    transfer_amount_value_getter,
    transfer_menu_getter,
    transfer_message_getter,
    transfer_recipient_getter,
    transfer_recipient_history_getter,
)
from .handlers import (
    on_balance_amount_input,
    on_balance_amount_select,
    on_balance_click,
    on_balance_gateway_select,
    on_balance_transfer_amount_accept,
    on_balance_transfer_amount_cancel,
    on_balance_transfer_amount_click,
    on_balance_transfer_amount_manual_cancel,
    on_balance_transfer_amount_manual_input_click,
    on_balance_transfer_amount_manual_value_input,
    on_balance_transfer_amount_preset_select,
    on_get_trial,
    on_balance_transfer_cancel,
    on_balance_transfer_click,
    on_balance_transfer_message_accept,
    on_balance_transfer_message_cancel,
    on_balance_transfer_message_click,
    on_balance_transfer_message_input,
    on_balance_transfer_recipient_cancel,
    on_balance_transfer_recipient_click,
    on_balance_transfer_recipient_history_back,
    on_balance_transfer_recipient_history_click,
    on_balance_transfer_recipient_history_select,
    on_balance_transfer_recipient_input,
    on_balance_transfer_send,
    on_balance_withdraw_click,
    on_bonus_amount_select,
    on_accept_bonus_amount,
    on_bonus_custom_input,
    on_bonus_custom_mode,
    on_cancel_bonus_amount,
    on_device_delete,
    on_extra_devices_list,
    on_add_device,
    on_invite,
    on_platform_select,
    on_promocode,
    on_show_qr,
    on_withdraw_points,
    show_reason,
)

menu = Window(
    Banner(BannerName.MENU),
    I18nFormat("msg-main-menu"),
    # [Попробовать бесплатно]
    Row(
        Button(
            text=I18nFormat("btn-menu-try-free"),
            id="try_free",
            on_click=on_get_trial,
            when=F["trial_available"],
        ),
    ),
    # [Баланс]
    Row(
        Button(
            text=Format("💰 Баланс: {balance} ₽"),
            id="balance",
            on_click=on_balance_click,
        ),
        when=F["is_balance_enabled"],
    ),
    # [Подписка][Мои устройства] - для всех пользователей
    Row(
        Start(
            text=I18nFormat("btn-menu-subscription"),
            id="subscription",
            state=Subscription.MAIN,
            mode=StartMode.RESET_STACK,
        ),
        SwitchTo(
            text=I18nFormat("btn-menu-devices"),
            id="devices",
            state=MainMenu.DEVICES,
            when=F["show_devices_button"],
        ),
    ),
    # [Подключиться][Пригласить] (если есть подписка)
    Row(
        *connect_buttons,
        Button(
            text=I18nFormat("btn-menu-connect-not-available"),
            id="not_available",
            on_click=show_reason,
            when=~F["connectable"],
        ),
        Button(
            text=I18nFormat("btn-menu-invite"),
            id="invite",
            on_click=on_invite,
            when=F["is_referral_enable"],
        ),
        SwitchInlineQueryChosenChatButton(
            text=I18nFormat("btn-menu-invite"),
            query=Format("{invite}"),
            allow_user_chats=True,
            allow_group_chats=True,
            allow_channel_chats=True,
            id="send",
            when=~F["is_referral_enable"],
        ),
        when=F["has_subscription"],
    ),
    # [Промокод] - для всех пользователей
    Row(
        Button(
            text=I18nFormat("btn-menu-promocode"),
            id="promocode",
            on_click=on_promocode,
        ),
    ),
    # [Сообщество][Помощь]
    Row(
        Url(
            text=I18nFormat("btn-menu-community"),
            id="community",
            url=Format("{community_url}"),
            when=F["is_community_enabled"],
        ),
        Url(
            text=I18nFormat("btn-menu-support"),
            id="support",
            url=Format("{support}"),
        ),
    ),
    # [Соглашение]
    Row(
        Url(
            text=I18nFormat("btn-menu-tos"),
            id="tos",
            url=Format("{tos_url}"),
            when=F["is_tos_enabled"],
        ),
    ),
    # [Панель управления]
    Row(
        Start(
            text=I18nFormat("btn-menu-dashboard"),
            id="dashboard",
            state=Dashboard.MAIN,
            mode=StartMode.RESET_STACK,
            when=F[MIDDLEWARE_DATA_KEY][USER_KEY].is_privileged,
        ),
    ),
    MessageInput(func=on_user_search),
    IgnoreUpdate(),
    state=MainMenu.MAIN,
    getter=menu_getter,
)

# Окно подключения с инструкцией
connect = Window(
    Banner(BannerName.MENU),
    I18nFormat("msg-menu-connect"),
    Row(
        Url(
            text=I18nFormat("btn-menu-download"),
            url=Format("{download_url}"),
            id="download",
        ),
    ),
    Row(
        Url(
            text=I18nFormat("btn-menu-connect-open"),
            url=Format("{happ_url}"),
            id="connect_happ",
        ),
    ),
    Row(
        Url(
            text=I18nFormat("btn-menu-connect-subscribe"),
            url=Format("{subscription_url}"),
            id="connect_subscribe_page",
        ),
    ),
    Row(
        *main_menu_button,
    ),
    IgnoreUpdate(),
    state=MainMenu.CONNECT,
    getter=connect_getter,
)

devices = Window(
    Banner(BannerName.MENU),
    I18nFormat("msg-menu-devices"),
    Row(
        Button(
            text=I18nFormat("btn-menu-devices-empty"),
            id="devices_empty",
            when=F["devices_empty"],
        ),
    ),
    ListGroup(
        Row(
            CopyText(
                text=Format("{item[platform]} - {item[device_model]}"),
                copy_text=Format("{item[platform]} - {item[device_model]}"),
            ),
            Button(
                text=Format("❌"),
                id="delete",
                on_click=on_device_delete,
            ),
        ),
        id="devices_list",
        item_id_getter=lambda item: item["short_hwid"],
        items="devices",
    ),
    # Кнопка списка купленных дополнительных устройств
    Row(
        Button(
            text=I18nFormat("btn-menu-extra-devices"),
            id="extra_devices_list",
            on_click=on_extra_devices_list,
            when=F["show_extra_devices_button"],
        ),
    ),
    Row(
        *main_menu_button,
    ),
    IgnoreUpdate(),
    state=MainMenu.DEVICES,
    getter=devices_getter,
)

invite = Window(
    Banner(BannerName.REFERRAL),
    I18nFormat("msg-menu-invite"),
    Row(
        Button(
            text=I18nFormat("btn-menu-invite-send"),
            id="send",
            on_click=on_invite,
            when=F["is_referral_enable"],
        ),
        SwitchInlineQueryChosenChatButton(
            text=I18nFormat("btn-menu-invite-send"),
            query=Format("{invite}"),
            allow_user_chats=True,
            allow_group_chats=True,
            allow_channel_chats=True,
            id="send_inline",
            when=~F["is_referral_enable"],
        ),
        Button(
            text=I18nFormat("btn-menu-invite-qr"),
            id="qr",
            on_click=on_show_qr,
        ),
    ),
    Row(
        CopyText(
            text=I18nFormat("btn-menu-invite-copy"),
            copy_text=Format("{referral_link}"),
        ),
    ),
    Row(
        *main_menu_button,
    ),
    IgnoreUpdate(),
    state=MainMenu.INVITE,
    getter=invite_getter,
)

invite_about = Window(
    Banner(BannerName.REFERRAL),
    I18nFormat("msg-menu-invite-about"),
    *get_back_and_main_menu_buttons(MainMenu.INVITE),
    IgnoreUpdate(),
    state=MainMenu.INVITE_ABOUT,
    getter=invite_about_getter,
)

invite_qr = Window(
    Banner(BannerName.REFERRAL),
    I18nFormat("msg-menu-invite"),
    Row(
        SwitchTo(
            text=I18nFormat("btn-back"),
            id="back",
            state=MainMenu.INVITE,
        ),
        Start(
            text=I18nFormat("btn-main-menu"),
            id="back_main_menu",
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
        ),
    ),
    IgnoreUpdate(),
    state=MainMenu.INVITE_QR,
    getter=invite_getter,
)

balance = Window(
    Banner(BannerName.MENU),
    I18nFormat("msg-balance-menu"),
    Row(
        SwitchTo(
            text=I18nFormat("btn-balance-topup"),
            id="topup",
            state=MainMenu.BALANCE_TOPUP,
        ),
        Button(
            text=I18nFormat("btn-balance-withdraw"),
            id="withdraw",
            on_click=on_balance_withdraw_click,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-balance-transfer"),
            id="transfer",
            on_click=on_balance_transfer_click,
            when=F["is_transfers_enabled"],
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-menu-invite-withdraw-balance"),
            id="activate_bonuses",
            state=MainMenu.BONUS_ACTIVATE,
            when=F["has_referral_balance"],  # Показываем только если есть бонусы и режим SEPARATE
        ),
    ),
    *main_menu_button,
    IgnoreUpdate(),
    state=MainMenu.BALANCE,
    getter=balance_menu_getter,
)

balance_topup = Window(
    Banner(BannerName.MENU),
    I18nFormat("msg-balance-select-gateway"),
    Column(
        Select(
            text=I18nFormat("btn-balance-gateway", gateway_type=F["item"]["gateway_type"]),
            id="select_gateway",
            item_id_getter=lambda item: item["gateway_type"],
            items="payment_methods",
            on_click=on_balance_gateway_select,
        ),
    ),
    *get_back_and_main_menu_buttons(MainMenu.BALANCE),
    IgnoreUpdate(),
    state=MainMenu.BALANCE_TOPUP,
    getter=balance_gateways_getter,
)

balance_amounts = Window(
    Banner(BannerName.MENU),
    I18nFormat("msg-balance-select-amount"),
    Row(
        Button(
            text=Format("100 {currency}"),
            id="amount_100",
            on_click=on_balance_amount_select,
        ),
        Button(
            text=Format("250 {currency}"),
            id="amount_250",
            on_click=on_balance_amount_select,
        ),
        Button(
            text=Format("500 {currency}"),
            id="amount_500",
            on_click=on_balance_amount_select,
        ),
    ),
    Row(
        Button(
            text=Format("1000 {currency}"),
            id="amount_1000",
            on_click=on_balance_amount_select,
        ),
        Button(
            text=Format("2500 {currency}"),
            id="amount_2500",
            on_click=on_balance_amount_select,
        ),
        Button(
            text=Format("5000 {currency}"),
            id="amount_5000",
            on_click=on_balance_amount_select,
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-balance-custom-amount"),
            id="custom_amount",
            state=MainMenu.BALANCE_AMOUNT,
        ),
    ),
    *get_back_and_main_menu_buttons(MainMenu.BALANCE_TOPUP),
    IgnoreUpdate(),
    state=MainMenu.BALANCE_AMOUNTS,
    getter=balance_amounts_getter,
)

balance_amount = Window(
    Banner(BannerName.MENU),
    I18nFormat("msg-balance-enter-amount"),
    SwitchTo(
        text=I18nFormat("btn-cancel"),
        id="cancel",
        state=MainMenu.BALANCE_AMOUNTS,
    ),
    MessageInput(func=on_balance_amount_input),
    IgnoreUpdate(),
    state=MainMenu.BALANCE_AMOUNT,
    getter=balance_amount_getter,
)

balance_confirm = Window(
    Banner(BannerName.MENU),
    I18nFormat("msg-balance-confirm"),
    Row(
        Url(
            text=I18nFormat("btn-balance-pay"),
            id="pay",
            url=Format("{payment_url}"),
            when=F["payment_url"],
        ),
    ),
    *get_back_and_main_menu_buttons(MainMenu.BALANCE_AMOUNTS),
    IgnoreUpdate(),
    state=MainMenu.BALANCE_CONFIRM,
    getter=balance_confirm_getter,
)

balance_success = Window(
    Banner(BannerName.MENU),
    I18nFormat(
        "msg-balance-success",
        amount=F["amount"],
        currency=F["currency"],
    ),
    Row(
        Start(
            text=I18nFormat("btn-done"),
            id="back_main_menu",
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
        ),
    ),
    IgnoreUpdate(),
    state=MainMenu.BALANCE_SUCCESS,
    getter=balance_success_getter,
)

bonus_activate = Window(
    Banner(BannerName.MENU),
    I18nFormat(
        "msg-bonus-activate",
        current_bonus_amount=F["current_bonus_amount"],
    ),
    # Кнопка "Активировать все"
    Row(
        Button(
            text=I18nFormat(
                "btn-bonus-activate-all",
                selected=F["selected_bonus_amount"] == "all",
                referral_balance=F["referral_balance"],
            ),
            id="preset_activate_all",
            on_click=on_bonus_amount_select,
        ),
    ),
    # Первый ряд - 3 кнопки (100, 200, 300)
    Row(
        Button(
            text=I18nFormat("btn-bonus-amount-100", selected=F["selected_bonus_amount"] == "100"),
            id="preset_100",
            on_click=on_bonus_amount_select,
        ),
        Button(
            text=I18nFormat("btn-bonus-amount-200", selected=F["selected_bonus_amount"] == "200"),
            id="preset_200",
            on_click=on_bonus_amount_select,
        ),
        Button(
            text=I18nFormat("btn-bonus-amount-300", selected=F["selected_bonus_amount"] == "300"),
            id="preset_300",
            on_click=on_bonus_amount_select,
        ),
    ),
    # Второй ряд - 3 кнопки (500, 750, 1000)
    Row(
        Button(
            text=I18nFormat("btn-bonus-amount-500", selected=F["selected_bonus_amount"] == "500"),
            id="preset_500",
            on_click=on_bonus_amount_select,
        ),
        Button(
            text=I18nFormat("btn-bonus-amount-750", selected=F["selected_bonus_amount"] == "750"),
            id="preset_750",
            on_click=on_bonus_amount_select,
        ),
        Button(
            text=I18nFormat("btn-bonus-amount-1000", selected=F["selected_bonus_amount"] == "1000"),
            id="preset_1000",
            on_click=on_bonus_amount_select,
        ),
    ),
    # Третий ряд - 3 кнопки (1500, 2000, 2500)
    Row(
        Button(
            text=I18nFormat("btn-bonus-amount-1500", selected=F["selected_bonus_amount"] == "1500"),
            id="preset_1500",
            on_click=on_bonus_amount_select,
        ),
        Button(
            text=I18nFormat("btn-bonus-amount-2000", selected=F["selected_bonus_amount"] == "2000"),
            id="preset_2000",
            on_click=on_bonus_amount_select,
        ),
        Button(
            text=I18nFormat("btn-bonus-amount-2500", selected=F["selected_bonus_amount"] == "2500"),
            id="preset_2500",
            on_click=on_bonus_amount_select,
        ),
    ),
    # Кнопки "Отмена" и "Принять"
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_cancel_bonus_amount,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_accept_bonus_amount,
            when=F["selected_bonus_amount"],
        ),
    ),
    IgnoreUpdate(),
    state=MainMenu.BONUS_ACTIVATE,
    getter=bonus_activate_getter,
)

bonus_activate_custom = Window(
    Banner(BannerName.MENU),
    I18nFormat("msg-bonus-activate-custom"),
    *get_back_and_main_menu_buttons(MainMenu.BONUS_ACTIVATE),
    MessageInput(func=on_bonus_custom_input),
    IgnoreUpdate(),
    state=MainMenu.BONUS_ACTIVATE_CUSTOM,
    getter=bonus_activate_custom_getter,
)

# === Balance Transfer Windows ===

balance_transfer = Window(
    Banner(BannerName.MENU),
    I18nFormat("msg-balance-transfer"),
    Button(
        text=I18nFormat("btn-balance-transfer-recipient"),
        id="select_recipient",
        on_click=on_balance_transfer_recipient_click,
    ),
    Button(
        text=I18nFormat("btn-balance-transfer-amount", amount=F["amount_display"]),
        id="select_amount",
        on_click=on_balance_transfer_amount_click,
    ),
    Button(
        text=I18nFormat("btn-balance-transfer-message"),
        id="select_message",
        on_click=on_balance_transfer_message_click,
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel_transfer",
            on_click=on_balance_transfer_cancel,
        ),
        Button(
            text=I18nFormat("btn-balance-transfer-send"),
            id="send_transfer",
            on_click=on_balance_transfer_send,
        ),
    ),
    IgnoreUpdate(),
    state=MainMenu.BALANCE_TRANSFER,
    getter=transfer_menu_getter,
)

balance_transfer_recipient = Window(
    Banner(BannerName.MENU),
    I18nFormat("msg-balance-transfer-recipient"),
    MessageInput(func=on_balance_transfer_recipient_input),
    Button(
        text=I18nFormat("btn-balance-transfer-history"),
        id="recipient_history",
        on_click=on_balance_transfer_recipient_history_click,
    ),
    Button(
        text=I18nFormat("btn-cancel"),
        id="cancel_recipient",
        on_click=on_balance_transfer_recipient_cancel,
    ),
    IgnoreUpdate(),
    state=MainMenu.BALANCE_TRANSFER_RECIPIENT,
    getter=transfer_recipient_getter,
)

balance_transfer_recipient_history = Window(
    Banner(BannerName.MENU),
    I18nFormat("msg-balance-transfer-recipient-history"),
    ScrollingGroup(
        Select(
            text=Format("{item[name]} ({item[telegram_id]})"),
            id="recipient_select",
            item_id_getter=lambda item: item["telegram_id"],
            items="recipients",
            type_factory=int,
            on_click=on_balance_transfer_recipient_history_select,
        ),
        id="scroll",
        width=1,
        height=7,
        hide_on_single_page=True,
        when=F["has_recipients"],
    ),
    I18nFormat("msg-balance-transfer-no-history", when=~F["has_recipients"]),
    Button(
        text=I18nFormat("btn-back"),
        id="back_recipient",
        on_click=on_balance_transfer_recipient_history_back,
    ),
    IgnoreUpdate(),
    state=MainMenu.BALANCE_TRANSFER_RECIPIENT_HISTORY,
    getter=transfer_recipient_history_getter,
)

balance_transfer_amount_value = Window(
    Banner(BannerName.MENU),
    I18nFormat("msg-balance-transfer-amount-value"),
    Row(
        Button(
            text=I18nFormat("btn-transfer-amount-100", selected=F["amount_100_selected"]),
            id="transfer_amount_100",
            on_click=on_balance_transfer_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-transfer-amount-250", selected=F["amount_250_selected"]),
            id="transfer_amount_250",
            on_click=on_balance_transfer_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-transfer-amount-500", selected=F["amount_500_selected"]),
            id="transfer_amount_500",
            on_click=on_balance_transfer_amount_preset_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-transfer-amount-1000", selected=F["amount_1000_selected"]),
            id="transfer_amount_1000",
            on_click=on_balance_transfer_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-transfer-amount-2000", selected=F["amount_2000_selected"]),
            id="transfer_amount_2000",
            on_click=on_balance_transfer_amount_preset_select,
        ),
        Button(
            text=I18nFormat("btn-transfer-amount-5000", selected=F["amount_5000_selected"]),
            id="transfer_amount_5000",
            on_click=on_balance_transfer_amount_preset_select,
        ),
    ),
    Button(
        text=I18nFormat("btn-manual-input"),
        id="amount_manual_input",
        on_click=on_balance_transfer_amount_manual_input_click,
    ),
    Row(
        Button(
            text=I18nFormat("btn-amount-cancel"),
            id="cancel_amount",
            on_click=on_balance_transfer_amount_cancel,
        ),
        Button(
            text=I18nFormat("btn-amount-accept"),
            id="accept_amount",
            on_click=on_balance_transfer_amount_accept,
        ),
    ),
    IgnoreUpdate(),
    state=MainMenu.BALANCE_TRANSFER_AMOUNT_VALUE,
    getter=transfer_amount_value_getter,
)

balance_transfer_amount_manual = Window(
    Banner(BannerName.MENU),
    I18nFormat("msg-balance-transfer-amount-manual"),
    MessageInput(func=on_balance_transfer_amount_manual_value_input),
    Button(
        text=I18nFormat("btn-cancel"),
        id="cancel_amount_manual",
        on_click=on_balance_transfer_amount_manual_cancel,
    ),
    IgnoreUpdate(),
    state=MainMenu.BALANCE_TRANSFER_AMOUNT_MANUAL,
    getter=transfer_amount_manual_getter,
)

balance_transfer_message = Window(
    Banner(BannerName.MENU),
    I18nFormat("msg-balance-transfer-message"),
    MessageInput(func=on_balance_transfer_message_input),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel_message",
            on_click=on_balance_transfer_message_cancel,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept_message",
            on_click=on_balance_transfer_message_accept,
        ),
    ),
    IgnoreUpdate(),
    state=MainMenu.BALANCE_TRANSFER_MESSAGE,
    getter=transfer_message_getter,
)

router = Dialog(
    menu,
    connect,
    devices,
    invite,
    invite_about,
    invite_qr,
    balance,
    balance_topup,
    balance_amounts,
    balance_amount,
    balance_confirm,
    balance_success,
    bonus_activate,
    bonus_activate_custom,
    balance_transfer,
    balance_transfer_recipient,
    balance_transfer_recipient_history,
    balance_transfer_amount_value,
    balance_transfer_amount_manual,
    balance_transfer_message,
)