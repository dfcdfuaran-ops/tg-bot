import asyncio
import traceback
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from aiogram import Bot, Dispatcher
from aiogram.types import WebhookInfo, User as AiogramUser, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.formatting import Text
from dishka import AsyncContainer, Scope
from fastapi import FastAPI
from fluentogram import TranslatorHub
from loguru import logger
from redis.asyncio import from_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from src.__version__ import __version__
from src.api.endpoints import TelegramWebhookEndpoint
from src.core.config.app import AppConfig
from src.core.enums import SystemNotificationType, UserRole
from src.core.storage.keys import ShutdownMessagesKey
from src.core.utils.message_payload import MessagePayload
from src.infrastructure.database import UnitOfWork
from src.infrastructure.redis.repository import RedisRepository
from src.services.command import CommandService
from src.services.notification import NotificationService
from src.services.payment_gateway import PaymentGatewayService
from src.services.remnawave import RemnawaveService
from src.services.settings import SettingsService
from src.services.user import UserService
from src.services.webhook import WebhookService


async def ensure_dev_user_exists(
    config: AppConfig,
    bot: Bot,
    max_retries: int = 5,
    retry_delay: float = 2.0,
) -> bool:
    """
    Create DEV user if not exists using a separate database connection.
    Uses retry logic to handle transient database issues during startup.
    Returns True if user exists or was created, False otherwise.
    """
    dev_telegram_id = config.bot.dev_id
    
    for attempt in range(1, max_retries + 1):
        engine = None
        try:
            # Create a separate lightweight connection for this operation
            engine = create_async_engine(
                url=config.database.dsn,
                pool_size=1,
                max_overflow=0,
                pool_timeout=5,
                pool_pre_ping=True,
                connect_args={
                    "timeout": 10,
                    "command_timeout": 15,
                },
            )
            
            async_session = async_sessionmaker(bind=engine, expire_on_commit=False)
            
            async with UnitOfWork(async_session) as uow:
                # Check if DEV user exists
                existing_user = await uow.repository.users.get(dev_telegram_id)
                
                if existing_user:
                    logger.debug(f"DEV user {dev_telegram_id} already exists")
                    return True
                
                # Get Telegram user info
                try:
                    dev_chat = await bot.get_chat(dev_telegram_id)
                except Exception as e:
                    logger.warning(f"Failed to get Telegram info for DEV user {dev_telegram_id}: {e}")
                    return False
                
                # Create AiogramUser object
                aiogram_user = AiogramUser(
                    id=dev_telegram_id,
                    is_bot=False,
                    first_name=dev_chat.first_name or "DEV",
                    last_name=dev_chat.last_name,
                    username=dev_chat.username,
                    language_code=config.default_locale.value,
                )
                
                # Create user using service logic
                from src.core.utils.generators import generate_referral_code
                from src.infrastructure.database.models.sql import User
                from src.infrastructure.database.models.dto import UserDto
                
                user_dto = UserDto(
                    telegram_id=aiogram_user.id,
                    username=aiogram_user.username,
                    referral_code=generate_referral_code(
                        aiogram_user.id,
                        secret=config.crypt_key.get_secret_value(),
                    ),
                    name=aiogram_user.full_name,
                    role=UserRole.DEV,
                    language=config.default_locale,
                )
                
                db_user = User(**user_dto.model_dump())
                await uow.repository.users.create(db_user)
                await uow.commit()
                
                logger.success(f"DEV user {dev_telegram_id} created automatically on first startup")
                return True
                
        except Exception as e:
            logger.warning(f"Attempt {attempt}/{max_retries} to create DEV user failed: {e}")
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * attempt)  # Exponential backoff
        finally:
            if engine:
                await engine.dispose()
    
    logger.error(f"Failed to create DEV user after {max_retries} attempts")
    return False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    dispatcher: Dispatcher = app.state.dispatcher
    telegram_webhook_endpoint: TelegramWebhookEndpoint = app.state.telegram_webhook_endpoint
    container: AsyncContainer = app.state.dishka_container

    async with container(scope=Scope.REQUEST) as startup_container:
        config: AppConfig = await startup_container.get(AppConfig)
        webhook_service: WebhookService = await startup_container.get(WebhookService)
        command_service: CommandService = await startup_container.get(CommandService)
        settings_service: SettingsService = await startup_container.get(SettingsService)
        gateway_service: PaymentGatewayService = await startup_container.get(PaymentGatewayService)
        remnawave_service: RemnawaveService = await startup_container.get(RemnawaveService)
        notification_service: NotificationService = await startup_container.get(NotificationService)
        redis_repository: RedisRepository = await startup_container.get(RedisRepository)
        user_service: UserService = await startup_container.get(UserService)
        bot: Bot = await startup_container.get(Bot)

        await gateway_service.create_default()
        settings = await settings_service.get()
        
        # Delete previous shutdown messages
        try:
            shutdown_key = ShutdownMessagesKey()
            shutdown_messages = await redis_repository.list_range(shutdown_key, 0, -1)
            for msg_data in shutdown_messages:
                try:
                    chat_id, message_id = msg_data.split(":")
                    await bot.delete_message(chat_id=int(chat_id), message_id=int(message_id))
                    logger.debug(f"Deleted shutdown message {message_id} in chat {chat_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete shutdown message: {e}")
            await redis_repository.delete(shutdown_key)
        except Exception as e:
            logger.warning(f"Failed to cleanup shutdown messages: {e}")
        
        # Initialize Redis consumer group for taskiq
        try:
            redis = await from_url(config.redis.dsn)
            await redis.xgroup_create(name="taskiq", groupname="taskiq", id="0", mkstream=True)
            await redis.close()
        except Exception as exc:
            # Consumer group might already exist, which is fine
            if "BUSYGROUP" not in str(exc):
                logger.warning(f"Failed to initialize consumer group: {exc}")

    await startup_container.close()

    allowed_updates = dispatcher.resolve_used_update_types()
    webhook_info: WebhookInfo = await webhook_service.setup(allowed_updates)

    if webhook_service.has_error(webhook_info):
        logger.critical(f"Webhook has a last error message: '{webhook_info.last_error_message}'")
        await notification_service.system_notify(
            ntf_type=SystemNotificationType.BOT_LIFETIME,
            payload=MessagePayload.not_deleted(
                i18n_key="ntf-event-error-webhook",
                i18n_kwargs={"error": webhook_info.last_error_message},
            ),
        )

    await command_service.setup()
    await telegram_webhook_endpoint.startup()

    bot: Bot = await container.get(Bot)
    bot_info = await bot.get_me()
    states: dict[Optional[bool], str] = {True: "Enabled", False: "Disabled", None: "Unknown"}

    logger.opt(colors=True).info(
        rf"""
        
    <cyan>██████╗   ███████╗  ██████╗</>
    <cyan>██╔══██╗  ██╔════╝ ██╔════╝</>
    <cyan>██║  ██║  █████╗   ██║     </>
    <cyan>██║  ██║  ██╔══╝   ██║     </>
    <cyan>██████╔╝  ██║      ╚██████╗</>
    <cyan>╚═════╝   ╚═╝       ╚═════╝</>
    <cyan> Digital  Freedom   Core</>

        <green>Version: {__version__}</>
        <cyan>------------------------</>
        Groups Mode  - {states[bot_info.can_join_groups]}
        Privacy Mode - {states[not bot_info.can_read_all_group_messages]}
        Inline Mode  - {states[bot_info.supports_inline_queries]}
        <cyan>------------------------</>
        <yellow>Bot in access mode: '{settings.access_mode}'</>
        <yellow>Purchases allowed: '{settings.purchases_allowed}'</>
        <yellow>Registration allowed: '{settings.registration_allowed}'</>
        """  # noqa: W605
    )
    await asyncio.sleep(2)
    
    # Send startup notification with countdown timer
    try:
        from src.core.i18n.translator import get_translated_kwargs
        from src.core.utils.formatters import i18n_postprocess_text
        from fluentogram import TranslatorHub
        from src.bot.states import Notification
        
        translator_hub: TranslatorHub = await container.get(TranslatorHub)
        
        # Ensure DEV user exists (creates if not)
        # dev_user_created = await ensure_dev_user_exists(config, bot)
        
        # Clear user cache if we just created DEV user
        # if dev_user_created:
        #     try:
        #         await redis_repository.delete_pattern("cache:get_by_role:*")
        #         await redis_repository.delete_pattern("cache:get_user:*")
        #     except Exception as e:
        #         logger.debug(f"Failed to clear cache after DEV user creation: {e}")
        
        # Fetch DEV users (should include newly created user)
        devs = await user_service.get_by_role(role=UserRole.DEV)
        settings_check = await settings_service.is_notification_enabled(SystemNotificationType.BOT_LIFETIME)
        
        if not devs:
            logger.warning(f"DEV user creation failed. Please send /start to the bot from Telegram ID: {config.bot.dev_id}")
        
        logger.debug(f"Startup notification check: devs={len(devs) if devs else 0}, settings_check={settings_check}")
        
        if devs and settings_check:
            # Send messages with close button
            for dev in devs:
                try:
                    i18n = translator_hub.get_translator_by_locale(locale=dev.language)
                    kwargs = get_translated_kwargs(i18n, {
                        "access_mode": settings.access_mode,
                        "purchases_allowed": settings.purchases_allowed,
                        "registration_allowed": settings.registration_allowed,
                    })
                    text = i18n_postprocess_text(i18n.get("ntf-event-bot-startup", **kwargs))
                    close_btn_text = i18n.get("btn-notification-close")
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text=close_btn_text, callback_data=Notification.CLOSE.state)]
                    ])
                    msg = await bot.send_message(
                        chat_id=dev.telegram_id,
                        text=text,
                        reply_markup=keyboard,
                    )
                    logger.debug(f"Sent startup notification to {dev.telegram_id}")
                except Exception as e:
                    logger.warning(f"Failed to send startup notification to {dev.telegram_id}: {e}")
    except Exception as e:
        logger.warning(f"Failed to send startup notification: {e}")

    try:
        await remnawave_service.try_connection()
    except Exception as exception:
        logger.exception(f"Remnawave connection failed: {exception}")
        error_type_name = type(exception).__name__
        error_message = Text(str(exception)[:512])

        await notification_service.error_notify(
            traceback_str=traceback.format_exc(),
            payload=MessagePayload.not_deleted(
                i18n_key="ntf-event-error-remnawave",
                i18n_kwargs={
                    "error": f"{error_type_name}: {error_message.as_html()}",
                },
            ),
        )

    yield

    # Send shutdown notification and save message IDs for deletion on next startup
    async with container(scope=Scope.REQUEST) as shutdown_container:
        notification_service: NotificationService = await shutdown_container.get(NotificationService)
        redis_repository: RedisRepository = await shutdown_container.get(RedisRepository)
        user_service: UserService = await shutdown_container.get(UserService)
        
        devs = await user_service.get_by_role(role=UserRole.DEV)
        
        shutdown_key = ShutdownMessagesKey()
        
        for dev in devs:
            try:
                # Send shutdown message without auto-delete (bot will stop before it can delete)
                msg = await notification_service.notify_user(
                    user=dev,
                    payload=MessagePayload.not_deleted(
                        i18n_key="ntf-event-bot-shutdown",
                        add_close_button=False,
                    ),
                )
                if msg:
                    # Save message ID to Redis for deletion on next startup
                    await redis_repository.list_push(shutdown_key, f"{dev.telegram_id}:{msg.message_id}")
                    logger.debug(f"Saved shutdown message {msg.message_id} for chat {dev.telegram_id}")
            except Exception as e:
                logger.warning(f"Failed to send shutdown notification to {dev.telegram_id}: {e}")
        
        # Set TTL for shutdown messages (24 hours) in case bot doesn't restart
        await redis_repository.expire(shutdown_key, 86400)

    await telegram_webhook_endpoint.shutdown()
    await command_service.delete()
    await webhook_service.delete()

    await container.close()
