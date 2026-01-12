from aiogram_dialog import Dialog, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Column, Row, SwitchTo
from magic_filter import F

from src.bot.routers.dashboard.remnashop.referral.getters import (
    accrual_strategy_getter,
    level_getter,
    referral_getter,
    reward_getter,
    reward_strategy_getter,
    reward_type_getter,
    invite_message_getter,
    invite_preview_getter,
)
from src.bot.routers.dashboard.remnashop.referral.handlers import (
    on_accrual_strategy_select,
    on_enable_toggle,
    on_level_select,
    on_level_switch,
    on_reward_free_select,
    on_reward_input,
    on_reward_preset_select,
    on_reward_type_select,
    on_reward_strategy_select,
    on_referral_cancel,
    on_referral_accept,
    on_reward_manual_input_cancel,
    on_submenu_cancel,
    on_submenu_accept,
    on_invite_message_input,
    on_invite_message_cancel,
    on_invite_message_accept,
    on_invite_message_reset,
    on_invite_preview_close,
)
from src.bot.states import RemnashopReferral
from src.bot.widgets import Banner, I18nFormat, IgnoreUpdate
from src.core.enums import BannerName

# Главное окно настроек реферальной системы
referral = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-referral-main"),
    Row(
        SwitchTo(
            text=I18nFormat("btn-referral-level"),
            id="level",
            state=RemnashopReferral.LEVEL,
        ),
        SwitchTo(
            text=I18nFormat("btn-referral-reward-type"),
            id="reward_type",
            state=RemnashopReferral.REWARD_TYPE,
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-referral-accrual-strategy"),
            id="accrual_strategy",
            state=RemnashopReferral.ACCRUAL_STRATEGY,
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-referral-reward-strategy"),
            id="reward_strategy",
            state=RemnashopReferral.REWARD_STRATEGY,
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-referral-reward"),
            id="reward",
            state=RemnashopReferral.REWARD,
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-referral-invite-message"),
            id="invite_message",
            state=RemnashopReferral.INVITE_MESSAGE,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_referral_cancel,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_referral_accept,
        ),
    ),
    IgnoreUpdate(),
    state=RemnashopReferral.MAIN,
    getter=referral_getter,
)

# Окно выбора уровня с радиокнопками
level = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-referral-level"),
    Row(
        Button(
            text=I18nFormat("btn-referral-level-one", selected=F["level_one_selected"]),
            id="level_1",
            on_click=on_level_select,
        ),
        Button(
            text=I18nFormat("btn-referral-level-two", selected=F["level_two_selected"]),
            id="level_2",
            on_click=on_level_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_submenu_cancel,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_submenu_accept,
        ),
    ),
    IgnoreUpdate(),
    state=RemnashopReferral.LEVEL,
    getter=level_getter,
)

# Окно выбора типа награды с радиокнопками
reward_type = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-referral-reward-type"),
    Row(
        Button(
            text=I18nFormat("btn-referral-type-money", selected=F["type_money_selected"]),
            id="type_MONEY",
            on_click=on_reward_type_select,
        ),
        Button(
            text=I18nFormat("btn-referral-type-days", selected=F["type_days_selected"]),
            id="type_EXTRA_DAYS",
            on_click=on_reward_type_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_submenu_cancel,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_submenu_accept,
        ),
    ),
    IgnoreUpdate(),
    state=RemnashopReferral.REWARD_TYPE,
    getter=reward_type_getter,
)

# Окно выбора условия начисления с радиокнопками
accrual_strategy = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-referral-accrual-strategy"),
    Row(
        Button(
            text=I18nFormat("btn-referral-accrual-first", selected=F["accrual_first_selected"]),
            id="accrual_ON_FIRST_PAYMENT",
            on_click=on_accrual_strategy_select,
        ),
        Button(
            text=I18nFormat("btn-referral-accrual-each", selected=F["accrual_each_selected"]),
            id="accrual_ON_EACH_PAYMENT",
            on_click=on_accrual_strategy_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_submenu_cancel,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_submenu_accept,
        ),
    ),
    IgnoreUpdate(),
    state=RemnashopReferral.ACCRUAL_STRATEGY,
    getter=accrual_strategy_getter,
)

# Окно выбора формы начисления с радиокнопками
reward_strategy = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-referral-reward-strategy"),
    Row(
        Button(
            text=I18nFormat("btn-referral-strategy-fixed", selected=F["strategy_fixed_selected"]),
            id="strategy_AMOUNT",
            on_click=on_reward_strategy_select,
        ),
        Button(
            text=I18nFormat("btn-referral-strategy-percent", selected=F["strategy_percent_selected"]),
            id="strategy_PERCENT",
            on_click=on_reward_strategy_select,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_submenu_cancel,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_submenu_accept,
        ),
    ),
    IgnoreUpdate(),
    state=RemnashopReferral.REWARD_STRATEGY,
    getter=reward_strategy_getter,
)

# Окно награды с кнопками выбора (как в Комиссии)
reward = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-referral-reward"),
    # Переключатель уровней (показывается только если выбрано 2 уровня)
    Row(
        Button(
            text=I18nFormat("btn-reward-level-one", selected=F["editing_level_one"]),
            id="level_switch_1",
            on_click=on_level_switch,
        ),
        Button(
            text=I18nFormat("btn-reward-level-two", selected=F["editing_level_two"]),
            id="level_switch_2",
            on_click=on_level_switch,
        ),
        when=F["show_level_switch"],
    ),
    # Кнопка "Без награды" сверху
    Button(
        text=I18nFormat("btn-reward-free", selected=F["reward_0_selected"]),
        id="reward_free",
        on_click=on_reward_free_select,
    ),
    # ===== ПРОЦЕНТНЫЕ КНОПКИ (5-50%) =====
    Row(
        Button(
            text=I18nFormat("btn-reward-5", selected=F["reward_5_selected"]),
            id="reward_5",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-10", selected=F["reward_10_selected"]),
            id="reward_10",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-15", selected=F["reward_15_selected"]),
            id="reward_15",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-20", selected=F["reward_20_selected"]),
            id="reward_20",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-25", selected=F["reward_25_selected"]),
            id="reward_25",
            on_click=on_reward_preset_select,
        ),
        when=F["is_percent"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-reward-30", selected=F["reward_30_selected"]),
            id="reward_30",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-35", selected=F["reward_35_selected"]),
            id="reward_35",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-40", selected=F["reward_40_selected"]),
            id="reward_40",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-45", selected=F["reward_45_selected"]),
            id="reward_45",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-50", selected=F["reward_50_selected"]),
            id="reward_50",
            on_click=on_reward_preset_select,
        ),
        when=F["is_percent"],
    ),
    # ===== КНОПКИ ДЕНЕЖНЫХ СУММ (10-500₽) =====
    Row(
        Button(
            text=I18nFormat("btn-reward-fixed-10", selected=F["reward_10_selected"], suffix=F["reward_suffix"]),
            id="reward_10",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-fixed-20", selected=F["reward_20_selected"], suffix=F["reward_suffix"]),
            id="reward_20",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-fixed-30", selected=F["reward_30_selected"], suffix=F["reward_suffix"]),
            id="reward_30",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-fixed-50", selected=F["reward_50_selected"], suffix=F["reward_suffix"]),
            id="reward_50",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-fixed-100", selected=F["reward_100_selected"], suffix=F["reward_suffix"]),
            id="reward_100",
            on_click=on_reward_preset_select,
        ),
        when=F["is_money_fixed"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-reward-fixed-150", selected=F["reward_150_selected"], suffix=F["reward_suffix"]),
            id="reward_150",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-fixed-200", selected=F["reward_200_selected"], suffix=F["reward_suffix"]),
            id="reward_200",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-fixed-250", selected=F["reward_250_selected"], suffix=F["reward_suffix"]),
            id="reward_250",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-fixed-300", selected=F["reward_300_selected"], suffix=F["reward_suffix"]),
            id="reward_300",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-fixed-500", selected=F["reward_500_selected"], suffix=F["reward_suffix"]),
            id="reward_500",
            on_click=on_reward_preset_select,
        ),
        when=F["is_money_fixed"],
    ),
    # ===== КНОПКИ ДНЕЙ (1-15) =====
    Row(
        Button(
            text=I18nFormat("btn-reward-days-1", selected=F["reward_1_selected"]),
            id="reward_1",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-days-2", selected=F["reward_2_selected"]),
            id="reward_2",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-days-3", selected=F["reward_3_selected"]),
            id="reward_3",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-days-4", selected=F["reward_4_selected"]),
            id="reward_4",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-days-5", selected=F["reward_5_selected"]),
            id="reward_5",
            on_click=on_reward_preset_select,
        ),
        when=F["is_extra_days"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-reward-days-6", selected=F["reward_6_selected"]),
            id="reward_6",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-days-7", selected=F["reward_7_selected"]),
            id="reward_7",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-days-8", selected=F["reward_8_selected"]),
            id="reward_8",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-days-9", selected=F["reward_9_selected"]),
            id="reward_9",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-days-10", selected=F["reward_10_selected"]),
            id="reward_10",
            on_click=on_reward_preset_select,
        ),
        when=F["is_extra_days"],
    ),
    Row(
        Button(
            text=I18nFormat("btn-reward-days-11", selected=F["reward_11_selected"]),
            id="reward_11",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-days-12", selected=F["reward_12_selected"]),
            id="reward_12",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-days-13", selected=F["reward_13_selected"]),
            id="reward_13",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-days-14", selected=F["reward_14_selected"]),
            id="reward_14",
            on_click=on_reward_preset_select,
        ),
        Button(
            text=I18nFormat("btn-reward-days-15", selected=F["reward_15_selected"]),
            id="reward_15",
            on_click=on_reward_preset_select,
        ),
        when=F["is_extra_days"],
    ),
    # Кнопка ручного ввода
    Button(
        text=I18nFormat("btn-manual-input"),
        id="manual_input_dummy",
        on_click=on_reward_preset_select,
    ),
    # Ручной ввод через MessageInput
    MessageInput(func=on_reward_input),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_submenu_cancel,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_submenu_accept,
        ),
    ),
    IgnoreUpdate(),
    state=RemnashopReferral.REWARD,
    getter=reward_getter,
)

# Окно для ручного ввода награды
reward_manual_input = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-referral-reward-manual"),
    # Ручной ввод через MessageInput
    MessageInput(func=on_reward_input),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_reward_manual_input_cancel,
        ),
    ),
    IgnoreUpdate(),
    state=RemnashopReferral.REWARD_MANUAL_INPUT,
)

# Окно настройки сообщения приглашения
invite_message = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-referral-invite-message", current_message=F["current_message"]),
    Row(
        SwitchTo(
            text=I18nFormat("btn-invite-edit"),
            id="edit",
            state=RemnashopReferral.INVITE_MESSAGE_EDIT,
        ),
    ),
    Row(
        SwitchTo(
            text=I18nFormat("btn-invite-preview"),
            id="preview",
            state=RemnashopReferral.INVITE_MESSAGE_PREVIEW,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-reset-default"),
            id="reset",
            on_click=on_invite_message_reset,
        ),
    ),
    Row(
        Button(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            on_click=on_invite_message_cancel,
        ),
        Button(
            text=I18nFormat("btn-accept"),
            id="accept",
            on_click=on_invite_message_accept,
        ),
    ),
    IgnoreUpdate(),
    state=RemnashopReferral.INVITE_MESSAGE,
    getter=invite_message_getter,
)

# Окно редактирования сообщения приглашения
invite_message_edit = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-referral-invite-edit", current_message=F["current_message"]),
    MessageInput(func=on_invite_message_input),
    Row(
        SwitchTo(
            text=I18nFormat("btn-cancel"),
            id="cancel",
            state=RemnashopReferral.INVITE_MESSAGE,
        ),
    ),
    IgnoreUpdate(),
    state=RemnashopReferral.INVITE_MESSAGE_EDIT,
    getter=invite_message_getter,
)

# Окно предпросмотра приглашения
invite_message_preview = Window(
    Banner(BannerName.DASHBOARD),
    I18nFormat("msg-referral-invite-preview", preview_message=F["preview_message"]),
    Row(
        Button(
            text=I18nFormat("btn-invite-close-preview"),
            id="close",
            on_click=on_invite_preview_close,
        ),
    ),
    IgnoreUpdate(),
    state=RemnashopReferral.INVITE_MESSAGE_PREVIEW,
    getter=invite_preview_getter,
)

router = Dialog(
    referral,
    level,
    reward_type,
    accrual_strategy,
    reward_strategy,
    reward,
    reward_manual_input,
    invite_message,
    invite_message_edit,
    invite_message_preview,
)
