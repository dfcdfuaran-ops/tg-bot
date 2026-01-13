from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager, ShowMode, SubManager, StartMode
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Select
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from loguru import logger
from pydantic import SecretStr

from src.bot.states import RemnashopGateways, DashboardSettings
from src.core.constants import USER_KEY
from src.core.enums import Currency
from src.core.utils.formatters import format_user_log as log
from src.core.utils.message_payload import MessagePayload
from src.infrastructure.database.models.dto import UserDto
from src.services.notification import NotificationService
from src.services.payment_gateway import PaymentGatewayService
from src.services.settings import SettingsService


@inject
async def on_gateway_select(
    callback: CallbackQuery,
    widget: Button,
    sub_manager: SubManager,
    payment_gateway_service: FromDishka[PaymentGatewayService],
    notification_service: FromDishka[NotificationService],
) -> None:
    user: UserDto = sub_manager.middleware_data[USER_KEY]
    gateway_id = int(sub_manager.item_id)
    gateway = await payment_gateway_service.get(gateway_id)

    if not gateway:
        raise ValueError(f"Attempted to select non-existent gateway '{gateway_id}'")

    logger.info(f"{log(user)} Gateway '{gateway_id}' selected")

    if not gateway.settings:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-gateway-not-configurable"),
        )
        return

    sub_manager.manager.dialog_data["gateway_id"] = gateway_id
    await sub_manager.switch_to(state=RemnashopGateways.SETTINGS)


@inject
async def on_gateway_test(
    callback: CallbackQuery,
    widget: Button,
    sub_manager: SubManager,
    payment_gateway_service: FromDishka[PaymentGatewayService],
    notification_service: FromDishka[NotificationService],
) -> None:
    user: UserDto = sub_manager.middleware_data[USER_KEY]
    gateway_id = int(sub_manager.item_id)
    gateway = await payment_gateway_service.get(gateway_id)

    if not gateway:
        raise ValueError(f"Attempted to test non-existent gateway '{gateway_id}'")

    if gateway.settings and not gateway.settings.is_configure:
        logger.warning(f"{log(user)} Gateway '{gateway_id}' is not configured")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-gateway-not-configured"),
        )
        return

    logger.info(f"{log(user)} Testing gateway '{gateway_id}'")

    try:
        payment = await payment_gateway_service.create_test_payment(user, gateway.type)
        logger.info(f"{log(user)} Test payment successful for gateway '{gateway_id}'")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(
                i18n_key="ntf-gateway-test-payment-created",
                i18n_kwargs={"url": payment.url},
            ),
        )

    except Exception as exception:
        logger.exception(
            f"{log(user)} Test payment failed for gateway '{gateway_id}'. Exception: {exception}"
        )
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-gateway-test-payment-error"),
        )
        raise


@inject
async def on_active_toggle(
    callback: CallbackQuery,
    widget: Button,
    sub_manager: SubManager,
    payment_gateway_service: FromDishka[PaymentGatewayService],
    notification_service: FromDishka[NotificationService],
) -> None:
    await sub_manager.load_data()
    user: UserDto = sub_manager.middleware_data[USER_KEY]
    gateway_id = int(sub_manager.item_id)
    gateway = await payment_gateway_service.get(gateway_id)

    if not gateway:
        raise ValueError(f"Attempted to toggle non-existent gateway '{gateway_id}'")

    if gateway.settings and not gateway.settings.is_configure:
        logger.warning(f"{log(user)} Gateway '{gateway_id}' is not configured")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-gateway-not-configured"),
        )
        return

    # Сохраняем изменения только в dialog_data, а не в БД
    if "pending_changes" not in sub_manager.manager.dialog_data:
        sub_manager.manager.dialog_data["pending_changes"] = {}
    
    if gateway_id not in sub_manager.manager.dialog_data["pending_changes"]:
        # Сохраняем исходное состояние при первом изменении
        sub_manager.manager.dialog_data["pending_changes"][gateway_id] = {
            "is_active": gateway.is_active
        }
    
    # Переключаем состояние в памяти
    gateway.is_active = not gateway.is_active
    logger.info(f"{log(user)} Toggled active state for gateway '{gateway_id}' (pending)")
    
    # Сохраняем текущее состояние (не исходное!)
    if "current_state" not in sub_manager.manager.dialog_data:
        sub_manager.manager.dialog_data["current_state"] = {}
    sub_manager.manager.dialog_data["current_state"][gateway_id] = {
        "is_active": gateway.is_active
    }
    
    # Временно обновляем в БД для отображения (но можем откатить)
    await payment_gateway_service.update(gateway)


async def on_field_select(
    callback: CallbackQuery,
    widget: Select,
    dialog_manager: DialogManager,
    selected_field: str,
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    dialog_manager.dialog_data["selected_field"] = selected_field
    logger.info(f"{log(user)} Selected field '{selected_field}' for editing")
    await dialog_manager.switch_to(state=RemnashopGateways.FIELD)


@inject
async def on_field_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    payment_gateway_service: FromDishka[PaymentGatewayService],
    notification_service: FromDishka[NotificationService],
) -> None:
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    gateway_id = dialog_manager.dialog_data["gateway_id"]
    selected_field = dialog_manager.dialog_data["selected_field"]

    if message.text is None:
        logger.warning(f"{log(user)} Empty input for field '{selected_field}'")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-gateway-field-wrong-value"),
        )
        return

    gateway = await payment_gateway_service.get(gateway_id)

    if not gateway or not gateway.settings:
        await dialog_manager.switch_to(state=RemnashopGateways.MAIN)
        raise ValueError(f"Attempted update of non-existent gateway '{gateway_id}'")

    input_value = message.text

    if selected_field in ["api_key", "secret_key"]:
        input_value = SecretStr(input_value)  # type: ignore[assignment]

    try:
        setattr(gateway.settings, selected_field, input_value)
    except ValueError:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-gateway-field-wrong-value"),
        )
        return

    await payment_gateway_service.update(gateway)
    logger.info(f"{log(user)} Updated '{selected_field}' for gateway '{gateway_id}'")
    await dialog_manager.switch_to(state=RemnashopGateways.SETTINGS)


@inject
async def on_default_currency_select(
    callback: CallbackQuery,
    widget: Select[Currency],
    dialog_manager: DialogManager,
    selected_currency: Currency,
    settings_service: FromDishka[SettingsService],
) -> None:
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Сохраняем исходную валюту при первом изменении
    if "pending_currency" not in dialog_manager.dialog_data:
        current_currency = await settings_service.get_default_currency()
        dialog_manager.dialog_data["pending_currency"] = current_currency
    
    logger.info(f"{log(user)} Set default currency '{selected_currency}' (pending)")
    await settings_service.set_default_currency(selected_currency)


@inject
async def on_gateway_move(
    callback: CallbackQuery,
    widget: Button,
    sub_manager: SubManager,
    payment_gateway_service: FromDishka[PaymentGatewayService],
) -> None:
    await sub_manager.load_data()
    user: UserDto = sub_manager.middleware_data[USER_KEY]
    gateway_id = int(sub_manager.item_id)

    # Сохраняем изменения placement в pending
    if "pending_placement" not in sub_manager.manager.dialog_data:
        # Получаем и сохраняем текущий порядок всех шлюзов
        gateways = await payment_gateway_service.get_all(sorted=True)
        sub_manager.manager.dialog_data["pending_placement"] = {
            gw.id: gw.order_index for gw in gateways
        }

    moved = await payment_gateway_service.move_gateway_up(gateway_id)
    if moved:
        logger.info(f"{log(user)} Moved plan '{gateway_id}' up successfully (pending)")
    else:
        logger.warning(f"{log(user)} Failed to move plan '{gateway_id}' up")


@inject
async def on_gateways_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    payment_gateway_service: FromDishka[PaymentGatewayService],
) -> None:
    """Отменить все изменения и вернуться к исходному состоянию"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Восстанавливаем исходное состояние из pending_changes
    if "pending_changes" in dialog_manager.dialog_data:
        for gateway_id_str, original_state in dialog_manager.dialog_data["pending_changes"].items():
            gateway_id = int(gateway_id_str)  # Конвертируем ключ из словаря в int
            gateway = await payment_gateway_service.get(gateway_id)
            if gateway:
                gateway.is_active = original_state["is_active"]
                await payment_gateway_service.update(gateway)
                logger.info(f"{log(user)} Reverted gateway '{gateway_id}' to original state")
        
        # Очищаем pending_changes
        dialog_manager.dialog_data.pop("pending_changes", None)
        dialog_manager.dialog_data.pop("current_state", None)
    
    logger.info(f"{log(user)} Cancelled all gateway changes")
    
    # Закрываем диалог и возвращаемся в родительское меню
    await dialog_manager.done()


@inject
async def on_gateways_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принять все изменения"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Изменения уже в БД, просто очищаем pending_changes
    if "pending_changes" in dialog_manager.dialog_data:
        dialog_manager.dialog_data.pop("pending_changes", None)
        dialog_manager.dialog_data.pop("current_state", None)
        logger.info(f"{log(user)} Accepted all gateway changes")
    
    # Закрываем диалог и возвращаемся в главное меню
    await dialog_manager.done()


@inject
async def on_placement_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    payment_gateway_service: FromDishka[PaymentGatewayService],
) -> None:
    """Отменить изменения порядка шлюзов"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    if "pending_placement" in dialog_manager.dialog_data:
        # Восстанавливаем исходный порядок
        for gateway_id, original_order in dialog_manager.dialog_data["pending_placement"].items():
            gateway = await payment_gateway_service.get(gateway_id)
            if gateway:
                gateway.order_index = original_order
                await payment_gateway_service.update(gateway)
        
        dialog_manager.dialog_data.pop("pending_placement", None)
        logger.info(f"{log(user)} Cancelled placement changes")


@inject
async def on_placement_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принять изменения порядка шлюзов"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    if "pending_placement" in dialog_manager.dialog_data:
        dialog_manager.dialog_data.pop("pending_placement", None)
        logger.info(f"{log(user)} Accepted placement changes")


@inject
async def on_currency_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Отменить изменение валюты по умолчанию"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    if "pending_currency" in dialog_manager.dialog_data:
        # Восстанавливаем исходную валюту
        original_currency = dialog_manager.dialog_data["pending_currency"]
        await settings_service.set_default_currency(original_currency)
        dialog_manager.dialog_data.pop("pending_currency", None)
        logger.info(f"{log(user)} Cancelled currency change")


@inject
async def on_currency_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принять изменение валюты по умолчанию"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    if "pending_currency" in dialog_manager.dialog_data:
        dialog_manager.dialog_data.pop("pending_currency", None)
        logger.info(f"{log(user)} Accepted currency change")
    
    # Навигируем обратно в главное меню gateways
    await dialog_manager.switch_to(RemnashopGateways.MAIN)


@inject
async def on_placement_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    payment_gateway_service: FromDishka[PaymentGatewayService],
) -> None:
    """Отменить изменения позиционирования шлюзов"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    if "pending_placement" in dialog_manager.dialog_data:
        original_order = dialog_manager.dialog_data["pending_placement"]
        # Восстанавливаем исходный порядок всех шлюзов
        for gateway_id_str, order_index in original_order.items():
            gateway_id = int(gateway_id_str)
            gateway = await payment_gateway_service.get(gateway_id)
            if gateway:
                gateway.order_index = order_index
                await payment_gateway_service.update(gateway)
        
        dialog_manager.dialog_data.pop("pending_placement", None)
        logger.info(f"{log(user)} Cancelled placement changes")


@inject
async def on_placement_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принять изменения позиционирования шлюзов"""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    if "pending_placement" in dialog_manager.dialog_data:
        dialog_manager.dialog_data.pop("pending_placement", None)
        logger.info(f"{log(user)} Accepted placement changes")
    
    # Навигируем обратно в главное меню gateways
    await dialog_manager.switch_to(RemnashopGateways.MAIN)
