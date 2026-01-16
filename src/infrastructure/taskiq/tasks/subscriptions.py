import traceback
from datetime import timedelta
from typing import Optional, cast

from aiogram.utils.formatting import Text
from dishka.integrations.taskiq import FromDishka, inject
from loguru import logger
from remnapy.exceptions import ServerError, NotFoundError

from src.bot.keyboards import get_user_keyboard
from src.core.enums import (
    PurchaseType,
    SubscriptionStatus,
    SystemNotificationType,
    TransactionStatus,
)
from src.core.utils.formatters import (
    i18n_format_days,
    i18n_format_device_limit,
    i18n_format_traffic_limit,
    format_bytes_to_gb,
)
from src.core.utils.message_payload import MessagePayload
from src.core.utils.time import datetime_now
from src.core.utils.types import RemnaUserDto
from src.infrastructure.database.models.dto import (
    PlanSnapshotDto,
    SubscriptionDto,
    TransactionDto,
    UserDto,
)
from src.infrastructure.taskiq.broker import broker
from src.services.extra_device import ExtraDeviceService
from src.services.notification import NotificationService
from src.services.plan import PlanService
from src.services.remnawave import RemnawaveService
from src.services.subscription import SubscriptionService
from src.services.transaction import TransactionService
from src.services.user import UserService

from .redirects import (
    redirect_to_failed_subscription_task,
    redirect_to_successed_payment_task,
    redirect_to_successed_trial_task,
)


@broker.task(retry_on_error=True)
@inject
async def trial_subscription_task(
    user: UserDto,
    plan: PlanSnapshotDto,
    remnawave_service: FromDishka[RemnawaveService],
    subscription_service: FromDishka[SubscriptionService],
    notification_service: FromDishka[NotificationService],
    plan_service: FromDishka[PlanService],
) -> None:
    logger.info(f"Started trial for user '{user.telegram_id}'")

    try:
        # Проверяем, существует ли пользователь в Remnawave
        existing_user = None
        try:
            result = await remnawave_service.remnawave.users.get_users_by_telegram_id(
                telegram_id=str(user.telegram_id)
            )
            if result:
                existing_user = result[0]
                logger.info(
                    f"Found existing user in Remnawave: uuid={existing_user.uuid}, "
                    f"tag={existing_user.tag}, status={existing_user.status}"
                )
        except NotFoundError:
            logger.debug(f"No existing user found in Remnawave for telegram_id={user.telegram_id}")
        except Exception as e:
            logger.warning(f"Error checking existing user in Remnawave: {e}")
        
        # Если пользователь уже существует в Remnawave
        if existing_user and existing_user.status in [SubscriptionStatus.ACTIVE, "ACTIVE"]:
            existing_tag = existing_user.tag or "IMPORT"
            logger.info(f"User has existing active subscription with tag '{existing_tag}'")
            
            # Пытаемся найти план по тегу
            matching_plan = await plan_service.get_by_tag(existing_tag)
            
            if matching_plan:
                # План найден - создаем подписку на основе существующего пользователя
                logger.info(f"Found matching plan '{matching_plan.name}' for tag '{existing_tag}'")
                
                # Создаём snapshot плана
                plan_snapshot = PlanSnapshotDto(
                    id=matching_plan.id,
                    name=matching_plan.name,
                    tag=matching_plan.tag,
                    type=matching_plan.type,
                    traffic_limit=matching_plan.traffic_limit,
                    device_limit=matching_plan.device_limit,
                    duration=matching_plan.duration,
                    traffic_limit_strategy=matching_plan.traffic_limit_strategy,
                    internal_squads=matching_plan.internal_squads,
                    external_squad=matching_plan.external_squad,
                )
                
                # Создаём подписку на основе существующего пользователя в Remnawave
                imported_subscription = SubscriptionDto(
                    user_remna_id=existing_user.uuid,
                    status=existing_user.status,
                    is_trial=False,  # Это не пробная, а импортированная подписка
                    traffic_limit=format_bytes_to_gb(existing_user.traffic_limit_bytes) if existing_user.traffic_limit_bytes else matching_plan.traffic_limit,
                    device_limit=existing_user.hwid_device_limit or matching_plan.device_limit,
                    traffic_limit_strategy=existing_user.traffic_limit_strategy or matching_plan.traffic_limit_strategy,
                    tag=existing_tag,
                    internal_squads=matching_plan.internal_squads,
                    external_squad=matching_plan.external_squad,
                    expire_at=existing_user.expire_at,
                    url=existing_user.subscription_url,
                    plan=plan_snapshot,
                )
                
                await subscription_service.create(user, imported_subscription)
                logger.info(f"Imported existing subscription for user '{user.telegram_id}' with plan '{matching_plan.name}'")
                
                # Уведомляем пользователя
                await notification_service.notify_user(
                    user=user,
                    payload=MessagePayload(
                        i18n_key="ntf-existing-subscription-found",
                        i18n_kwargs={
                            "plan_name": matching_plan.name,
                            "tag": existing_tag,
                        },
                    ),
                )
                
                await redirect_to_successed_trial_task.kiq(user)
                logger.info(f"Imported subscription task completed for user '{user.telegram_id}'")
                return
                
            else:
                # План не найден - меняем тег на IMPORT
                logger.warning(f"No matching plan found for tag '{existing_tag}', changing to IMPORT")
                
                try:
                    from remnapy.models import UpdateUserRequestDto
                    await remnawave_service.remnawave.users.update_user(
                        UpdateUserRequestDto(
                            uuid=existing_user.uuid,
                            tag="IMPORT",
                        )
                    )
                    logger.info(f"Changed tag from '{existing_tag}' to 'IMPORT' for user '{user.telegram_id}'")
                except Exception as e:
                    logger.error(f"Failed to update tag to IMPORT: {e}")
                
                # Создаём базовую подписку без плана
                # Используем данные из существующего пользователя
                imported_subscription = SubscriptionDto(
                    user_remna_id=existing_user.uuid,
                    status=existing_user.status,
                    is_trial=False,
                    traffic_limit=format_bytes_to_gb(existing_user.traffic_limit_bytes) if existing_user.traffic_limit_bytes else 0,
                    device_limit=existing_user.hwid_device_limit or 1,
                    traffic_limit_strategy=existing_user.traffic_limit_strategy,
                    tag="IMPORT",
                    internal_squads=[],
                    external_squad=None,
                    expire_at=existing_user.expire_at,
                    url=existing_user.subscription_url,
                    plan=None,
                )
                
                await subscription_service.create(user, imported_subscription)
                
                # Уведомляем пользователя
                await notification_service.notify_user(
                    user=user,
                    payload=MessagePayload(
                        i18n_key="ntf-existing-subscription-no-plan",
                        i18n_kwargs={
                            "old_tag": existing_tag,
                        },
                    ),
                )
                
                await redirect_to_successed_trial_task.kiq(user)
                logger.info(f"Imported subscription (no plan) task completed for user '{user.telegram_id}'")
                return

        # Если пользователя нет в Remnawave или подписка неактивна - создаём пробную
        # force=True позволяет обновить существующего пользователя в Remnawave
        # если он уже есть (например, старая подписка через панель)
        created_user = await remnawave_service.create_user(user, plan=plan, force=True)
        trial_subscription = SubscriptionDto(
            user_remna_id=created_user.uuid,
            status=created_user.status,
            is_trial=True,
            traffic_limit=plan.traffic_limit,
            device_limit=plan.device_limit,
            traffic_limit_strategy=plan.traffic_limit_strategy,
            tag=plan.tag,
            internal_squads=plan.internal_squads,
            external_squad=plan.external_squad,
            expire_at=created_user.expire_at,
            url=created_user.subscription_url,
            plan=plan,
        )
        await subscription_service.create(user, trial_subscription)
        logger.debug(f"Created new trial subscription for user '{user.telegram_id}'")

        await notification_service.system_notify(
            ntf_type=SystemNotificationType.TRIAL_GETTED,
            payload=MessagePayload.not_deleted(
                i18n_key="ntf-event-subscription-trial",
                i18n_kwargs={
                    "user_id": str(user.telegram_id),
                    "user_name": user.name,
                    "username": user.username or False,
                    "plan_name": plan.name,
                    "plan_type": plan.type,
                    "plan_traffic_limit": i18n_format_traffic_limit(plan.traffic_limit),
                    "plan_device_limit": i18n_format_device_limit(plan.device_limit),
                    "plan_duration": i18n_format_days(plan.duration),
                },
                reply_markup=get_user_keyboard(user.telegram_id),
            ),
        )
        await redirect_to_successed_trial_task.kiq(user)
        logger.info(f"Trial subscription task completed successfully for user '{user.telegram_id}'")

    except ServerError as server_error:
        logger.error(
            f"Remnawave server error when creating trial for user '{user.telegram_id}': "
            f"{server_error}. This may indicate a problem with the Remnawave API or invalid plan data."
        )
        # Re-raise to be handled by general exception handler
        raise

    except Exception as exception:
        logger.exception(
            f"Failed to give trial for user '{user.telegram_id}' exception: {exception}"
        )
        traceback_str = traceback.format_exc()
        error_type_name = type(exception).__name__
        error_message = Text(str(exception)[:512])

        await notification_service.error_notify(
            error_id=user.telegram_id,
            traceback_str=traceback_str,
            payload=MessagePayload.not_deleted(
                i18n_key="ntf-event-error",
                i18n_kwargs={
                    "user": True,
                    "user_id": str(user.telegram_id),
                    "user_name": user.name,
                    "username": user.username or False,
                    "error": f"{error_type_name}: {error_message.as_html()}",
                },
                reply_markup=get_user_keyboard(user.telegram_id),
            ),
        )

        await redirect_to_failed_subscription_task.kiq(user)


@broker.task(retry_on_error=True)
@inject
async def purchase_subscription_task(
    transaction: TransactionDto,
    subscription: Optional[SubscriptionDto],
    remnawave_service: FromDishka[RemnawaveService],
    subscription_service: FromDishka[SubscriptionService],
    transaction_service: FromDishka[TransactionService],
    notification_service: FromDishka[NotificationService],
    user_service: FromDishka[UserService],
) -> None:
    """
    Обрабатывает покупку подписки.
    
    Логика:
    - NEW без подписки: создаём пользователя в Remnawave
    - NEW с любой подпиской (trial/referral/обычная): ОБНОВЛЯЕМ пользователя, добавляем оставшееся время если trial
    - RENEW: продлеваем существующую подписку
    - CHANGE: меняем план (без добавления trial времени)
    """
    logger.info(f"[purchase_subscription_task] Started: transaction={transaction.payment_id}")
    
    purchase_type = transaction.purchase_type
    user = cast(UserDto, transaction.user)
    plan = transaction.plan

    if not user:
        logger.error(f"User not found for transaction '{transaction.id}'")
        return

    # Определяем, есть ли пробная/реферальная подписка (по флагу ИЛИ по названию)
    def is_trial_or_referral(sub: Optional[SubscriptionDto]) -> bool:
        if not sub:
            return False
        if sub.is_trial:
            return True
        if sub.plan and sub.plan.name:
            name_lower = sub.plan.name.lower()
            return "пробн" in name_lower or "реферал" in name_lower
        return False

    has_trial = is_trial_or_referral(subscription)
    has_any_subscription = subscription is not None
    
    logger.info(
        f"[purchase_subscription_task] user={user.telegram_id}, "
        f"purchase_type={purchase_type}, has_trial={has_trial}, has_any_subscription={has_any_subscription}, "
        f"subscription_id={subscription.id if subscription else None}, "
        f"subscription_is_trial={subscription.is_trial if subscription else None}, "
        f"current_plan={subscription.plan.name if subscription and subscription.plan else None}"
    )

    try:
        # ========== NEW без подписки: создаём нового пользователя ==========
        if purchase_type == PurchaseType.NEW and not has_any_subscription:
            logger.info(f"[NEW] Creating new user in Remnawave for '{user.telegram_id}'")
            
            created_user = await remnawave_service.create_user(user, plan=plan, force=True)
            
            new_subscription = SubscriptionDto(
                user_remna_id=created_user.uuid,
                status=SubscriptionStatus.ACTIVE,
                traffic_limit=plan.traffic_limit,
                device_limit=plan.device_limit,
                extra_devices=0,  # Новый пользователь без дополнительных устройств
                traffic_limit_strategy=plan.traffic_limit_strategy,
                tag=plan.tag,
                internal_squads=plan.internal_squads,
                external_squad=plan.external_squad,
                expire_at=created_user.expire_at,
                url=created_user.subscription_url,
                plan=plan,
            )
            await subscription_service.create(user, new_subscription)
            logger.info(f"[NEW] Created subscription for '{user.telegram_id}', expire_at={created_user.expire_at}")

        # ========== NEW с любой подпиской или CHANGE: ОБНОВЛЯЕМ существующего пользователя ==========
        elif (purchase_type == PurchaseType.NEW and has_any_subscription) or purchase_type == PurchaseType.CHANGE:
            if not subscription:
                raise ValueError(f"No subscription found for user '{user.telegram_id}'")

            # Базовое время: сейчас + длительность нового плана
            current_time = datetime_now()
            new_expire = current_time + timedelta(days=plan.duration)
            logger.info(
                f"[UPDATE] Base calculation: now={current_time}, plan_duration={plan.duration}d, "
                f"base_expire={new_expire}"
            )
            
            # Если есть trial/referral - добавляем оставшееся время
            if has_trial:
                logger.info(
                    f"[UPDATE] Trial detected: is_trial={subscription.is_trial}, "
                    f"plan_name='{subscription.plan.name if subscription.plan else None}', "
                    f"subscription.expire_at={subscription.expire_at}, current_time={current_time}"
                )
                if subscription.expire_at > current_time:
                    remaining_time = subscription.expire_at - current_time
                    old_expire = new_expire
                    new_expire = new_expire + remaining_time
                    logger.info(
                        f"[NEW+TRIAL] Adding remaining trial time: {remaining_time.days}d {remaining_time.seconds//3600}h, "
                        f"old_expire={old_expire} -> new_expire={new_expire}"
                    )
                else:
                    logger.info(
                        f"[UPDATE] Trial expired, not adding time: expire_at={subscription.expire_at} <= current={current_time}"
                    )
            else:
                logger.info(f"[UPDATE] No trial/referral subscription, using base expire: {new_expire}")

            logger.info(f"[UPDATE] Updating user in Remnawave: uuid={subscription.user_remna_id}, expire={new_expire}")
            
            # Сохраняем текущие дополнительные устройства
            current_extra_devices = subscription.extra_devices or 0
            # Рассчитываем общий лимит устройств (базовый из плана + дополнительные)
            total_device_limit = plan.device_limit + current_extra_devices
            
            logger.info(
                f"[UPDATE] Device limits: plan={plan.device_limit}, extra={current_extra_devices}, "
                f"total={total_device_limit}"
            )
            
            # ОБНОВЛЯЕМ пользователя в Remnawave (НЕ удаляем!)
            updated_user = await remnawave_service.updated_user(
                user=user,
                uuid=subscription.user_remna_id,
                subscription=SubscriptionDto(
                    user_remna_id=subscription.user_remna_id,
                    status=SubscriptionStatus.ACTIVE,
                    traffic_limit=plan.traffic_limit,
                    device_limit=total_device_limit,  # Используем общий лимит
                    extra_devices=current_extra_devices,  # Сохраняем extra_devices
                    traffic_limit_strategy=plan.traffic_limit_strategy,
                    tag=plan.tag,
                    internal_squads=plan.internal_squads,
                    external_squad=plan.external_squad,
                    expire_at=new_expire,
                    url=subscription.url,
                    plan=plan,
                ),
                reset_traffic=True,
            )
            
            # Обновляем локальную подписку (НЕ удаляем и создаём новую!)
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.traffic_limit = plan.traffic_limit
            subscription.device_limit = total_device_limit  # Сохраняем общий лимит
            subscription.extra_devices = current_extra_devices  # ВАЖНО: сохраняем extra_devices
            subscription.traffic_limit_strategy = plan.traffic_limit_strategy
            subscription.tag = plan.tag
            subscription.internal_squads = plan.internal_squads
            subscription.external_squad = plan.external_squad
            subscription.expire_at = new_expire
            subscription.url = updated_user.subscription_url
            subscription.plan = plan
            subscription.is_trial = False  # Больше не trial
            
            await subscription_service.update(subscription)
            
            action = "NEW+TRIAL" if has_trial else "CHANGE"
            logger.info(f"[{action}] Updated subscription for '{user.telegram_id}', expire_at={new_expire}")

        # ========== RENEW: продлеваем подписку ==========
        elif purchase_type == PurchaseType.RENEW:
            if not subscription:
                raise ValueError(f"No subscription found for renewal for user '{user.telegram_id}'")

            # Продление: от текущего expire или от сейчас (если уже истекла)
            base_date = max(subscription.expire_at, datetime_now())
            new_expire = base_date + timedelta(days=plan.duration)
            
            # Сохраняем текущие дополнительные устройства и пересчитываем лимит
            current_extra_devices = subscription.extra_devices or 0
            total_device_limit = plan.device_limit + current_extra_devices
            
            logger.info(
                f"[RENEW] Updating user in Remnawave: uuid={subscription.user_remna_id}, expire={new_expire}, "
                f"device_limits: plan={plan.device_limit}, extra={current_extra_devices}, total={total_device_limit}"
            )

            subscription.expire_at = new_expire
            subscription.plan = plan
            subscription.device_limit = total_device_limit  # Обновляем общий лимит
            subscription.extra_devices = current_extra_devices  # Сохраняем extra_devices
            
            await remnawave_service.updated_user(
                user=user,
                uuid=subscription.user_remna_id,
                subscription=subscription,
            )
            
            await subscription_service.update(subscription)
            logger.info(f"[RENEW] Renewed subscription for '{user.telegram_id}', expire_at={new_expire}")

        else:
            raise Exception(f"Unknown purchase type '{purchase_type}' for user '{user.telegram_id}'")

        # Очищаем кэш пользователя перед получением свежих данных
        await user_service.clear_user_cache(user.telegram_id)
        
        # Получаем свежего пользователя и редиректим на успех
        fresh_user = await user_service.get(telegram_id=user.telegram_id)
        await redirect_to_successed_payment_task.kiq(fresh_user or user, purchase_type)
        logger.info(f"[purchase_subscription_task] Completed for '{user.telegram_id}'")

    except Exception as exception:
        logger.exception(
            f"Failed to process purchase type '{purchase_type}' for user "
            f"'{user.telegram_id}' exception: {exception}"
        )
        traceback_str = traceback.format_exc()
        error_type_name = type(exception).__name__
        error_message = Text(str(exception)[:512])

        transaction.status = TransactionStatus.FAILED
        await transaction_service.update(transaction)

        await notification_service.error_notify(
            error_id=user.telegram_id,
            traceback_str=traceback_str,
            payload=MessagePayload.not_deleted(
                i18n_key="ntf-event-error",
                i18n_kwargs={
                    "user": True,
                    "user_id": str(user.telegram_id),
                    "user_name": user.name,
                    "username": user.username or False,
                    "error": f"{error_type_name}: {error_message.as_html()}",
                },
                reply_markup=get_user_keyboard(user.telegram_id),
            ),
        )

        await redirect_to_failed_subscription_task.kiq(user)


@broker.task
@inject
async def delete_current_subscription_task(
    remna_user: RemnaUserDto,
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
) -> None:
    logger.info(f"Delete current subscription started for user '{remna_user.telegram_id}'")

    if not remna_user.telegram_id:
        logger.debug(f"Skipping RemnaUser '{remna_user.username}': telegram_id is empty")
        return

    user = await user_service.get(remna_user.telegram_id)

    if not user:
        logger.debug(f"User '{remna_user.telegram_id}' not found, skipping deletion")
        return

    subscription = await subscription_service.get_current(user.telegram_id)

    if not subscription:
        logger.debug(f"No current subscription for user '{user.telegram_id}', skipping deletion")
        return

    # Проверяем, что UUID совпадает с удаляемым пользователем
    if subscription.user_remna_id != remna_user.uuid:
        logger.debug(
            f"Subscription user UUID differs for '{user.telegram_id}': "
            f"subscription UUID={subscription.user_remna_id}, deleted UUID={remna_user.uuid}, skipping deletion"
        )
        return

    # Проверяем, что подписка ещё не была удалена (избегаем гонки условий)
    if subscription.status == SubscriptionStatus.DELETED:
        logger.debug(f"Subscription for user '{user.telegram_id}' already deleted, skipping")
        return

    # Проверяем, что подписка не была только что создана (защита от гонки условий при переходе с trial)
    # Если подписка была создана менее 30 секунд назад, пропускаем удаление
    if subscription.created_at:
        time_since_creation = datetime_now() - subscription.created_at
        if time_since_creation.total_seconds() < 30:
            logger.warning(
                f"Subscription for user '{user.telegram_id}' was created {time_since_creation.total_seconds():.1f}s ago, "
                f"skipping deletion to avoid race condition"
            )
            return

    subscription.status = SubscriptionStatus.DELETED
    await subscription_service.update(subscription)
    await user_service.delete_current_subscription(user.telegram_id)
    logger.info(f"Successfully deleted subscription for user '{user.telegram_id}'")


@broker.task
@inject
async def update_status_current_subscription_task(
    user_telegram_id: int,
    status: SubscriptionStatus,
    user_service: FromDishka[UserService],
    subscription_service: FromDishka[SubscriptionService],
) -> None:
    logger.info(f"Update status current subscription started for user '{user_telegram_id}'")

    user = await user_service.get(user_telegram_id)

    if not user:
        logger.debug(f"User '{user_telegram_id}' not found, skipping status update")
        return

    subscription = await subscription_service.get_current(user.telegram_id)

    if not subscription:
        logger.debug(
            f"No current subscription for user '{user.telegram_id}', skipping status update"
        )
        return

    # Не обновляем статус если подписка была деактивирована или удалена локально
    # Эти статусы имеют приоритет над статусами от RemnaWave
    if subscription.status in [SubscriptionStatus.DISABLED, SubscriptionStatus.DELETED]:
        logger.debug(
            f"Subscription '{subscription.id}' has local status '{subscription.status}', "
            f"not overwriting with RemnaWave status '{status}'"
        )
        return

    subscription.status = status
    await subscription_service.update(subscription)


@broker.task(schedule=[{"cron": "0 * * * *"}])  # Каждый час
@inject
async def check_expired_extra_devices_task(
    extra_device_service: FromDishka[ExtraDeviceService],
    subscription_service: FromDishka[SubscriptionService],
    remnawave_service: FromDishka[RemnawaveService],
    user_service: FromDishka[UserService],
    notification_service: FromDishka[NotificationService],
) -> None:
    """
    Проверяет истекшие дополнительные устройства и деактивирует их.
    Запускается каждый час.
    """
    logger.info("[check_expired_extra_devices] Starting check for expired extra devices")
    
    expired_purchases = await extra_device_service.get_expired_active_purchases()
    
    if not expired_purchases:
        logger.info("[check_expired_extra_devices] No expired purchases found")
        return
    
    logger.info(f"[check_expired_extra_devices] Found {len(expired_purchases)} expired purchases")
    
    for purchase in expired_purchases:
        try:
            # Получаем подписку
            subscription = await subscription_service.get(purchase.subscription_id)
            if not subscription:
                logger.warning(f"Subscription '{purchase.subscription_id}' not found for purchase '{purchase.id}'")
                await extra_device_service.deactivate(purchase.id)
                continue
            
            # Получаем пользователя
            user = await user_service.get(purchase.user_telegram_id)
            if not user:
                logger.warning(f"User '{purchase.user_telegram_id}' not found for purchase '{purchase.id}'")
                await extra_device_service.deactivate(purchase.id)
                continue
            
            device_count_to_remove = purchase.device_count
            
            # Если автопродление отключено - просто деактивируем и уменьшаем лимит
            if not purchase.auto_renew:
                logger.info(f"[check_expired_extra_devices] Auto-renew disabled for purchase '{purchase.id}', deactivating")
                
                # Деактивируем покупку
                await extra_device_service.deactivate(purchase.id)
                
                # Обновляем лимит устройств в подписке
                new_extra_devices = max(0, (subscription.extra_devices or 0) - device_count_to_remove)
                new_device_limit = max(subscription.plan.device_limit, (subscription.device_limit or 0) - device_count_to_remove)
                
                subscription.extra_devices = new_extra_devices
                subscription.device_limit = new_device_limit
                
                await subscription_service.update(subscription)
                
                # Обновляем в Remnawave
                await remnawave_service.updated_user(
                    user=user,
                    uuid=subscription.user_remna_id,
                    subscription=subscription,
                )
                
                # Очищаем кеш
                await user_service.clear_user_cache(user.telegram_id)
                
                # Уведомляем пользователя
                await notification_service.notify_user(
                    user=user,
                    payload=MessagePayload(
                        i18n_key="ntf-extra-device-expired",
                        i18n_kwargs={
                            "device_count": device_count_to_remove,
                        },
                    ),
                )
                
                logger.info(
                    f"[check_expired_extra_devices] Deactivated purchase '{purchase.id}' for user '{user.telegram_id}', "
                    f"removed {device_count_to_remove} devices"
                )
            else:
                # Автопродление включено - проверяем баланс и продлеваем
                if user.balance >= purchase.price:
                    # Списываем с баланса и продлеваем
                    await user_service.subtract_from_balance(user, purchase.price)
                    await extra_device_service.renew_purchase(purchase.id, duration_days=30)
                    
                    # Очищаем кеш
                    await user_service.clear_user_cache(user.telegram_id)
                    
                    logger.info(
                        f"[check_expired_extra_devices] Auto-renewed purchase '{purchase.id}' for user '{user.telegram_id}', "
                        f"charged {purchase.price} ₽"
                    )
                    
                    await notification_service.notify_user(
                        user=user,
                        payload=MessagePayload(
                            i18n_key="ntf-extra-device-renewed",
                            i18n_kwargs={
                                "device_count": device_count_to_remove,
                                "price": purchase.price,
                            },
                        ),
                    )
                else:
                    # Недостаточно средств - деактивируем
                    logger.info(
                        f"[check_expired_extra_devices] Insufficient balance for auto-renew purchase '{purchase.id}' "
                        f"(user={user.telegram_id}, balance={user.balance}, price={purchase.price})"
                    )
                    
                    await extra_device_service.deactivate(purchase.id)
                    
                    # Обновляем лимит устройств
                    new_extra_devices = max(0, (subscription.extra_devices or 0) - device_count_to_remove)
                    new_device_limit = max(subscription.plan.device_limit, (subscription.device_limit or 0) - device_count_to_remove)
                    
                    subscription.extra_devices = new_extra_devices
                    subscription.device_limit = new_device_limit
                    
                    await subscription_service.update(subscription)
                    
                    # Обновляем в Remnawave
                    await remnawave_service.updated_user(
                        user=user,
                        uuid=subscription.user_remna_id,
                        subscription=subscription,
                    )
                    
                    # Очищаем кеш
                    await user_service.clear_user_cache(user.telegram_id)
                    
                    await notification_service.notify_user(
                        user=user,
                        payload=MessagePayload(
                            i18n_key="ntf-extra-device-expired-no-balance",
                            i18n_kwargs={
                                "device_count": device_count_to_remove,
                                "price": purchase.price,
                            },
                        ),
                    )
                    
        except Exception as e:
            logger.exception(f"[check_expired_extra_devices] Error processing purchase '{purchase.id}': {e}")
    
    logger.info("[check_expired_extra_devices] Completed")