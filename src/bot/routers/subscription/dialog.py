from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.kbd import Button, Column, Group, Row, Select, SwitchTo, Start, Url, ListGroup, CopyText
from aiogram_dialog.widgets.text import Format
from aiogram_dialog.widgets.kbd.state import StartMode
from aiogram_dialog.widgets.input import MessageInput
from magic_filter import F

from src.bot.keyboards import connect_buttons, get_back_and_main_menu_buttons, main_menu_button
from src.bot.states import MainMenu, Subscription
from src.bot.widgets import Banner, I18nFormat, IgnoreUpdate
from src.core.constants import PURCHASE_PREFIX
from src.core.enums import BannerName, PaymentGatewayType, PurchaseType

from .getters import (
    add_device_select_count_getter,
    add_device_duration_getter,
    add_device_payment_getter,
    add_device_confirm_getter,
    add_device_success_getter,
    add_device_payment_link_getter,
    confirm_balance_getter,
    confirm_getter,
    confirm_yoomoney_getter,
    confirm_yookassa_getter,
    devices_getter,
    duration_getter,
    extra_devices_list_getter,
    getter_connect,
    payment_method_getter,
    plans_getter,
    referral_success_getter,
    subscription_getter,
    success_payment_getter,
)
from .handlers import (
    on_add_device,
    on_add_device_select_count,
    on_add_device_duration_select,
    on_add_device_payment_select,
    on_add_device_confirm,
    on_back_to_devices,
    on_confirm_balance_payment,
    on_delete_extra_device_purchase,
    on_device_delete,
    on_duration_select,
    on_extra_devices_list,
    on_get_subscription,
    on_payment_method_select,
    on_plan_select,
    on_subscription_plans,
    on_referral_code_request,
    on_referral_code_input,
    on_promocode_input,
)
from src.bot.routers.menu.handlers import on_get_trial

subscription = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-subscription-main"),
    # Кнопка "Пробная" - только если нет пробной подписки (is_trial_subscription == 0)
    Row(
        Button(
            text=I18nFormat("btn-menu-trial"),
            id="trial",
            on_click=on_get_trial,
            when=F["trial_available"] & ~F["is_topup_mode"] & (F["is_trial_subscription"] == 0),
        ),
    ),
    # Кнопка "Реферальная подписка" - только если нет пробной подписки (is_trial_subscription == 0)
    Row(
        Button(
            text=I18nFormat("btn-subscription-referral"),
            id="referral_trial",
            on_click=on_referral_code_request,
            when=F["trial_available"] & ~F["is_referral_trial"] & ~F["is_topup_mode"] & (F["is_trial_subscription"] == 0),
        ),
    ),
    # Кнопка "Улучшить до реферальной" - для Пробного тарифа (когда is_trial_subscription == 1 и is_referral_subscription == 0)
    Row(
        Button(
            text=I18nFormat("btn-subscription-upgrade-referral"),
            id="upgrade_referral",
            on_click=on_referral_code_request,
            when=F["can_upgrade_to_referral"] & ~F["is_topup_mode"],
        ),
    ),
    # Купить подписку - когда нет активной подписки ИЛИ есть пробная/реферальная подписка
    Row(
        Button(
            text=I18nFormat("btn-subscription-new"),
            id=f"{PURCHASE_PREFIX}{PurchaseType.NEW}",
            on_click=on_subscription_plans,
            when=(~F["has_active_subscription"] | (F["is_trial_subscription"] == 1)) & ~F["is_topup_mode"],
        ),
    ),
    # Продлить и Изменить - только для активных (непробных) подписок (is_trial_subscription == 0)
    Row(
        Button(
            text=I18nFormat("btn-subscription-renew"),
            id=f"{PURCHASE_PREFIX}{PurchaseType.RENEW}",
            on_click=on_subscription_plans,
            when=F["has_active_subscription"] & F["is_not_unlimited"] & ~F["is_topup_mode"] & (F["is_trial_subscription"] == 0),
        ),
        Button(
            text=I18nFormat("btn-subscription-change"),
            id=f"{PURCHASE_PREFIX}{PurchaseType.CHANGE}",
            on_click=on_subscription_plans,
            when=F["has_active_subscription"] & ~F["is_topup_mode"] & (F["is_trial_subscription"] == 0),
        ),
    ),
    # Пополнить баланс
    Row(
        Button(
            text=I18nFormat("btn-menu-topup"),
            id=f"{PURCHASE_PREFIX}{PurchaseType.TOPUP}",
            on_click=on_subscription_plans,
            when=F["is_topup_mode"],
        ),
    ),
    Row(
        *main_menu_button,
    ),
    IgnoreUpdate(),
    state=Subscription.MAIN,
    getter=subscription_getter,
)

plans = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-subscription-plans"),
    Column(
        Select(
            text=Format("{item[name]}"),
            id=f"{PURCHASE_PREFIX}select_plan",
            item_id_getter=lambda item: item["id"],
            items="plans",
            type_factory=int,
            on_click=on_plan_select,
        ),
    ),
    *get_back_and_main_menu_buttons(Subscription.MAIN),
    IgnoreUpdate(),
    state=Subscription.PLANS,
    getter=plans_getter,
)

duration = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-subscription-duration"),
    Group(
        Select(
            text=I18nFormat(
                "btn-subscription-duration",
                period=F["item"]["period"],
                final_amount=F["item"]["final_amount"],
                discount_percent=F["item"]["discount_percent"],
                original_amount=F["item"]["original_amount"],
                currency=F["item"]["currency"],
                has_discount=F["item"]["has_discount"],
            ),
            id=f"{PURCHASE_PREFIX}select_duration",
            item_id_getter=lambda item: item["days"],
            items="durations",
            type_factory=int,
            on_click=on_duration_select,
        ),
        width=2,
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-back"),
            id="back_to_plans",
            state=Subscription.PLANS,
            when=~F["only_single_plan"],
        ),
        SwitchTo(
            text=I18nFormat("btn-back"),
            id="back_to_main",
            state=Subscription.MAIN,
            when=F["only_single_plan"],
        ),
        Start(
            text=I18nFormat("btn-main-menu"),
            id="back_main_menu",
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
        ),
    ),
    IgnoreUpdate(),
    state=Subscription.DURATION,
    getter=duration_getter,
)

payment_method = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-subscription-payment-method"),
    Column(
        Select(
            text=I18nFormat(
                "btn-subscription-payment-method",
                gateway_type=F["item"]["gateway_type"],
                price=F["item"]["price"],
                original_price=F["item"]["original_price"],
                currency=F["item"]["currency"],
                discount_percent=F["item"]["discount_percent"],
                has_discount=F["item"]["has_discount"],
            ),
            id=f"{PURCHASE_PREFIX}select_payment_method",
            item_id_getter=lambda item: item["gateway_type"],
            items="payment_methods",
            type_factory=PaymentGatewayType,
            on_click=on_payment_method_select,
        ),
    ),
    *get_back_and_main_menu_buttons(Subscription.DURATION),
    IgnoreUpdate(),
    state=Subscription.PAYMENT_METHOD,
    getter=payment_method_getter,
)

confirm = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-subscription-confirm"),
    Row(
        Url(
            text=I18nFormat("btn-subscription-pay"),
            url=Format("{url}"),
            when=F["url"],
        ),
        Button(
            text=I18nFormat("btn-subscription-get"),
            id=f"{PURCHASE_PREFIX}get",
            on_click=on_get_subscription,
            when=~F["url"],
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-subscription-back-payment-method"),
            id=f"{PURCHASE_PREFIX}back_payment_method",
            state=Subscription.PAYMENT_METHOD,
            when=~F["only_single_gateway"] & ~F["is_free"] & ~F["is_telegram_stars"] & ~F["is_yoomoney"] & ~F["is_heleket"],
        ),
        SwitchTo(
            text=I18nFormat("btn-back"),
            id=f"{PURCHASE_PREFIX}back_to_payment_method_stars",
            state=Subscription.PAYMENT_METHOD,
            when=(F["is_telegram_stars"] | F["is_yoomoney"] | F["is_heleket"]) & ~F["only_single_gateway"],
        ),
        SwitchTo(
            text=I18nFormat("btn-subscription-back-duration"),
            id=f"{PURCHASE_PREFIX}back_duration",
            state=Subscription.DURATION,
            when=F["only_single_gateway"] & ~F["only_single_duration"] | F["is_free"],
        ),
        Start(
            text=I18nFormat("btn-main-menu"),
            id="back_main_menu",
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
        ),
    ),
    IgnoreUpdate(),
    state=Subscription.CONFIRM,
    getter=confirm_getter,
)

confirm_balance = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-subscription-confirm-balance"),
    Row(
        Button(
            text=I18nFormat("btn-subscription-confirm-balance"),
            id=f"{PURCHASE_PREFIX}confirm_balance",
            on_click=on_confirm_balance_payment,
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-back"),
            id=f"{PURCHASE_PREFIX}back_payment_method",
            state=Subscription.PAYMENT_METHOD,
        ),
        Start(
            text=I18nFormat("btn-main-menu"),
            id="back_main_menu",
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
        ),
    ),
    IgnoreUpdate(),
    state=Subscription.CONFIRM_BALANCE,
    getter=confirm_balance_getter,
)

confirm_yoomoney = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-subscription-confirm-yoomoney"),
    Row(
        Url(
            text=I18nFormat("btn-subscription-pay"),
            url=Format("{url}"),
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-back"),
            id=f"{PURCHASE_PREFIX}back_payment_method",
            state=Subscription.PAYMENT_METHOD,
        ),
        Start(
            text=I18nFormat("btn-main-menu"),
            id="back_main_menu",
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
        ),
    ),
    IgnoreUpdate(),
    state=Subscription.CONFIRM_YOOMONEY,
    getter=confirm_yoomoney_getter,
)

confirm_yookassa = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-subscription-confirm-yookassa"),
    Row(
        Url(
            text=I18nFormat("btn-subscription-pay"),
            url=Format("{url}"),
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-back"),
            id=f"{PURCHASE_PREFIX}back_payment_method",
            state=Subscription.PAYMENT_METHOD,
        ),
        Start(
            text=I18nFormat("btn-main-menu"),
            id="back_main_menu",
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
        ),
    ),
    IgnoreUpdate(),
    state=Subscription.CONFIRM_YOOKASSA,
    getter=confirm_yookassa_getter,
)

add_device_success = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat(
        "msg-add-device-success-full",
        device_count=F["device_count"],
        device_count_word=F["device_count_word"],
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
    state=Subscription.ADD_DEVICE_SUCCESS,
    getter=add_device_success_getter,
)

# Экран со ссылкой платежа для дополнительных устройств
add_device_payment_link = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-add-device-payment-link"),
    Row(
        Url(
            text=I18nFormat("btn-pay"),
            url=Format("{payment_url}"),
        ),
        SwitchTo(
            text=I18nFormat("btn-back"),
            id="back_to_devices",
            state=Subscription.DEVICES,
        ),
    ),
    IgnoreUpdate(),
    state=Subscription.ADD_DEVICE_PAYMENT_LINK,
    getter=add_device_payment_link_getter,
)

success_payment = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-subscription-success"),
    Row(
        *connect_buttons,
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
    state=Subscription.SUCCESS,
    getter=success_payment_getter,
)

success_trial = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-subscription-trial"),
    Row(
        *connect_buttons,
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
    state=Subscription.TRIAL,
    getter=getter_connect,
)

failed = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-subscription-failed"),
    *get_back_and_main_menu_buttons(MainMenu.MAIN),  # Возвращаемся в главное меню
    IgnoreUpdate(),
    state=Subscription.FAILED,
)

referral_code_input = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-subscription-referral-code"),
    MessageInput(func=on_referral_code_input),
    SwitchTo(
        text=I18nFormat("btn-cancel"),
        id="cancel",
        state=Subscription.MAIN,
    ),
    IgnoreUpdate(),
    state=Subscription.REFERRAL_CODE,
)

referral_success = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-subscription-referral-success"),
    Row(
        *connect_buttons,
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
    state=Subscription.REFERRAL_SUCCESS,
    getter=referral_success_getter,
)

promocode_input = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-subscription-promocode"),
    MessageInput(func=on_promocode_input),
    Start(
        text=I18nFormat("btn-cancel"),
        id="cancel_promocode",
        state=MainMenu.MAIN,
        mode=StartMode.RESET_STACK,
    ),
    IgnoreUpdate(),
    state=Subscription.PROMOCODE,
)

# Окно управления устройствами
devices = Window(
    Banner(BannerName.SUBSCRIPTION),
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
    Row(
        Button(
            text=I18nFormat("btn-menu-add-device"),
            id="add_device",
            on_click=on_add_device,
            when=F["can_add_device"],
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-menu-extra-devices"),
            id="extra_devices_list",
            on_click=on_extra_devices_list,
            when=F["extra_devices"] > 0,
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-back"),
            id="back",
            state=Subscription.MAIN,
        ),
        Start(
            text=I18nFormat("btn-main-menu"),
            id="back_main_menu",
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
        ),
    ),
    IgnoreUpdate(),
    state=Subscription.DEVICES,
    getter=devices_getter,
)

# Окно выбора количества устройств для добавления
add_device = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat(
        "msg-add-device-full",
        device_price=F["device_price"],
    ),
    Row(
        Button(text=Format("1"), id="device_count_1", on_click=lambda c, w, m: on_add_device_select_count(c, w, m, "1")),
        Button(text=Format("2"), id="device_count_2", on_click=lambda c, w, m: on_add_device_select_count(c, w, m, "2")),
        Button(text=Format("3"), id="device_count_3", on_click=lambda c, w, m: on_add_device_select_count(c, w, m, "3")),
        Button(text=Format("4"), id="device_count_4", on_click=lambda c, w, m: on_add_device_select_count(c, w, m, "4")),
        Button(text=Format("5"), id="device_count_5", on_click=lambda c, w, m: on_add_device_select_count(c, w, m, "5")),
    ),
    Row(
        Button(text=Format("6"), id="device_count_6", on_click=lambda c, w, m: on_add_device_select_count(c, w, m, "6")),
        Button(text=Format("7"), id="device_count_7", on_click=lambda c, w, m: on_add_device_select_count(c, w, m, "7")),
        Button(text=Format("8"), id="device_count_8", on_click=lambda c, w, m: on_add_device_select_count(c, w, m, "8")),
        Button(text=Format("9"), id="device_count_9", on_click=lambda c, w, m: on_add_device_select_count(c, w, m, "9")),
        Button(text=Format("10"), id="device_count_10", on_click=lambda c, w, m: on_add_device_select_count(c, w, m, "10")),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-back"),
            id="back_to_extra_devices",
            state=Subscription.EXTRA_DEVICES_LIST,
        ),
        Start(
            text=I18nFormat("btn-main-menu"),
            id="back_main_menu",
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
        ),
    ),
    IgnoreUpdate(),
    state=Subscription.ADD_DEVICE_SELECT_COUNT,
    getter=add_device_select_count_getter,
)

# Окно выбора длительности покупки доп.устройств
add_device_duration = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat(
        "msg-add-device-duration",
        device_count=F["device_count"],
    ),
    Row(
        Button(
            text=I18nFormat(
                "btn-add-device-duration-full",
                days=F["days_full"],
                price=F["price_full"],
            ),
            id="duration_full",
            on_click=on_add_device_duration_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat(
                "btn-add-device-duration-month",
                days=F["days_month"],
                price=F["price_month"],
            ),
            id="duration_month",
            on_click=on_add_device_duration_select,
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-back"),
            id="back_to_count",
            state=Subscription.ADD_DEVICE_SELECT_COUNT,
        ),
        Start(
            text=I18nFormat("btn-main-menu"),
            id="back_main_menu",
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
        ),
    ),
    IgnoreUpdate(),
    state=Subscription.ADD_DEVICE_DURATION,
    getter=add_device_duration_getter,
)

# Окно выбора способа оплаты для добавления устройств
add_device_payment = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat(
        "msg-add-device-payment-full",
        device_count=F["device_count"],
    ),
    Column(
        Select(
            text=I18nFormat(
                "btn-subscription-payment-method",
                gateway_type=F["item"]["gateway_type"],
                price=F["item"]["price"],
                original_price=F["item"]["original_price"],
                discount_percent=F["item"]["discount_percent"],
                has_discount=F["item"]["has_discount"],
            ),
            id="select_add_device_payment",
            item_id_getter=lambda item: item["gateway_type"],
            items="payment_methods",
            type_factory=PaymentGatewayType,
            on_click=on_add_device_payment_select,
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-back"),
            id="back_to_duration",
            state=Subscription.ADD_DEVICE_DURATION,
        ),
        Start(
            text=I18nFormat("btn-main-menu"),
            id="back_main_menu_payment",
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
        ),
    ),
    IgnoreUpdate(),
    state=Subscription.ADD_DEVICE_PAYMENT,
    getter=add_device_payment_getter,
)

# Окно подтверждения покупки устройств
add_device_confirm = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat(
        "msg-add-device-confirm-full",
        device_count=F["device_count"],
        selected_method=F["selected_method"],
        balance=F["balance"],
        currency=F["currency"],
        new_balance=F["new_balance"],
    ),
    Row(
        # Если есть payment_url (оплата через шлюз) - показываем URL кнопку
        Url(
            text=I18nFormat("btn-confirm-payment"),
            url=Format("{payment_url}"),
            when=F["payment_url"],
        ),
        # Если нет payment_url (оплата с баланса) - показываем обычную кнопку
        Button(
            text=I18nFormat("btn-confirm-payment"),
            id="confirm_add_device",
            on_click=on_add_device_confirm,
            when=~F["payment_url"],
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-back"),
            id="back_to_payment",
            state=Subscription.ADD_DEVICE_PAYMENT,
        ),
        Start(
            text=I18nFormat("btn-main-menu"),
            id="main_menu_from_confirm",
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
        ),
    ),
    IgnoreUpdate(),
    state=Subscription.ADD_DEVICE_CONFIRM,
    getter=add_device_confirm_getter,
)

# Окно списка купленных дополнительных устройств
extra_devices_list = Window(
    Banner(BannerName.SUBSCRIPTION),
    I18nFormat("msg-extra-devices-list"),
    ListGroup(
        Row(
            Button(
                text=Format("{item[device_count]} шт."),
                id="info_count",
            ),
            Button(
                text=Format("❌"),
                id="delete",
                on_click=on_delete_extra_device_purchase,
            ),
        ),
        id="extra_devices_list_group",
        item_id_getter=lambda item: str(item["id"]),
        items="purchases",
        when=~F["purchases_empty"],
    ),
    # Кнопка добавления устройств (если доступно)
    Row(
        SwitchTo(
            text=I18nFormat("btn-menu-add-device"),
            id="add_device",
            state=Subscription.ADD_DEVICE_SELECT_COUNT,
            when=F["can_add_device"],
        ),
    ),
    Row(
        Start(
            text=I18nFormat("btn-back"),
            id="back_to_devices",
            state=MainMenu.DEVICES,
            mode=StartMode.RESET_STACK,
        ),
        Start(
            text=I18nFormat("btn-main-menu"),
            id="back_main_menu",
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
        ),
    ),
    IgnoreUpdate(),
    state=Subscription.EXTRA_DEVICES_LIST,
    getter=extra_devices_list_getter,
)

router = Dialog(
    subscription,
    devices,
    add_device,
    add_device_duration,
    add_device_payment,
    add_device_confirm,
    add_device_success,
    add_device_payment_link,
    extra_devices_list,
    referral_code_input,
    referral_success,
    promocode_input,
    plans,
    duration,
    payment_method,
    confirm,
    confirm_balance,
    confirm_yoomoney,
    confirm_yookassa,
    success_payment,
    success_trial,
    failed,
)