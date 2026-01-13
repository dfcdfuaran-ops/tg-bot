from aiogram.types import CallbackQuery, Message
from aiogram_dialog import DialogManager, ShowMode, StartMode
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from fluentogram import TranslatorRunner
from loguru import logger

from src.bot.states import RemnashopReferral, DashboardSettings
from src.core.constants import USER_KEY
from src.core.enums import (
    ReferralAccrualStrategy,
    ReferralLevel,
    ReferralRewardStrategy,
    ReferralRewardType,
)
from src.core.utils.formatters import format_user_log as log
from src.core.utils.message_payload import MessagePayload
from src.infrastructure.database.models.dto import UserDto
from src.services.notification import NotificationService
from src.services.settings import SettingsService


def _ensure_reward_backup(current: dict) -> None:
    """Создает backup наград перед первым изменением, если его еще нет.
    
    ВАЖНО: Сохраняет текущие значения AS-IS (включая None).
    Функция on_submenu_cancel должна обрабатывать None значения.
    """
    if "submenu_backup_reward_strategy" not in current:
        current["submenu_backup_reward_strategy"] = current.get("reward_strategy")
        current["submenu_backup_reward_level_1"] = current.get("reward_level_1")
        current["submenu_backup_reward_level_2"] = current.get("reward_level_2")
        # Сохраняем флаг что backup был создан
        current["has_reward_backup"] = True


@inject
async def on_enable_toggle(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Toggle включения/выключения реферальной системы."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]

    settings = await settings_service.get()
    settings.referral.enable = not settings.referral.enable
    await settings_service.update(settings)

    logger.info(
        f"{log(user)} Successfully toggled referral system status to '{settings.referral.enable}'"
    )


@inject
async def on_level_select(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор уровня реферальной системы (радиокнопка)."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Извлекаем уровень из widget_id (level_1 или level_2)
    level = int(widget.widget_id.split("_")[1])
    
    current = dialog_manager.dialog_data.get("current_referral", {})
    
    # Сохраняем исходное значение перед первым изменением в этом подменю
    if "submenu_backup_level" not in current:
        current["submenu_backup_level"] = current.get("level")
    
    current["level"] = level
    current["editing_field"] = "level"  # Отслеживаем какое поле редактируется
    dialog_manager.dialog_data["current_referral"] = current
    
    logger.debug(f"{log(user)} Selected referral level: {level}")


@inject
async def on_reward_type_select(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор типа награды (радиокнопка)."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Извлекаем тип из widget_id (type_MONEY или type_EXTRA_DAYS)
    reward_type = widget.widget_id.split("_", 1)[1]
    
    current = dialog_manager.dialog_data.get("current_referral", {})
    
    # Сохраняем исходное значение перед первым изменением в этом подменю
    if "submenu_backup_reward_type" not in current:
        current["submenu_backup_reward_type"] = current.get("reward_type")
    
    current["reward_type"] = reward_type
    current["editing_field"] = "reward_type"  # Отслеживаем какое поле редактируется
    dialog_manager.dialog_data["current_referral"] = current
    
    logger.debug(f"{log(user)} Selected reward type: {reward_type}")


@inject
async def on_accrual_strategy_select(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор условия начисления (радиокнопка)."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Извлекаем стратегию из widget_id (accrual_ON_FIRST_PAYMENT или accrual_ON_EACH_PAYMENT)
    strategy = widget.widget_id.split("_", 1)[1]
    
    current = dialog_manager.dialog_data.get("current_referral", {})
    
    # Сохраняем исходное значение перед первым изменением в этом подменю
    if "submenu_backup_accrual_strategy" not in current:
        current["submenu_backup_accrual_strategy"] = current.get("accrual_strategy")
    
    current["accrual_strategy"] = strategy
    current["editing_field"] = "accrual_strategy"  # Отслеживаем какое поле редактируется
    dialog_manager.dialog_data["current_referral"] = current
    
    logger.debug(f"{log(user)} Selected accrual strategy: {strategy}")


@inject
async def on_reward_strategy_select(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор формы начисления (радиокнопка)."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Извлекаем стратегию из widget_id (strategy_AMOUNT или strategy_PERCENT)
    strategy = widget.widget_id.split("_", 1)[1]
    
    current = dialog_manager.dialog_data.get("current_referral", {})
    
    # Сохраняем исходное значение перед первым изменением в этом подменю
    _ensure_reward_backup(current)
    
    current["reward_strategy"] = strategy
    current["editing_field"] = "reward_strategy"  # Отслеживаем какое поле редактируется
    # При смене стратегии сбрасываем награды обоих уровней в 0
    current["reward_level_1"] = 0
    current["reward_level_2"] = 0
    dialog_manager.dialog_data["current_referral"] = current
    
    logger.debug(f"{log(user)} Selected reward strategy: {strategy}")


@inject
async def on_level_switch(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Переключение между редактированием первого и второго уровня наград."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Извлекаем уровень из widget_id (level_switch_1 или level_switch_2)
    editing_level = int(widget.widget_id.split("_")[-1])
    
    current = dialog_manager.dialog_data.get("current_referral", {})
    current["editing_level"] = editing_level
    dialog_manager.dialog_data["current_referral"] = current
    
    logger.debug(f"{log(user)} Switched to editing level: {editing_level}")


@inject
async def on_reward_free_select(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Выбор 'Без награды' - устанавливает награду в 0."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    current = dialog_manager.dialog_data.get("current_referral", {})
    
    # Создаем backup перед изменением (только для наград, без стратегии)
    if "submenu_backup_reward_level_1" not in current:
        # Сохраняем текущие значения (или 0 если None)
        current["submenu_backup_reward_level_1"] = current.get("reward_level_1") or 0
        current["submenu_backup_reward_level_2"] = current.get("reward_level_2") or 0
    
    editing_level = current.get("editing_level", 1)
    current[f"reward_level_{editing_level}"] = 0
    current["editing_field"] = "reward"  # Используем 'reward' вместо 'reward_strategy'
    dialog_manager.dialog_data["current_referral"] = current
    
    logger.debug(f"{log(user)} Selected no reward (0) for level {editing_level}")


@inject
async def on_reward_preset_select(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
    i18n: FromDishka[TranslatorRunner],
) -> None:
    """Выбор пресета награды."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    current = dialog_manager.dialog_data.get("current_referral", {})
    
    # DEBUG: Логируем текущие значения перед backup
    logger.debug(f"{log(user)} Before backup: reward_level_1={current.get('reward_level_1')}, reward_level_2={current.get('reward_level_2')}")
    
    # Создаем backup перед любым изменением (только для наград, без стратегии)
    if "submenu_backup_reward_level_1" not in current:
        # Сохраняем текущие значения (или 0 если None)
        current["submenu_backup_reward_level_1"] = current.get("reward_level_1") or 0
        current["submenu_backup_reward_level_2"] = current.get("reward_level_2") or 0
    
    dialog_manager.dialog_data["current_referral"] = current
    
    # Кнопка "Ручной ввод" - переходим в режим ручного ввода
    if widget.widget_id == "manual_input_dummy":
        # Устанавливаем editing_field до перехода
        current["editing_field"] = "reward"
        dialog_manager.dialog_data["current_referral"] = current
        # Используем switch_to чтобы сохранить dialog_data
        await dialog_manager.switch_to(RemnashopReferral.REWARD_MANUAL_INPUT)
        return
    
    # Извлекаем значение из widget_id (reward_10, reward_20, etc.)
    value = int(widget.widget_id.split("_")[1])
    
    editing_level = current.get("editing_level", 1)
    current[f"reward_level_{editing_level}"] = value
    current["editing_field"] = "reward"  # Используем 'reward' вместо 'reward_strategy'
    dialog_manager.dialog_data["current_referral"] = current
    
    logger.debug(f"{log(user)} Selected reward preset: {value} for level {editing_level}")


@inject
async def on_reward_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
    settings_service: FromDishka[SettingsService],
) -> None:
    """Обработка ввода награды вручную."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    text = message.text

    if not text:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-referral-invalid-reward"),
        )
        return

    current = dialog_manager.dialog_data.get("current_referral", {})

    if text.isdigit():
        value = int(text)
        reward_strategy = current.get("reward_strategy", "AMOUNT")
        
        # Валидация
        if reward_strategy == "PERCENT":
            if not (0 <= value <= 100):
                await message.answer("⚠️ Для процентной награды введите число от 0 до 100!")
                return
        else:
            if value < 0:
                await message.answer("⚠️ Введите число больше или равное 0!")
                return
        
        editing_level = current.get("editing_level", 1)
        
        # Создаем backup перед изменением (только для наград, без стратегии)
        if "submenu_backup_reward_level_1" not in current:
            # Сохраняем текущие значения (или 0 если None)
            current["submenu_backup_reward_level_1"] = current.get("reward_level_1") or 0
            current["submenu_backup_reward_level_2"] = current.get("reward_level_2") or 0
        
        current[f"reward_level_{editing_level}"] = value
        current["editing_field"] = "reward"  # Используем 'reward' вместо 'reward_strategy'
        dialog_manager.dialog_data["current_referral"] = current
        
        logger.debug(f"{log(user)} Set reward value: {value} for level {editing_level}")
        try:
            await message.delete()
        except Exception:
            pass
        
        # Возвращаемся в меню выбора награды (используем switch_to для сохранения dialog_data)
        await dialog_manager.switch_to(RemnashopReferral.REWARD)
    else:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-referral-invalid-reward"),
        )


@inject
async def on_reward_manual_input_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена ручного ввода - возврат в меню выбора награды."""
    # Используем switch_to для сохранения dialog_data
    await dialog_manager.switch_to(RemnashopReferral.REWARD)


@inject
async def on_submenu_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Отмена изменений в подменю - восстановление значений из backup и возврат на одно меню назад."""
    settings = await settings_service.get_referral_settings()
    current = dialog_manager.dialog_data.get("current_referral")
    initial = dialog_manager.dialog_data.get("initial_referral", {})
    
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    if current:
        editing_field = current.get("editing_field")
        
        # DEBUG: Логируем что восстанавливаем
        logger.debug(f"{log(user)} Cancel pressed. editing_field={editing_field}")
        logger.debug(f"{log(user)} Current before restore: {current}")
        if editing_field == "reward_strategy":
            logger.debug(f"{log(user)} Backup values: level_1={current.get('submenu_backup_reward_level_1')}, level_2={current.get('submenu_backup_reward_level_2')}")
            logger.debug(f"{log(user)} Initial values: level_1={initial.get('reward_level_1')}, level_2={initial.get('reward_level_2')}")
        
        # Восстанавливаем исходные значения из submenu_backup
        if editing_field == "level" and "submenu_backup_level" in current:
            current["level"] = current.pop("submenu_backup_level")
        elif editing_field == "reward_type" and "submenu_backup_reward_type" in current:
            current["reward_type"] = current.pop("submenu_backup_reward_type")
        elif editing_field == "accrual_strategy" and "submenu_backup_accrual_strategy" in current:
            current["accrual_strategy"] = current.pop("submenu_backup_accrual_strategy")
        elif editing_field == "reward_strategy":
            if "submenu_backup_reward_strategy" in current:
                backup_strategy = current.pop("submenu_backup_reward_strategy")
                current["reward_strategy"] = backup_strategy if backup_strategy is not None else settings.reward.strategy.value
            else:
                # Если нет backup, восстанавливаем из settings
                current["reward_strategy"] = settings.reward.strategy.value
            
            # Восстанавливаем значения наград с защитой от None
            if "submenu_backup_reward_level_1" in current:
                backup_level_1 = current.pop("submenu_backup_reward_level_1")
                # Если backup None, берем из initial или из settings
                if backup_level_1 is None:
                    reward_config = settings.reward.config
                    backup_level_1 = initial.get("reward_level_1", reward_config.get(ReferralLevel.FIRST, 0))
                current["reward_level_1"] = backup_level_1
            
            if "submenu_backup_reward_level_2" in current:
                backup_level_2 = current.pop("submenu_backup_reward_level_2")
                # Если backup None, берем из initial или из settings
                if backup_level_2 is None:
                    reward_config = settings.reward.config
                    backup_level_2 = initial.get("reward_level_2", reward_config.get(ReferralLevel.SECOND, 0))
                current["reward_level_2"] = backup_level_2
            
            # Удаляем флаг backup
            current.pop("has_reward_backup", None)
            
            # DEBUG: Логируем восстановленные значения
            logger.debug(f"{log(user)} Restored values: level_1={current.get('reward_level_1')}, level_2={current.get('reward_level_2')}")
        elif editing_field == "reward":
            # Для меню REWARD восстанавливаем только награды, НЕ стратегию
            if "submenu_backup_reward_level_1" in current:
                backup_level_1 = current.pop("submenu_backup_reward_level_1")
                current["reward_level_1"] = backup_level_1
            
            if "submenu_backup_reward_level_2" in current:
                backup_level_2 = current.pop("submenu_backup_reward_level_2")
                current["reward_level_2"] = backup_level_2
            
            logger.debug(f"{log(user)} Restored reward values: level_1={current.get('reward_level_1')}, level_2={current.get('reward_level_2')}")
        
        logger.debug(f"{log(user)} Current after restore: {current}")
        dialog_manager.dialog_data["current_referral"] = current
    
    # Возврат в главное меню реф.системы
    await dialog_manager.switch_to(RemnashopReferral.MAIN)


@inject
async def on_submenu_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принятие изменений в подменю - удаление backup и возврат на одно меню назад."""
    # Изменения уже применены в current_referral при каждом нажатии кнопки
    # Удаляем backup значения
    current = dialog_manager.dialog_data.get("current_referral")
    if current:
        # Удаляем все backup ключи для текущего поля
        editing_field = current.get("editing_field")
        if editing_field == "level":
            current.pop("submenu_backup_level", None)
        elif editing_field == "reward_type":
            current.pop("submenu_backup_reward_type", None)
        elif editing_field == "accrual_strategy":
            current.pop("submenu_backup_accrual_strategy", None)
        elif editing_field == "reward_strategy":
            current.pop("submenu_backup_reward_strategy", None)
            current.pop("submenu_backup_reward_level_1", None)
            current.pop("submenu_backup_reward_level_2", None)
        elif editing_field == "reward":
            # Для меню REWARD удаляем только backup наград
            current.pop("submenu_backup_reward_level_1", None)
            current.pop("submenu_backup_reward_level_2", None)
        
        # Очищаем editing_field чтобы следующее подменю создало свой backup
        current.pop("editing_field", None)
        dialog_manager.dialog_data["current_referral"] = current
    
    # Возвращаемся в главное меню реф.системы
    await dialog_manager.switch_to(RemnashopReferral.MAIN)


@inject
async def on_referral_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена изменений реферальной системы."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    # Восстанавливаем начальное состояние из initial_referral
    initial = dialog_manager.dialog_data.get("initial_referral")
    if initial:
        dialog_manager.dialog_data["current_referral"] = initial.copy()
    
    # Очищаем временные данные
    dialog_manager.dialog_data.pop("current_referral", None)
    dialog_manager.dialog_data.pop("initial_referral", None)
    
    logger.info(f"{log(user)} Cancelled referral changes")
    
    # Закрываем диалог реферальной системы и возвращаемся к предыдущему меню
    await dialog_manager.done()


@inject
async def on_referral_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Применение изменений реферальной системы."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    current = dialog_manager.dialog_data.get("current_referral", {})
    initial = dialog_manager.dialog_data.get("initial_referral", {})
    
    # Проверяем, есть ли изменения
    if current != initial:
        settings = await settings_service.get()
        
        # Применяем изменения
        if "level" in current:
            new_level = ReferralLevel(current["level"])
            settings.referral.level = new_level
            # Обновляем конфигурацию наград
            config = settings.referral.reward.config
            for lvl in ReferralLevel:
                if lvl.value <= current["level"] and lvl not in config:
                    prev_value = config.get(ReferralLevel(lvl.value - 1), 0)
                    config[lvl] = prev_value
        
        if "reward_type" in current:
            settings.referral.reward.type = ReferralRewardType(current["reward_type"])
        
        if "accrual_strategy" in current:
            settings.referral.accrual_strategy = ReferralAccrualStrategy(current["accrual_strategy"])
        
        if "reward_strategy" in current:
            settings.referral.reward.strategy = ReferralRewardStrategy(current["reward_strategy"])
        
        # Сохраняем награды для обоих уровней
        if "reward_level_1" in current:
            settings.referral.reward.config[ReferralLevel.FIRST] = current["reward_level_1"]
        if "reward_level_2" in current:
            settings.referral.reward.config[ReferralLevel.SECOND] = current["reward_level_2"]
        
        await settings_service.update(settings)
        logger.info(f"{log(user)} Applied referral changes")
    
    # Очищаем временные данные
    dialog_manager.dialog_data.pop("current_referral", None)
    dialog_manager.dialog_data.pop("initial_referral", None)
    
    # Закрываем диалог реферальной системы и возвращаемся к предыдущему меню
    await dialog_manager.done()


# === Invite Message Handlers ===


@inject
async def on_invite_message_input(
    message: Message,
    widget: MessageInput,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Обработка ввода сообщения приглашения."""
    dialog_manager.show_mode = ShowMode.EDIT
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    new_message = message.text.strip() if message.text else ""
    
    if not new_message:
        await message.answer("⚠️ Сообщение не может быть пустым!")
        return
    
    # Автоматически добавляем {space} в начало, если его там нет
    if not new_message.startswith("{space}"):
        new_message = "{space}" + new_message
    
    # Сохраняем новое сообщение
    settings = await settings_service.get()
    settings.referral.invite_message = new_message
    await settings_service.update(settings)
    
    logger.info(f"{log(user)} Updated invite message")
    
    try:
        await message.delete()
    except Exception:
        pass
    
    await dialog_manager.switch_to(RemnashopReferral.INVITE_MESSAGE)


@inject
async def on_invite_message_cancel(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Отмена - возврат в главное меню реферальной программы."""
    await dialog_manager.switch_to(RemnashopReferral.MAIN)


@inject
async def on_invite_message_accept(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Принять изменения - возврат в главное меню реферальной программы."""
    await dialog_manager.switch_to(RemnashopReferral.MAIN)


@inject
async def on_invite_message_reset(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
    settings_service: FromDishka[SettingsService],
) -> None:
    """Сброс сообщения приглашения на значение по умолчанию."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    
    default_message = "{space}Добро пожаловать в защищенный интернет!\n\n➡️ Подключиться: {url}"
    
    settings = await settings_service.get()
    settings.referral.invite_message = default_message
    await settings_service.update(settings)
    
    logger.info(f"{log(user)} Reset invite message to default")


@inject
async def on_invite_preview_close(
    callback: CallbackQuery,
    widget: Button,
    dialog_manager: DialogManager,
) -> None:
    """Закрыть предпросмотр - возврат в настройки приглашения."""
    await dialog_manager.switch_to(RemnashopReferral.INVITE_MESSAGE)
