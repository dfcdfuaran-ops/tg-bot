import uuid
from decimal import Decimal
from typing import Optional
from uuid import UUID

from aiogram import Bot
from fluentogram import TranslatorHub
from loguru import logger
from redis.asyncio import Redis

from src.bot.keyboards import get_user_keyboard
from src.core.config import AppConfig
from src.core.enums import (
    Currency,
    PaymentGatewayType,
    PurchaseType,
    SystemNotificationType,
    TransactionStatus,
)
from src.core.utils.formatters import (
    i18n_format_days,
    i18n_format_device_limit,
    i18n_format_traffic_limit,
    i18n_format_expire_time,
    i18n_format_bytes_to_unit,
)
from src.core.utils.message_payload import MessagePayload
from src.infrastructure.database import UnitOfWork
from src.infrastructure.database.models.dto import (
    AnyGatewaySettingsDto,
    CryptomusGatewaySettingsDto,
    CryptopayGatewaySettingsDto,
    HeleketGatewaySettingsDto,
    PaymentGatewayDto,
    PaymentResult,
    PlanSnapshotDto,
    PriceDetailsDto,
    RobokassaGatewaySettingsDto,
    TransactionDto,
    UserDto,
    YookassaGatewaySettingsDto,
    YoomoneyGatewaySettingsDto,
)
from src.infrastructure.database.models.sql import PaymentGateway
from src.infrastructure.payment_gateways import BasePaymentGateway, PaymentGatewayFactory
from src.infrastructure.redis import RedisRepository
from src.infrastructure.taskiq.tasks.redirects import (
    redirect_to_main_menu_task,
    send_balance_topup_notification_task,
)
from src.infrastructure.taskiq.tasks.subscriptions import purchase_subscription_task
from src.services.notification import NotificationService
from src.services.referral import ReferralService
from src.services.settings import SettingsService
from src.services.subscription import SubscriptionService
from src.services.user import UserService

from remnapy import RemnawaveSDK

from .base import BaseService
from .transaction import TransactionService


class PaymentGatewayService(BaseService):
    uow: UnitOfWork
    transaction_service: TransactionService
    subscription_service: SubscriptionService
    payment_gateway_factory: PaymentGatewayFactory
    referral_service: ReferralService
    user_service: UserService
    settings_service: SettingsService
    remnawave: RemnawaveSDK

    def __init__(
        self,
        config: AppConfig,
        bot: Bot,
        redis_client: Redis,
        redis_repository: RedisRepository,
        translator_hub: TranslatorHub,
        #
        uow: UnitOfWork,
        transaction_service: TransactionService,
        subscription_service: SubscriptionService,
        payment_gateway_factory: PaymentGatewayFactory,
        referral_service: ReferralService,
        user_service: UserService,
        notification_service: NotificationService,
        settings_service: SettingsService,
        remnawave: RemnawaveSDK,
    ) -> None:
        super().__init__(config, bot, redis_client, redis_repository, translator_hub)
        self.uow = uow
        self.transaction_service = transaction_service
        self.subscription_service = subscription_service
        self.payment_gateway_factory = payment_gateway_factory
        self.referral_service = referral_service
        self.user_service = user_service
        self.notification_service = notification_service
        self.settings_service = settings_service
        self.remnawave = remnawave

    async def create_default(self) -> None:
        for gateway_type in PaymentGatewayType:
            settings: Optional[AnyGatewaySettingsDto]

            if await self.get_by_type(gateway_type):
                continue

            match gateway_type:
                case PaymentGatewayType.TELEGRAM_STARS:
                    is_active = True
                    settings = None
                case PaymentGatewayType.YOOKASSA:
                    is_active = False
                    settings = YookassaGatewaySettingsDto()
                case PaymentGatewayType.YOOMONEY:
                    is_active = False
                    settings = YoomoneyGatewaySettingsDto()
                case PaymentGatewayType.CRYPTOMUS:
                    is_active = False
                    settings = CryptomusGatewaySettingsDto()
                case PaymentGatewayType.HELEKET:
                    is_active = False
                    settings = HeleketGatewaySettingsDto()
                # case PaymentGatewayType.CRYPTOPAY:
                #     is_active = False
                #     settings = CryptopayGatewaySettingsDto()
                # case PaymentGatewayType.ROBOKASSA:
                #     is_active = False
                #     settings = RobokassaGatewaySettingsDto()
                case _:
                    logger.warning(f"Unhandled payment gateway type '{gateway_type}' - skipping")
                    continue

            order_index = await self.uow.repository.gateways.get_max_index()
            order_index = (order_index or 0) + 1

            payment_gateway = PaymentGatewayDto(
                order_index=order_index,
                type=gateway_type,
                currency=Currency.from_gateway_type(gateway_type),
                is_active=is_active,
                settings=settings,
            )

            db_payment_gateway = PaymentGateway(**payment_gateway.model_dump())
            db_payment_gateway = await self.uow.repository.gateways.create(db_payment_gateway)

            logger.info(f"Payment gateway '{gateway_type}' created")

    async def get(self, gateway_id: int) -> Optional[PaymentGatewayDto]:
        db_gateway = await self.uow.repository.gateways.get(gateway_id)

        if not db_gateway:
            logger.warning(f"Payment gateway '{gateway_id}' not found")
            return None

        logger.debug(f"Retrieved payment gateway '{gateway_id}'")
        return PaymentGatewayDto.from_model(db_gateway, decrypt=True)

    async def get_by_type(self, gateway_type: PaymentGatewayType) -> Optional[PaymentGatewayDto]:
        db_gateway = await self.uow.repository.gateways.get_by_type(gateway_type)

        if not db_gateway:
            logger.warning(f"Payment gateway of type '{gateway_type}' not found")
            return None

        logger.debug(f"Retrieved payment gateway of type '{gateway_type}'")
        return PaymentGatewayDto.from_model(db_gateway, decrypt=True)

    async def get_all(self, sorted: bool = False) -> list[PaymentGatewayDto]:
        db_gateways = await self.uow.repository.gateways.get_all(sorted)
        logger.debug(f"Retrieved '{len(db_gateways)}' payment gateways")
        return PaymentGatewayDto.from_model_list(db_gateways, decrypt=False)

    async def update(self, gateway: PaymentGatewayDto) -> Optional[PaymentGatewayDto]:
        updated_data = gateway.changed_data

        if gateway.settings and gateway.settings.changed_data:
            updated_data["settings"] = gateway.settings.prepare_init_data(encrypt=True)

        db_updated_gateway = await self.uow.repository.gateways.update(
            gateway_id=gateway.id,  # type: ignore[arg-type]
            **updated_data,
        )

        if db_updated_gateway:
            logger.info(f"Payment gateway '{gateway.type}' updated successfully")
        else:
            logger.warning(
                f"Attempted to update gateway '{gateway.type}' (ID: '{gateway.id}'), "
                f"but gateway was not found or update failed"
            )

        return PaymentGatewayDto.from_model(db_updated_gateway, decrypt=True)

    async def filter_active(self, is_active: bool = True) -> list[PaymentGatewayDto]:
        db_gateways = await self.uow.repository.gateways.filter_active(is_active)
        logger.debug(f"Filtered active gateways: '{is_active}', found '{len(db_gateways)}'")
        return PaymentGatewayDto.from_model_list(db_gateways, decrypt=False)

    async def move_gateway_up(self, gateway_id: int) -> bool:
        db_gateways = await self.uow.repository.gateways.get_all()
        db_gateways.sort(key=lambda p: p.order_index)

        index = next((i for i, p in enumerate(db_gateways) if p.id == gateway_id), None)
        if index is None:
            logger.warning(f"Payment gateway with ID '{gateway_id}' not found for move operation")
            return False

        if index == 0:
            gateway = db_gateways.pop(0)
            db_gateways.append(gateway)
            logger.debug(f"Payment gateway '{gateway_id}' moved from top to bottom")
        else:
            db_gateways[index - 1], db_gateways[index] = db_gateways[index], db_gateways[index - 1]
            logger.debug(f"Payment gateway '{gateway_id}' moved up one position")

        for i, gateway in enumerate(db_gateways, start=1):
            gateway.order_index = i

        logger.info(f"Payment gateway '{gateway_id}' reorder successfully")
        return True

    #

    async def create_topup_payment(
        self,
        user: UserDto,
        amount: int,
        gateway_type: PaymentGatewayType,
    ) -> PaymentResult:
        """Create a payment for topping up user balance."""
        # Minimum topup amount is 5 rubles
        MIN_TOPUP_AMOUNT = 5
        if amount < MIN_TOPUP_AMOUNT:
            raise ValueError(f"Minimum topup amount is {MIN_TOPUP_AMOUNT}")
        
        gateway_instance = await self._get_gateway_instance(gateway_type)

        i18n = self.translator_hub.get_translator_by_locale(locale=user.language)
        details = i18n.get("payment-invoice-topup", amount=amount)

        pricing = PriceDetailsDto(original_amount=amount)
        plan = PlanSnapshotDto.test()  # Используем test plan как заглушку

        transaction_data = {
            "status": TransactionStatus.PENDING,
            "purchase_type": PurchaseType.TOPUP,
            "gateway_type": gateway_instance.data.type,
            "pricing": pricing,
            "currency": gateway_instance.data.currency,
            "plan": plan,
            "user": user,
        }

        payment: PaymentResult = await gateway_instance.handle_create_payment(
            amount=pricing.final_amount,
            details=details,
        )
        transaction = TransactionDto(payment_id=payment.id, **transaction_data)
        await self.transaction_service.create(user, transaction)

        logger.info(f"Created topup transaction '{payment.id}' for user '{user.telegram_id}'")
        logger.info(f"Topup payment link: '{payment.url}' for user '{user.telegram_id}'")
        return payment

    async def create_extra_devices_payment(
        self,
        user: UserDto,
        device_count: int,
        amount: Decimal,
        gateway_type: PaymentGatewayType,
        duration_days: int = 30,
    ) -> PaymentResult:
        """Create a payment for buying extra devices."""
        gateway_instance = await self._get_gateway_instance(gateway_type)

        i18n = self.translator_hub.get_translator_by_locale(locale=user.language)
        details = i18n.get("payment-invoice-extra-devices", device_count=device_count)

        pricing = PriceDetailsDto(original_amount=amount)
        plan = PlanSnapshotDto.test()  # Используем test plan как заглушку
        plan.name = f"Дополнительные устройства (x{device_count})"
        plan.duration = duration_days

        transaction_data = {
            "status": TransactionStatus.PENDING,
            "purchase_type": PurchaseType.EXTRA_DEVICES,
            "gateway_type": gateway_instance.data.type,
            "pricing": pricing,
            "currency": gateway_instance.data.currency,
            "plan": plan,
            "user": user,
        }

        payment: PaymentResult = await gateway_instance.handle_create_payment(
            amount=pricing.final_amount,
            details=details,
        )
        transaction = TransactionDto(payment_id=payment.id, **transaction_data)
        await self.transaction_service.create(user, transaction)

        logger.info(f"Created extra devices transaction '{payment.id}' for user '{user.telegram_id}'")
        logger.info(f"Extra devices payment link: '{payment.url}' for user '{user.telegram_id}'")
        return payment

    async def create_payment(
        self,
        user: UserDto,
        plan: PlanSnapshotDto,
        pricing: PriceDetailsDto,
        purchase_type: PurchaseType,
        gateway_type: PaymentGatewayType,
    ) -> PaymentResult:
        gateway_instance = await self._get_gateway_instance(gateway_type)

        i18n = self.translator_hub.get_translator_by_locale(locale=user.language)
        key, kw = i18n_format_days(plan.duration)
        details = i18n.get(
            "payment-invoice-description",
            purchase_type=purchase_type,
            name=plan.name,
            duration=i18n.get(key, **kw),
        )

        transaction_data = {
            "status": TransactionStatus.PENDING,
            "purchase_type": purchase_type,
            "gateway_type": gateway_instance.data.type,
            "pricing": pricing,
            "currency": gateway_instance.data.currency,
            "plan": plan,
            "user": user,
        }

        if pricing.is_free:
            payment_id = uuid.uuid4()

            transaction = TransactionDto(payment_id=payment_id, **transaction_data)
            await self.transaction_service.create(user, transaction)

            logger.info(f"Payment for user '{user.telegram_id}' not created. Pricing is free")
            return PaymentResult(id=payment_id, url=None)

        payment: PaymentResult = await gateway_instance.handle_create_payment(
            amount=pricing.final_amount,
            details=details,
        )
        transaction = TransactionDto(payment_id=payment.id, **transaction_data)
        await self.transaction_service.create(user, transaction)

        logger.info(f"Created transaction '{payment.id}' for user '{user.telegram_id}'")
        logger.info(f"Payment link: '{payment.url}' for user '{user.telegram_id}'")
        return payment

    async def create_balance_payment(
        self,
        user: UserDto,
        plan: PlanSnapshotDto,
        pricing: PriceDetailsDto,
        purchase_type: PurchaseType,
    ) -> PaymentResult:
        """Create a payment using user balance (no external gateway)."""
        payment_id = uuid.uuid4()
        
        # Get default currency for balance payments
        settings = await self.settings_service.get()
        currency = settings.default_currency
        
        transaction_data = {
            "status": TransactionStatus.PENDING,
            "purchase_type": purchase_type,
            "gateway_type": PaymentGatewayType.BALANCE,
            "pricing": pricing,
            "currency": currency,
            "plan": plan,
            "user": user,
        }
        
        transaction = TransactionDto(payment_id=payment_id, **transaction_data)
        await self.transaction_service.create(user, transaction)
        
        logger.info(f"Created balance payment '{payment_id}' for user '{user.telegram_id}'")
        return PaymentResult(id=payment_id, url=None)

    async def create_test_payment(
        self,
        user: UserDto,
        gateway_type: PaymentGatewayType,
    ) -> PaymentResult:
        gateway_instance = await self._get_gateway_instance(gateway_type)
        i18n = self.translator_hub.get_translator_by_locale(locale=user.language)
        test_details = i18n.get("test-payment")

        test_pricing = PriceDetailsDto(original_amount=2)
        test_plan = PlanSnapshotDto.test()

        test_payment: PaymentResult = await gateway_instance.handle_create_payment(
            amount=test_pricing.final_amount,
            details=test_details,
        )
        test_transaction = TransactionDto(
            payment_id=test_payment.id,
            status=TransactionStatus.PENDING,
            purchase_type=PurchaseType.NEW,
            gateway_type=gateway_instance.data.type,
            is_test=True,
            pricing=test_pricing,
            currency=gateway_instance.data.currency,
            plan=test_plan,
            user=user,
        )
        await self.transaction_service.create(user, test_transaction)

        logger.info(f"Created test transaction '{test_payment.id}' for user '{user.telegram_id}'")
        logger.info(
            f"Created test payment '{test_payment.id}' for gateway '{gateway_type}', "
            f"link: '{test_payment.url}'"
        )
        return test_payment

    async def handle_payment_succeeded(self, payment_id: UUID) -> None:
        transaction = await self.transaction_service.get(payment_id)

        if not transaction or not transaction.user:
            logger.critical(f"Transaction or user not found for '{payment_id}'")
            return

        if transaction.is_completed:
            logger.warning(
                f"Transaction '{payment_id}' for user "
                f"'{transaction.user.telegram_id}' already completed"
            )
            return

        transaction.status = TransactionStatus.COMPLETED
        await self.transaction_service.update(transaction)

        logger.info(f"Payment succeeded '{payment_id}' for user '{transaction.user.telegram_id}'")

        if transaction.is_test:
            await self.notification_service.notify_user(
                user=transaction.user,
                payload=MessagePayload(
                    i18n_key="ntf-gateway-test-payment-confirmed",
                ),
            )
            return

        i18n_keys = {
            PurchaseType.NEW: "ntf-event-subscription-new",
            PurchaseType.RENEW: "ntf-event-subscription-renew",
            PurchaseType.CHANGE: "ntf-event-subscription-change",
            PurchaseType.TOPUP: "ntf-event-balance-topup",
            PurchaseType.EXTRA_DEVICES: "ntf-event-extra-devices",
        }
        i18n_key = i18n_keys.get(transaction.purchase_type)
        
        # Для покупки дополнительных устройств
        if transaction.purchase_type == PurchaseType.EXTRA_DEVICES:
            from src.services.extra_device import ExtraDeviceService
            from src.services.subscription import SubscriptionService
            from src.services.remnawave import RemnawaveService
            from src.services.user import UserService
            from src.services.settings import SettingsService
            from src.services.notification import NotificationService
            from src.services.plan import PlanService
            
            # Получаем сервисы из DI
            # Создаем SettingsService (нужен для NotificationService)
            settings_service = SettingsService(
                config=self.config,
                bot=self.bot,
                redis_client=self.redis_client,
                redis_repository=self.redis_repository,
                translator_hub=self.translator_hub,
                uow=self.uow,
            )
            
            # Создаем UserService (нужен для SubscriptionService, RemnawaveService, NotificationService)
            user_service = UserService(
                config=self.config,
                bot=self.bot,
                redis_client=self.redis_client,
                redis_repository=self.redis_repository,
                translator_hub=self.translator_hub,
                uow=self.uow,
            )
            
            # Создаем NotificationService (нужен для RemnawaveService)
            notification_service = NotificationService(
                config=self.config,
                bot=self.bot,
                redis_client=self.redis_client,
                redis_repository=self.redis_repository,
                translator_hub=self.translator_hub,
                user_service=user_service,
                settings_service=settings_service,
            )
            
            extra_device_service = ExtraDeviceService(
                config=self.config,
                bot=self.bot,
                redis_client=self.redis_client,
                redis_repository=self.redis_repository,
                translator_hub=self.translator_hub,
                uow=self.uow,
            )
            subscription_service = SubscriptionService(
                config=self.config,
                bot=self.bot,
                redis_client=self.redis_client,
                redis_repository=self.redis_repository,
                translator_hub=self.translator_hub,
                uow=self.uow,
                user_service=user_service,
            )
            plan_service = PlanService(
                config=self.config,
                bot=self.bot,
                redis_client=self.redis_client,
                redis_repository=self.redis_repository,
                translator_hub=self.translator_hub,
                uow=self.uow,
            )
            remnawave_service = RemnawaveService(
                config=self.config,
                bot=self.bot,
                redis_client=self.redis_client,
                redis_repository=self.redis_repository,
                translator_hub=self.translator_hub,
                remnawave=self.remnawave,
                user_service=user_service,
                subscription_service=subscription_service,
                notification_service=notification_service,
                plan_service=plan_service,
            )
            
            # Получаем количество устройств из имени плана
            device_count = 1
            if "x" in transaction.plan.name:
                try:
                    device_count = int(transaction.plan.name.split("x")[1].split(")")[0])
                except:
                    device_count = 1
            
            # Получаем текущую подписку пользователя
            fresh_user = await self.user_service.get(transaction.user.telegram_id)
            if not fresh_user or not fresh_user.current_subscription:
                logger.error(f"No active subscription for user '{transaction.user.telegram_id}' to add devices")
                return
            
            subscription = fresh_user.current_subscription
            
            # Увеличиваем лимит устройств
            new_extra_devices = (subscription.extra_devices or 0) + device_count
            subscription.extra_devices = new_extra_devices
            subscription.device_limit = (subscription.device_limit or 0) + device_count
            
            # Обновляем в БД
            await subscription_service.update(subscription)
            
            # Создаём запись о покупке дополнительных устройств (срок 30 дней)
            await extra_device_service.create_purchase(
                user=fresh_user,
                subscription=subscription,
                device_count=device_count,
                price=int(transaction.pricing.final_amount),
                duration_days=30,
            )
            
            # Обновляем в RemnaWave
            await remnawave_service.updated_user(
                user=fresh_user,
                uuid=subscription.user_remna_id,
                subscription=subscription,
            )
            
            # Очищаем кеш
            await self.user_service.clear_user_cache(fresh_user.telegram_id)
            
            logger.info(f"Added {device_count} extra devices for user '{transaction.user.telegram_id}'")
            
            # Вычисляем device_limit_number и device_limit_bonus
            plan_device_limit = (
                subscription.plan.device_limit 
                if subscription.plan and subscription.plan.device_limit > 0 
                else 0
            )
            device_limit_number = (
                plan_device_limit 
                if plan_device_limit > 0 
                else subscription.device_limit
            )
            device_limit_bonus = max(
                0, 
                subscription.device_limit - plan_device_limit - subscription.extra_devices
            ) if plan_device_limit > 0 else 0
            
            # Отправляем системное уведомление (Event)
            i18n_kwargs = {
                "payment_id": str(transaction.payment_id),
                "gateway_type": transaction.gateway_type,
                "final_amount": transaction.pricing.final_amount,
                "discount_percent": transaction.pricing.discount_percent,
                "currency": transaction.currency.symbol,
                "user_id": str(transaction.user.telegram_id),
                "user_name": transaction.user.name,
                "username": transaction.user.username or False,
                "device_count": device_count,
                # Параметры для frg-subscription-details
                "subscription_id": str(subscription.user_remna_id),
                "subscription_status": subscription.status,
                "plan_name": subscription.plan.name,
                "traffic_used": i18n_format_bytes_to_unit(0),  # TODO: получить real traffic used
                "traffic_limit": i18n_format_traffic_limit(subscription.traffic_limit),
                "device_limit_number": device_limit_number,
                "device_limit_bonus": device_limit_bonus,
                "extra_devices": subscription.extra_devices,
                "expire_time": i18n_format_expire_time(subscription.expire_at),
            }
            
            await self.notification_service.system_notify(
                ntf_type=SystemNotificationType.EXTRA_DEVICES,
                payload=MessagePayload.not_deleted(
                    i18n_key=i18n_key,
                    i18n_kwargs=i18n_kwargs,
                    reply_markup=get_user_keyboard(transaction.user.telegram_id),
                ),
            )
            
            # Assign referral rewards
            if not transaction.pricing.is_free and transaction.gateway_type != PaymentGatewayType.BALANCE:
                await self.referral_service.assign_referral_rewards(transaction=transaction)
            
            # Перенаправляем на экран успеха добавления устройств
            from src.infrastructure.taskiq.tasks.redirects import redirect_to_extra_devices_success_task
            await redirect_to_extra_devices_success_task.kiq(
                user=fresh_user,
                device_count=device_count,
            )
            
            return
        
        # Для пополнения баланса не создаём подписку, только добавляем деньги
        if transaction.purchase_type == PurchaseType.TOPUP:
            i18n_kwargs = {
                "payment_id": str(transaction.payment_id),
                "gateway_type": transaction.gateway_type,
                "final_amount": transaction.pricing.final_amount,
                "currency": transaction.currency.symbol,
                "user_id": str(transaction.user.telegram_id),
                "user_name": transaction.user.name,
                "username": transaction.user.username or False,
            }
            
            await self.notification_service.system_notify(
                ntf_type=SystemNotificationType.BILLING,
                payload=MessagePayload.not_deleted(
                    i18n_key=i18n_key,
                    i18n_kwargs=i18n_kwargs,
                    reply_markup=get_user_keyboard(transaction.user.telegram_id),
                ),
            )
            
            if not transaction.pricing.is_free:
                await self.user_service.add_to_balance(
                    user=transaction.user,
                    amount=int(transaction.pricing.final_amount),
                )
            
            # Assign referral rewards (only for external payment gateways)
            if not transaction.pricing.is_free and transaction.gateway_type != PaymentGatewayType.BALANCE:
                await self.referral_service.assign_referral_rewards(transaction=transaction)
            
            # Redirect user to main menu
            await redirect_to_main_menu_task.kiq(telegram_id=transaction.user.telegram_id)
            
            # Send success notification with close button (appears below main menu)
            await send_balance_topup_notification_task.kiq(
                telegram_id=transaction.user.telegram_id,
                amount=transaction.pricing.final_amount,
                currency_symbol=transaction.currency.symbol,
            )
            
            logger.debug(f"Balance topped up for user '{transaction.user.telegram_id}'")
            return

        subscription = await self.subscription_service.get_current(transaction.user.telegram_id)
        extra_i18n_kwargs = {}

        if transaction.purchase_type == PurchaseType.CHANGE:
            plan = subscription.plan if subscription else None

            extra_i18n_kwargs = {
                "previous_plan_name": plan.name if plan else "N/A",
                "previous_plan_type": {
                    "key": "plan-type",
                    "plan_type": plan.type if plan else "N/A",
                },
                "previous_plan_traffic_limit": (
                    i18n_format_traffic_limit(plan.traffic_limit) if plan else "N/A"
                ),
                "previous_plan_device_limit": (
                    i18n_format_device_limit(plan.device_limit) if plan else "N/A"
                ),
                "previous_plan_duration": (i18n_format_days(plan.duration) if plan else "N/A"),
            }

        i18n_kwargs = {
            "payment_id": str(transaction.payment_id),
            "gateway_type": transaction.gateway_type,
            "final_amount": transaction.pricing.final_amount,
            "discount_percent": transaction.pricing.discount_percent,
            "original_amount": transaction.pricing.original_amount,
            "currency": transaction.currency.symbol,
            "user_id": str(transaction.user.telegram_id),
            "user_name": transaction.user.name,
            "username": transaction.user.username or False,
            "plan_name": transaction.plan.name,
            "plan_type": transaction.plan.type,
            "plan_traffic_limit": i18n_format_traffic_limit(transaction.plan.traffic_limit),
            "plan_device_limit": i18n_format_device_limit(transaction.plan.device_limit),
            "plan_duration": i18n_format_days(transaction.plan.duration),
        }

        await self.notification_service.system_notify(
            ntf_type=SystemNotificationType.SUBSCRIPTION,
            payload=MessagePayload.not_deleted(
                i18n_key=i18n_key,
                i18n_kwargs={**i18n_kwargs, **extra_i18n_kwargs},
                reply_markup=get_user_keyboard(transaction.user.telegram_id),
            ),
        )

        logger.info(f"Sending purchase_subscription_task for transaction '{transaction.payment_id}', subscription={subscription is not None}")
        await purchase_subscription_task.kiq(transaction, subscription)
        logger.info(f"purchase_subscription_task sent successfully")

        # Сбросить одноразовую скидку после успешной покупки
        if transaction.user.purchase_discount > 0 and transaction.pricing.discount_percent > 0:
            logger.info(
                f"Resetting one-time discount for user '{transaction.user.telegram_id}' "
                f"(was {transaction.user.purchase_discount}%)"
            )
            transaction.user.purchase_discount = 0
            transaction.user.purchase_discount_expires_at = None
            await self.user_service.update(transaction.user)

        # Для оплаты с баланса не добавляем деньги обратно и не начисляем реф. бонусы
        # (деньги уже были списаны при подтверждении)
        if not transaction.pricing.is_free and transaction.gateway_type != PaymentGatewayType.BALANCE:
            # Пополнить баланс пользователя суммой оплаты (для внешних шлюзов)
            await self.user_service.add_to_balance(
                user=transaction.user,
                amount=int(transaction.pricing.final_amount),
            )
            # Назначить реферальные бонусы
            await self.referral_service.assign_referral_rewards(transaction=transaction)

        logger.debug(f"Called tasks payment for user '{transaction.user.telegram_id}'")

    async def handle_payment_canceled(self, payment_id: UUID) -> None:
        transaction = await self.transaction_service.get(payment_id)

        if not transaction or not transaction.user:
            logger.critical(f"Transaction or user not found for '{payment_id}'")
            return

        transaction.status = TransactionStatus.CANCELED
        await self.transaction_service.update(transaction)
        logger.info(f"Payment canceled '{payment_id}' for user '{transaction.user.telegram_id}'")

    #

    async def _get_gateway_instance(self, gateway_type: PaymentGatewayType) -> BasePaymentGateway:
        logger.debug(f"Creating gateway instance for type '{gateway_type}'")
        gateway = await self.get_by_type(gateway_type)

        if not gateway:
            raise ValueError(f"Payment gateway of type '{gateway_type}' not found")

        return self.payment_gateway_factory(gateway)
