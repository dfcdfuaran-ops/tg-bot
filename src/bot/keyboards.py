from typing import Final, Tuple

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram_dialog import StartMode
from aiogram_dialog.widgets.kbd import Row, Start, SwitchTo, Url, WebApp
from aiogram_dialog.widgets.text import Format
from magic_filter import F

from src.bot.states import DashboardUser, MainMenu, Subscription
from src.bot.widgets.i18n_format import I18nFormat
from src.core.constants import GOTO_PREFIX, PURCHASE_PREFIX, REPOSITORY, T_ME
from src.core.enums import PurchaseType
from src.core.utils.formatters import format_username_to_url

CALLBACK_CHANNEL_CONFIRM: Final[str] = "channel_confirm"
CALLBACK_RULES_ACCEPT: Final[str] = "rules_accept"

connect_buttons = (
    Start(
        text=I18nFormat("btn-menu-connect"),
        id="connect_menu",
        state=MainMenu.CONNECT,
        mode=StartMode.RESET_STACK,
        when=F["connectable"],
    ),
)

# Создаем функцию для получения кнопок "Назад" и "Главное меню" в одной строке
def get_back_and_main_menu_buttons(back_state) -> Tuple[Row]:
    """
    Возвращает Row с кнопками "Назад" и "Главное меню" в одной строке.
    
    Args:
        back_state: Состояние для кнопки "Назад"
    
    Returns:
        Tuple с одним элементом Row
    """
    return (
        Row(
            SwitchTo(
                text=I18nFormat("btn-back"),
                id="back",
                state=back_state,
            ),
            Start(
                text=I18nFormat("btn-main-menu"),
                id="back_main_menu",
                state=MainMenu.MAIN,
                mode=StartMode.RESET_STACK,
            ),
        ),
    )

# Старые константы для обратной совместимости
back_main_menu_button = (
    Row(
        Start(
            text=I18nFormat("btn-back-main-menu"),
            id="back_main_menu",
            state=MainMenu.MAIN,
            mode=StartMode.RESET_STACK,
        ),
    ),
)

main_menu_button = (
    Start(
        text=I18nFormat("btn-main-menu"),
        id="back_main_menu",
        state=MainMenu.MAIN,
        mode=StartMode.RESET_STACK,
    ),
)


def get_goto_buttons(is_referral_enable: bool) -> list[InlineKeyboardButton]:
    buttons = [
        InlineKeyboardButton(
            text="btn-contact-support",
        ),
        InlineKeyboardButton(
            text="btn-goto-subscription",
            callback_data=f"{GOTO_PREFIX}{Subscription.MAIN.state}",
        ),
        InlineKeyboardButton(
            text="btn-goto-promocode",
            callback_data=f"{GOTO_PREFIX}{Subscription.PROMOCODE.state}",
        ),
    ]

    if is_referral_enable:
        buttons.append(
            InlineKeyboardButton(
                text="btn-goto-invite",
                callback_data=f"{GOTO_PREFIX}{MainMenu.INVITE.state}",
            )
        )

    return buttons


def get_renew_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="btn-goto-subscription-renew",
            callback_data=f"{GOTO_PREFIX}{PURCHASE_PREFIX}{PurchaseType.RENEW}",
        ),
    )
    return builder.as_markup()


def get_buy_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="btn-goto-subscription",
            callback_data=f"{GOTO_PREFIX}{PURCHASE_PREFIX}{PurchaseType.NEW}",
        ),
    )
    return builder.as_markup()


def get_channel_keyboard(channel_link: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="btn-channel-join",
            url=channel_link,
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="btn-channel-confirm",
            callback_data=CALLBACK_CHANNEL_CONFIRM,
        ),
    )
    return builder.as_markup()


def get_rules_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="btn-rules-accept",
            callback_data=CALLBACK_RULES_ACCEPT,
        ),
    )
    return builder.as_markup()


def get_contact_support_keyboard(username: str, text: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="btn-contact-support",
            url=format_username_to_url(username, text),
        ),
    )
    return builder.as_markup()


def get_remnashop_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="btn-remnashop-github",
            url=REPOSITORY,
        ),
        InlineKeyboardButton(
            text="btn-remnashop-telegram",
            url=f"{T_ME}remna_shop",
        ),
        # InlineKeyboardButton(
        #     text="btn-remnashop-guide",
        #     url=f"{T_ME}remna_shop",
        # ),
    )

    builder.row(
        InlineKeyboardButton(
            text="btn-remnashop-donate",
            url="https://yookassa.ru/my/i/Z8AkHJ_F9sO_/l",
        )
    )

    return builder.as_markup()


def get_remnashop_update_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="btn-remnashop-release-latest",
            url=f"{REPOSITORY}/releases/latest",
        ),
        InlineKeyboardButton(
            text="btn-remnashop-how-upgrade",
            url=f"{REPOSITORY}?tab=readme-ov-file#step-5--how-to-upgrade",
        ),
    )

    return builder.as_markup()


def get_user_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="btn-goto-user-profile",
            callback_data=f"{GOTO_PREFIX}{DashboardUser.MAIN.state}:{telegram_id}",
        ),
    )

    return builder.as_markup()
    return builder.as_markup()


def get_close_keyboard() -> InlineKeyboardMarkup:
    """Get inline keyboard with close button."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="btn-notification-close",
            callback_data="close_notification",
        ),
    )
    
    return builder.as_markup()


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Get inline keyboard with main menu button."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(
            text="btn-goto-main-menu",
            callback_data=f"{GOTO_PREFIX}{MainMenu.MAIN.state}",
        ),
    )
    
    return builder.as_markup()
