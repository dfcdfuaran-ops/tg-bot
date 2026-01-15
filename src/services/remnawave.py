from datetime import timedelta
from typing import Optional, cast
from uuid import UUID

from aiogram import Bot
from fluentogram import TranslatorHub
from loguru import logger
from redis.asyncio import Redis
from remnapy import RemnawaveSDK
from remnapy.exceptions import ConflictError, NotFoundError
from remnapy.exceptions.general import ConflictError as GeneralConflictError
from remnapy.exceptions.general import ServerError
from remnapy.models import (
    CreateUserRequestDto,
    CreateUserResponseDto,
    GetStatsResponseDto,
    HWIDDeleteRequest,
    HwidUserDeviceDto,
    UpdateUserRequestDto,
    UserResponseDto,
)
from remnapy.models.hwid import HwidDeviceDto
from remnapy.models.webhook import NodeDto

from src.bot.keyboards import get_user_keyboard
from src.core.config import AppConfig
from src.core.constants import DATETIME_FORMAT, IMPORTED_TAG
from src.core.enums import (
    RemnaNodeEvent,
    RemnaUserEvent,
    RemnaUserHwidDevicesEvent,
    SubscriptionStatus,
    SystemNotificationType,
    UserNotificationType,
)
from src.core.i18n.keys import ByteUnitKey
from src.core.utils.formatters import (
    format_country_code,
    format_days_to_datetime,
    format_device_count,
    format_gb_to_bytes,
    format_limits_to_plan_type,
    i18n_format_bytes_to_unit,
    i18n_format_device_limit,
    i18n_format_expire_time,
    i18n_format_traffic_limit,
)
from src.core.utils.message_payload import MessagePayload
from src.core.utils.time import datetime_now
from src.core.utils.types import RemnaUserDto
from src.infrastructure.database.models.dto import (
    PlanSnapshotDto,
    RemnaSubscriptionDto,
    SubscriptionDto,
    UserDto,
)
from src.infrastructure.redis import RedisRepository
from src.infrastructure.taskiq.tasks.notifications import (
    send_subscription_expire_notification_task,
    send_subscription_limited_notification_task,
    send_system_notification_task,
)
from src.services.notification import NotificationService
from src.services.plan import PlanService
from src.services.subscription import SubscriptionService
from src.services.user import UserService

from .base import BaseService


class RemnawaveService(BaseService):
    remnawave: RemnawaveSDK
    user_service: UserService
    subscription_service: SubscriptionService
    plan_service: PlanService

    def __init__(
        self,
        config: AppConfig,
        bot: Bot,
        redis_client: Redis,
        redis_repository: RedisRepository,
        translator_hub: TranslatorHub,
        #
        remnawave: RemnawaveSDK,
        user_service: UserService,
        subscription_service: SubscriptionService,
        notification_service: NotificationService,
        plan_service: PlanService,
    ) -> None:
        super().__init__(config, bot, redis_client, redis_repository, translator_hub)
        self.remnawave = remnawave
        self.user_service = user_service
        self.subscription_service = subscription_service
        self.notification_service = notification_service
        self.plan_service = plan_service

    async def try_connection(self) -> None:
        response = await self.remnawave.system.get_stats()

        if not isinstance(response, GetStatsResponseDto):
            raise ValueError(f"Invalid response from Remnawave panel: {response}")

    async def _validate_and_get_squads(
        self,
        internal_squads: list[UUID] | None,
        external_squad_uuid: UUID | None,
    ) -> tuple[list[UUID], UUID | None]:
        """
        Validates squads existence in panel and returns valid ones.
        If squads don't exist, returns default squad from panel.
        
        Returns: (valid_internal_squads, valid_external_squad_uuid)
        """
        valid_internal_squads: list[UUID] = []
        valid_external_squad_uuid: UUID | None = None
        
        try:
            # Get all squads from panel
            panel_squads = await self.remnawave.internal_squads.get_internal_squads()
            
            if not panel_squads or not panel_squads.internal_squads:
                logger.warning("No internal squads found in panel")
                return [], None
            
            # Create set of valid squad UUIDs for quick lookup
            valid_squad_uuids = {squad.uuid for squad in panel_squads.internal_squads}
            
            # Validate internal_squads
            if internal_squads:
                for squad_uuid in internal_squads:
                    if squad_uuid in valid_squad_uuids:
                        valid_internal_squads.append(squad_uuid)
                    else:
                        logger.warning(
                            f"Internal squad {squad_uuid} not found in panel, skipping"
                        )
            
            # If no valid internal squads found, use first squad from panel as default
            if not valid_internal_squads:
                default_squad = panel_squads.internal_squads[0]
                valid_internal_squads = [default_squad.uuid]
                logger.info(
                    f"No valid internal squads provided or found, using default: "
                    f"{default_squad.name} ({default_squad.uuid})"
                )
            
            # Validate external_squad if provided
            if external_squad_uuid:
                try:
                    external_squads_response = await self.remnawave.external_squads.get_external_squads()
                    if external_squads_response and external_squads_response.external_squads:
                        valid_external_uuids = {squad.uuid for squad in external_squads_response.external_squads}
                        if external_squad_uuid in valid_external_uuids:
                            valid_external_squad_uuid = external_squad_uuid
                            logger.debug(f"External squad {external_squad_uuid} validated successfully")
                        else:
                            logger.warning(
                                f"External squad {external_squad_uuid} not found in panel, skipping"
                            )
                    else:
                        logger.warning("No external squads found in panel")
                except Exception as e:
                    logger.warning(f"Failed to validate external squad: {e}")
            
        except Exception as e:
            logger.error(f"Failed to validate squads: {e}")
            # Return empty list on error - let the API handle it
            return [], None
        
        return valid_internal_squads, valid_external_squad_uuid

    async def create_user(
        self,
        user: UserDto,
        plan: Optional[PlanSnapshotDto] = None,
        subscription: Optional[SubscriptionDto] = None,
        force: bool = False,
    ) -> UserResponseDto:
        async def _do_create() -> CreateUserResponseDto:
            if subscription:
                logger.info(
                    f"Creating RemnaUser '{user.remna_name}' "
                    f"from subscription '{subscription.plan.name}'"
                )
                
                # Используем сквады из подписки (или из плана если в подписке нет)
                internal_squads: list[UUID] = []
                if subscription.internal_squads:
                    internal_squads = subscription.internal_squads
                elif subscription.plan and subscription.plan.internal_squads:
                    internal_squads = subscription.plan.internal_squads
                
                # Get external squad
                external_squad = subscription.external_squad[0] if subscription.external_squad else None
                
                # Validate squads and get valid ones
                valid_internal_squads, valid_external_squad = await self._validate_and_get_squads(
                    internal_squads, external_squad
                )
                
                # Извлекаем short_uuid из URL подписки
                short_uuid = None
                if subscription.url:
                    try:
                        # URL формат: https://sub.domain.com/SHORT_UUID
                        short_uuid = subscription.url.rstrip('/').split('/')[-1]
                        logger.debug(f"Extracted short_uuid from URL: {short_uuid}")
                    except Exception as e:
                        logger.warning(f"Failed to extract short_uuid from URL '{subscription.url}': {e}")
                
                return await self.remnawave.users.create_user(
                    CreateUserRequestDto(
                        uuid=subscription.user_remna_id,
                        short_uuid=short_uuid,
                        expire_at=subscription.expire_at,
                        username=user.remna_name,
                        traffic_limit_bytes=format_gb_to_bytes(subscription.traffic_limit),
                        traffic_limit_strategy=subscription.traffic_limit_strategy,
                        description=user.remna_description,
                        tag=subscription.tag,
                        telegram_id=user.telegram_id,
                        hwid_device_limit=format_device_count(subscription.device_limit),
                        active_internal_squads=valid_internal_squads,
                        external_squad_uuid=valid_external_squad,
                    )
                )

            if plan:
                logger.info(f"Creating RemnaUser '{user.telegram_id}' from plan '{plan.name}'")
                
                # Prepare external_squad_uuid - handle None values in list
                external_squad_uuid = None
                if plan.external_squad:
                    # Filter out None values and get first valid UUID
                    valid_squads = [squad for squad in plan.external_squad if squad is not None]
                    if valid_squads:
                        external_squad_uuid = valid_squads[0]
                
                # Validate squads and get valid ones
                valid_internal_squads, valid_external_squad = await self._validate_and_get_squads(
                    plan.internal_squads, external_squad_uuid
                )
                
                # Prepare request data
                request_data = CreateUserRequestDto(
                    expire_at=format_days_to_datetime(plan.duration),
                    username=user.remna_name,
                    traffic_limit_bytes=format_gb_to_bytes(plan.traffic_limit),
                    traffic_limit_strategy=plan.traffic_limit_strategy,
                    description=user.remna_description,
                    tag=plan.tag,
                    telegram_id=user.telegram_id,
                    hwid_device_limit=format_device_count(plan.device_limit),
                    active_internal_squads=valid_internal_squads,
                    external_squad_uuid=valid_external_squad,
                )
                
                # Log request data for debugging
                logger.debug(
                    f"Creating user with data: "
                    f"username={request_data.username}, "
                    f"telegram_id={request_data.telegram_id}, "
                    f"expire_at={request_data.expire_at}, "
                    f"traffic_limit_bytes={request_data.traffic_limit_bytes}, "
                    f"hwid_device_limit={request_data.hwid_device_limit}, "
                    f"active_internal_squads={request_data.active_internal_squads}, "
                    f"external_squad_uuid={request_data.external_squad_uuid}, "
                    f"tag={request_data.tag}"
                )
                
                return await self.remnawave.users.create_user(request_data)

            raise ValueError("Either 'plan' or 'subscription' must be provided")

        try:
            created = await _do_create()

        except (ConflictError, GeneralConflictError, ServerError) as e:
            # ServerError (500) может возникать при попытке создать пользователя, который уже существует
            # ConflictError (400) - стандартная ошибка при дубликате
            logger.error(f"User creation failed with error: {e}, force={force}")
            if not force:
                raise

            logger.warning(
                f"User '{user.remna_name}' already exists in Remnawave (or server error on creation). "
                f"Force flag enabled, will try to find and update/recreate existing user"
            )
            
            try:
                # Сначала пытаемся найти пользователя по telegram_id (более надежный способ)
                telegram_result = await self.remnawave.users.get_users_by_telegram_id(
                    telegram_id=str(user.telegram_id)
                )
                
                if telegram_result:
                    old_remna_user = telegram_result[0]
                    logger.info(
                        f"Found existing user by telegram_id '{user.telegram_id}': uuid={old_remna_user.uuid}, "
                        f"username={old_remna_user.username}, short_uuid={old_remna_user.short_uuid}"
                    )
                else:
                    # Если не найден по telegram_id, ищем по username
                    try:
                        old_remna_user = await self.remnawave.users.get_user_by_username(user.remna_name)
                        logger.info(f"Found existing user by username: uuid={old_remna_user.uuid}, short_uuid={old_remna_user.short_uuid}")
                    except NotFoundError:
                        # Пользователь не найден ни по telegram_id, ни по username
                        # Это странная ситуация (500 ошибка, но пользователя нет)
                        # Скорее всего он был удален между попытками
                        logger.warning(
                            f"User not found by telegram_id or username after ServerError. "
                            f"User might have been deleted. Will try to create user again."
                        )
                        
                        logger.info(f"Attempting to create user: {user.remna_name}")
                        
                        # Создаем request_data с модифицированным username напрямую
                        if plan:
                            external_squad_uuid = None
                            if plan.external_squad:
                                valid_squads = [squad for squad in plan.external_squad if squad is not None]
                                if valid_squads:
                                    external_squad_uuid = valid_squads[0]
                            
                            valid_internal_squads, valid_external_squad = await self._validate_and_get_squads(
                                plan.internal_squads, external_squad_uuid
                            )
                            
                            modified_request = CreateUserRequestDto(
                                expire_at=format_days_to_datetime(plan.duration),
                                username=user.remna_name,
                                traffic_limit_bytes=format_gb_to_bytes(plan.traffic_limit),
                                traffic_limit_strategy=plan.traffic_limit_strategy,
                                description=user.remna_description,
                                tag=plan.tag,
                                telegram_id=user.telegram_id,
                                hwid_device_limit=format_device_count(plan.device_limit),
                                active_internal_squads=valid_internal_squads,
                                external_squad_uuid=valid_external_squad,
                            )
                            
                            # Логируем полный запрос для отладки
                            logger.debug(
                                f"Modified user creation request: "
                                f"username={modified_request.username}, "
                                f"telegram_id={modified_request.telegram_id}, "
                                f"expire_at={modified_request.expire_at}, "
                                f"traffic_limit_bytes={modified_request.traffic_limit_bytes}, "
                                f"hwid_device_limit={modified_request.hwid_device_limit}, "
                                f"active_internal_squads={modified_request.active_internal_squads}, "
                                f"external_squad_uuid={modified_request.external_squad_uuid}, "
                                f"tag={modified_request.tag}"
                            )
                            
                            try:
                                created = await self.remnawave.users.create_user(modified_request)
                                logger.info(f"Successfully created user: {user.remna_name}")
                                return created
                            except ServerError as se:
                                logger.error(
                                    f"ServerError 500 when creating user. "
                                    f"This indicates an issue with Remnawave API or database. "
                                    f"Error: {se}"
                                )
                                # Пробуем создать с минимальными параметрами (без squad'ов)
                                logger.info("Attempting to create user with minimal parameters (empty squads)")
                                minimal_request = CreateUserRequestDto(
                                    expire_at=format_days_to_datetime(plan.duration),
                                    username=user.remna_name,
                                    traffic_limit_bytes=format_gb_to_bytes(plan.traffic_limit),
                                    traffic_limit_strategy=plan.traffic_limit_strategy,
                                    description=user.remna_description,
                                    tag=plan.tag,
                                    telegram_id=user.telegram_id,
                                    hwid_device_limit=format_device_count(plan.device_limit),
                                    active_internal_squads=[],  # Пустой массив, не None!
                                    external_squad_uuid=None,  # Без external squad
                                )
                                
                                created = await self.remnawave.users.create_user(minimal_request)
                                logger.warning(
                                    f"User created with minimal parameters (no squads): {user.remna_name}. "
                                    f"You may need to manually assign squads in Remnawave panel."
                                )
                                return created
                        elif subscription:
                            internal_squads = subscription.internal_squads or []
                            if not internal_squads and subscription.plan and subscription.plan.internal_squads:
                                internal_squads = subscription.plan.internal_squads
                            
                            external_squad = None
                            if subscription.external_squad and len(subscription.external_squad) > 0:
                                external_squad = subscription.external_squad[0]
                            elif subscription.plan and subscription.plan.external_squad and len(subscription.plan.external_squad) > 0:
                                external_squad = subscription.plan.external_squad[0]
                            
                            valid_internal_squads, valid_external_squad = await self._validate_and_get_squads(
                                internal_squads, external_squad
                            )
                            
                            short_uuid = None
                            try:
                                short_uuid = subscription.url.rstrip('/').split('/')[-1]
                                logger.debug(f"Extracted short_uuid from URL: {short_uuid}")
                            except Exception as e:
                                logger.warning(f"Failed to extract short_uuid from URL '{subscription.url}': {e}")
                            
                            modified_request = CreateUserRequestDto(
                                status=subscription.status,
                                short_uuid=short_uuid,
                                expire_at=subscription.expire_at,
                                username=user.remna_name,
                                traffic_limit_bytes=format_gb_to_bytes(subscription.traffic_limit),
                                traffic_limit_strategy=subscription.traffic_limit_strategy,
                                description=user.remna_description,
                                tag=subscription.tag,
                                telegram_id=user.telegram_id,
                                hwid_device_limit=format_device_count(subscription.device_limit),
                                active_internal_squads=valid_internal_squads,
                                external_squad_uuid=valid_external_squad,
                            )
                            
                            logger.debug(
                                f"Modified user creation request: "
                                f"username={modified_request.username}, "
                                f"telegram_id={modified_request.telegram_id}, "
                                f"expire_at={modified_request.expire_at}, "
                                f"traffic_limit_bytes={modified_request.traffic_limit_bytes}, "
                                f"active_internal_squads={modified_request.active_internal_squads}, "
                                f"external_squad_uuid={modified_request.external_squad_uuid}"
                            )
                            
                            try:
                                created = await self.remnawave.users.create_user(modified_request)
                                logger.info(f"Successfully created user: {user.remna_name}")
                                return created
                            except ServerError as se:
                                logger.error(
                                    f"ServerError 500 when creating user. "
                                    f"This indicates an issue with Remnawave API or database. "
                                    f"Error: {se}"
                                )
                                # Пробуем создать с минимальными параметрами (без squad'ов)
                                logger.info("Attempting to create user with minimal parameters (empty squads)")
                                minimal_request = CreateUserRequestDto(
                                    status=subscription.status,
                                    short_uuid=short_uuid,
                                    expire_at=subscription.expire_at,
                                    username=user.remna_name,
                                    traffic_limit_bytes=format_gb_to_bytes(subscription.traffic_limit),
                                    traffic_limit_strategy=subscription.traffic_limit_strategy,
                                    description=user.remna_description,
                                    tag=subscription.tag,
                                    telegram_id=user.telegram_id,
                                    hwid_device_limit=format_device_count(subscription.device_limit),
                                    active_internal_squads=[],  # Пустой массив (API требует array, не null)
                                    external_squad_uuid=None,
                                )
                                
                                created = await self.remnawave.users.create_user(minimal_request)
                                logger.warning(
                                    f"User created with minimal parameters (no squads): {user.remna_name}. "
                                    f"You may need to manually assign squads in Remnawave panel."
                                )
                                return created
                        else:
                            raise ValueError("Either 'plan' or 'subscription' must be provided")
                
                # Если есть подписка с URL, извлекаем short_uuid и ВСЕГДА проверяем/обновляем
                need_recreate = False
                if subscription and subscription.url:
                    try:
                        desired_short_uuid = subscription.url.rstrip('/').split('/')[-1]
                        # ВСЕГДА пересоздаем пользователя, если есть short_uuid из бэкапа
                        # чтобы гарантировать совпадение URL подписки в панели и БД
                        logger.info(
                            f"short_uuid from backup: {desired_short_uuid}, "
                            f"existing in panel: {old_remna_user.short_uuid}. "
                            f"Will recreate user to ensure consistency."
                        )
                        need_recreate = True
                    except Exception as ex:
                        logger.warning(f"Failed to extract short_uuid from URL '{subscription.url}': {ex}")
                
                # Если нужно пересоздать пользователя для сохранения short_uuid
                if need_recreate:
                    logger.info(f"Deleting user {old_remna_user.uuid} to recreate with correct short_uuid")
                    await self.remnawave.users.delete_user(old_remna_user.uuid)
                    
                    # Пробуем создать заново
                    created = await _do_create()
                    logger.info(
                        f"User recreated successfully with short_uuid={created.short_uuid}"
                    )
                    return created
                
                # Обновляем пользователя вместо удаления и пересоздания
                logger.info(f"Updating existing user {old_remna_user.uuid} instead of recreating")
                
                try:
                    if plan:
                        updated = await self.updated_user(
                            user=user,
                            uuid=old_remna_user.uuid,
                            plan=plan,
                            reset_traffic=True,
                        )
                        # Возвращаем данные в формате CreateUserResponseDto
                        return updated
                    elif subscription:
                        updated = await self.updated_user(
                            user=user,
                            uuid=old_remna_user.uuid,
                            subscription=subscription,
                            reset_traffic=True,
                        )
                        return updated
                    else:
                        raise ValueError("Either 'plan' or 'subscription' must be provided for update")
                        
                except Exception as update_error:
                    # Если обновление не удалось (например, 500 ошибка из-за некорректных данных),
                    # пробуем пересоздать пользователя
                    logger.error(
                        f"Failed to update existing user {old_remna_user.uuid}: {update_error}. "
                        f"Will try to delete and recreate"
                    )
                    
                    try:
                        # Удаляем проблемного пользователя
                        await self.remnawave.users.delete_user(old_remna_user.uuid)
                        logger.info(f"Deleted problematic user {old_remna_user.uuid}")
                        
                        # Создаем заново
                        created = await _do_create()
                        logger.info(f"User recreated successfully after update failure: {created.uuid}")
                        return created
                    except Exception as recreate_error:
                        logger.error(f"Failed to recreate user after update failure: {recreate_error}")
                        raise
                    
            except Exception as handle_error:
                logger.error(f"Failed to handle existing user: {handle_error}")
                raise

        logger.info(f"RemnaUser '{created.username}' created successfully")
        return created

    async def updated_user(
        self,
        user: UserDto,
        uuid: UUID,
        plan: Optional[PlanSnapshotDto] = None,
        subscription: Optional[SubscriptionDto] = None,
        reset_traffic: bool = False,
    ) -> UserResponseDto:
        if subscription:
            logger.info(
                f"Updating RemnaUser '{user.telegram_id}' from subscription '{subscription.id}'"
            )
            status = (
                SubscriptionStatus.DISABLED
                if subscription.status == SubscriptionStatus.DISABLED
                else SubscriptionStatus.ACTIVE
            )
            traffic_limit = subscription.traffic_limit
            device_limit = subscription.device_limit
            
            # Используем сквады из подписки (или из плана если в подписке нет)
            internal_squads: list[UUID] = []
            if subscription.internal_squads:
                internal_squads = subscription.internal_squads
            elif subscription.plan and subscription.plan.internal_squads:
                internal_squads = subscription.plan.internal_squads
            
            # Используем external_squad из подписки (или из плана если в подписке нет)
            external_squad = None
            if subscription.external_squad and len(subscription.external_squad) > 0:
                external_squad = subscription.external_squad[0]
            elif subscription.plan and subscription.plan.external_squad and len(subscription.plan.external_squad) > 0:
                external_squad = subscription.plan.external_squad[0]
            
            # Validate squads
            valid_internal_squads, valid_external_squad = await self._validate_and_get_squads(
                internal_squads, external_squad
            )
            
            expire_at = subscription.expire_at
            tag = subscription.tag
            strategy = subscription.traffic_limit_strategy

        elif plan:
            logger.info(f"Updating RemnaUser '{user.telegram_id}' from plan '{plan.name}'")
            status = SubscriptionStatus.ACTIVE
            traffic_limit = plan.traffic_limit
            device_limit = plan.device_limit
            external_squad = plan.external_squad[0] if plan.external_squad else None
            
            # Validate squads
            valid_internal_squads, valid_external_squad = await self._validate_and_get_squads(
                plan.internal_squads, external_squad
            )
            
            expire_at = format_days_to_datetime(plan.duration)
            tag = plan.tag
            strategy = plan.traffic_limit_strategy
        else:
            raise ValueError("Either 'plan' or 'subscription' must be provided")

        updated_user = await self.remnawave.users.update_user(
            UpdateUserRequestDto(
                uuid=uuid,
                active_internal_squads=valid_internal_squads,
                external_squad_uuid=valid_external_squad,
                description=user.remna_description,
                tag=tag,
                expire_at=expire_at,
                hwid_device_limit=format_device_count(device_limit),
                status=status,
                telegram_id=user.telegram_id,
                traffic_limit_bytes=format_gb_to_bytes(traffic_limit),
                traffic_limit_strategy=strategy,
            )
        )

        if reset_traffic:
            await self.remnawave.users.reset_user_traffic(uuid)
            logger.info(f"Traffic reset for RemnaUser '{user.telegram_id}'")

        logger.info(f"RemnaUser '{user.telegram_id}' updated successfully")
        return updated_user

    async def delete_user(self, user: UserDto) -> bool:
        logger.info(f"Deleting RemnaUser '{user.telegram_id}'")

        if not user.current_subscription:
            logger.warning(f"No current subscription for user '{user.telegram_id}'")

            users_result = await self.remnawave.users.get_users_by_telegram_id(
                telegram_id=str(user.telegram_id)
            )

            if not users_result:
                return False

            uuid = users_result[0].uuid
        else:
            uuid = user.current_subscription.user_remna_id

        result = await self.remnawave.users.delete_user(uuid)

        if result.is_deleted:
            logger.info(f"RemnaUser '{user.telegram_id}' deleted successfully")
        else:
            logger.warning(f"RemnaUser '{user.telegram_id}' deletion failed")

        return result.is_deleted

    async def get_devices_user(self, user: UserDto) -> list[HwidDeviceDto]:
        logger.info(f"Fetching devices for RemnaUser '{user.telegram_id}'")

        if not user.current_subscription:
            logger.warning(f"No subscription found for user '{user.telegram_id}'")
            return []

        try:
            result = await self.remnawave.hwid.get_hwid_user(user.current_subscription.user_remna_id)
        except Exception as e:
            logger.warning(
                f"Failed to get devices for user '{user.telegram_id}' "
                f"with remna_id '{user.current_subscription.user_remna_id}': {e}"
            )
            return []

        if result.total:
            logger.info(f"Found '{result.total}' device(s) for RemnaUser '{user.telegram_id}'")
            return result.devices

        logger.info(f"No devices found for RemnaUser '{user.telegram_id}'")
        return []

    async def delete_device(self, user: UserDto, hwid: str) -> Optional[int]:
        logger.info(f"Deleting device '{hwid}' for RemnaUser '{user.telegram_id}'")

        if not user.current_subscription:
            logger.warning(f"No subscription found for user '{user.telegram_id}'")
            return None

        result = await self.remnawave.hwid.delete_hwid_to_user(
            HWIDDeleteRequest(
                user_uuid=user.current_subscription.user_remna_id,
                hwid=hwid,
            )
        )

        logger.info(f"Deleted device '{hwid}' for RemnaUser '{user.telegram_id}'")
        return result.total

    async def get_user(self, uuid: UUID) -> Optional[UserResponseDto]:
        logger.info(f"Fetching RemnaUser '{uuid}'")
        try:
            remna_user = await self.remnawave.users.get_user_by_uuid(uuid)
        except NotFoundError:
            logger.warning(f"RemnaUser '{uuid}' not found")
            return None

        logger.info(f"RemnaUser '{remna_user.telegram_id}' fetched successfully")
        return remna_user

    async def get_subscription_url(self, uuid: UUID) -> Optional[str]:
        remna_user = await self.get_user(uuid)

        if remna_user is None:
            logger.warning(f"RemnaUser '{uuid}' has not subscription url")
            return None

        return remna_user.subscription_url

    async def sync_user(self, remna_user: RemnaUserDto, creating: bool = True) -> None:
        if not remna_user.telegram_id:
            logger.warning(f"Skipping sync for '{remna_user.username}', missing 'telegram_id'")
            return

        user = await self.user_service.get(telegram_id=remna_user.telegram_id)

        if not user and creating:
            logger.debug(f"User '{remna_user.telegram_id}' not found in bot, creating new user")
            user = await self.user_service.create_from_panel(remna_user)

        user = cast(UserDto, user)
        subscription = await self.subscription_service.get_current(telegram_id=user.telegram_id)
        remna_subscription = RemnaSubscriptionDto.from_remna_user(remna_user)

        if not remna_subscription.url:
            remna_subscription.url = await self.get_subscription_url(remna_user.uuid)  # type: ignore[assignment]

        if not subscription:
            # Check if user has any existing subscriptions (not just current)
            all_user_subscriptions = await self.subscription_service.get_all_by_user(user.telegram_id)
            
            # Filter out IMPORTED subscriptions and prefer updating existing ones
            non_imported_subscriptions = [
                sub for sub in all_user_subscriptions 
                if sub.plan.name != IMPORTED_TAG
            ]
            
            if non_imported_subscriptions:
                # Prefer the non-IMPORTED subscription (usually the most recent one)
                subscription = non_imported_subscriptions[0]
                logger.info(
                    f"Found existing non-IMPORTED subscription '{subscription.id}' for user '{user.telegram_id}', "
                    f"will update instead of creating new IMPORTED subscription"
                )
            else:
                logger.info(f"No subscription found for '{user.telegram_id}', creating IMPORTED")

                temp_plan = PlanSnapshotDto(
                    id=-1,
                    name=IMPORTED_TAG,
                    tag=remna_subscription.tag,
                    type=format_limits_to_plan_type(
                        remna_subscription.traffic_limit,
                        remna_subscription.device_limit,
                    ),
                    traffic_limit=remna_subscription.traffic_limit,
                    device_limit=remna_subscription.device_limit,
                    duration=-1,
                    traffic_limit_strategy=remna_subscription.traffic_limit_strategy,
                    internal_squads=remna_subscription.internal_squads,
                    external_squad=remna_subscription.external_squad,
                )

                expired = remna_user.expire_at and remna_user.expire_at < datetime_now()
                status = SubscriptionStatus.EXPIRED if expired else remna_user.status

                subscription = SubscriptionDto(
                    user_remna_id=remna_user.uuid,
                    status=status,
                    traffic_limit=temp_plan.traffic_limit,
                    device_limit=temp_plan.device_limit,
                    traffic_limit_strategy=temp_plan.traffic_limit_strategy,
                    tag=temp_plan.tag,
                    internal_squads=remna_subscription.internal_squads,
                    external_squad=remna_subscription.external_squad,
                    expire_at=remna_user.expire_at,
                    url=remna_subscription.url,
                    plan=temp_plan,
                )

                await self.subscription_service.create(user, subscription)
                logger.info(f"IMPORTED subscription created for '{user.telegram_id}'")
        
        # Update subscription (whether it was found as current or as non-IMPORTED)
        if subscription:
            # Проверяем, изменился ли тег и нужно ли переключить план
            old_tag = subscription.tag
            new_tag = remna_subscription.tag
            
            if old_tag != new_tag and new_tag:
                # Тег изменился, ищем план с таким тегом
                matching_plan = await self.plan_service.get_by_tag(new_tag)
                
                if matching_plan and matching_plan.is_active:
                    # Нашли активный план с таким тегом - переключаем подписку
                    logger.info(
                        f"Tag changed from '{old_tag}' to '{new_tag}' for user '{user.telegram_id}'. "
                        f"Switching subscription to plan '{matching_plan.name}' (ID: {matching_plan.id})"
                    )
                    
                    # Создаём снимок плана с текущей длительностью подписки
                    duration_days = -1  # unlimited по умолчанию
                    if subscription.expire_at:
                        remaining = subscription.expire_at - datetime_now()
                        duration_days = max(1, remaining.days)
                    
                    new_plan_snapshot = PlanSnapshotDto.from_plan(matching_plan, duration_days)
                    
                    # Сохраняем дополнительные устройства
                    extra_devices = subscription.extra_devices or 0
                    
                    # Новый лимит устройств = лимит плана + дополнительные устройства
                    new_device_limit = matching_plan.device_limit + extra_devices
                    
                    # Обновляем подписку с новым планом
                    subscription.plan = new_plan_snapshot
                    subscription.tag = new_tag
                    subscription.traffic_limit = matching_plan.traffic_limit
                    subscription.device_limit = new_device_limit
                    subscription.traffic_limit_strategy = matching_plan.traffic_limit_strategy
                    subscription.internal_squads = matching_plan.internal_squads.copy()
                    subscription.external_squad = matching_plan.external_squad.copy() if matching_plan.external_squad else None
                    
                    # Обновляем лимит устройств в Remnawave панели
                    try:
                        await self.remnawave.users.update_user(
                            UpdateUserRequestDto(
                                uuid=remna_user.uuid,
                                hwid_device_limit=format_device_count(new_device_limit),
                                traffic_limit_bytes=format_gb_to_bytes(matching_plan.traffic_limit),
                                traffic_limit_strategy=matching_plan.traffic_limit_strategy,
                            )
                        )
                        logger.info(
                            f"Updated RemnaUser '{user.telegram_id}' in panel with new device limit: {new_device_limit}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to update RemnaUser '{user.telegram_id}' in panel: {e}"
                        )
                    
                    logger.info(
                        f"Subscription plan switched to '{matching_plan.name}' for user '{user.telegram_id}'. "
                        f"Device limit: {matching_plan.device_limit} + {extra_devices} extra = {new_device_limit}"
                    )
                else:
                    if matching_plan:
                        logger.debug(
                            f"Found plan with tag '{new_tag}' but it's inactive, skipping switch"
                        )
                    else:
                        logger.debug(
                            f"No plan found with tag '{new_tag}', keeping current plan"
                        )
            
            logger.info(f"Synchronizing subscription for '{user.telegram_id}'")
            subscription = SubscriptionService.apply_sync(
                target=subscription,
                source=remna_subscription,
            )
            await self.subscription_service.update(subscription)
            logger.info(f"Subscription updated for '{user.telegram_id}'")

        logger.info(f"Sync completed for user '{remna_user.telegram_id}'")

    #

    async def handle_user_event(self, event: str, remna_user: RemnaUserDto) -> None:  # noqa: C901
        from src.infrastructure.taskiq.tasks.subscriptions import (  # noqa: PLC0415
            delete_current_subscription_task,
            update_status_current_subscription_task,
        )

        logger.info(f"Received event '{event}' for RemnaUser '{remna_user.telegram_id}'")

        if not remna_user.telegram_id:
            logger.debug(f"Skipping RemnaUser '{remna_user.username}': telegram_id is empty")
            return

        if event == RemnaUserEvent.CREATED:
            if remna_user.tag != IMPORTED_TAG:
                logger.debug(
                    f"Created RemnaUser '{remna_user.telegram_id}' "
                    f"is not tagged as '{IMPORTED_TAG}', skipping sync"
                )
            else:
                await self.sync_user(remna_user)
            return

        user = await self.user_service.get(telegram_id=remna_user.telegram_id)

        if not user:
            logger.warning(f"No local user found for telegram_id '{remna_user.telegram_id}'")
            return

        # Получаем информацию о плане из текущей подписки пользователя
        plan_name = user.current_subscription.plan.name if user.current_subscription and user.current_subscription.plan else "Unknown"
        
        # Убеждаемся что plan_name никогда не None
        if not plan_name:
            plan_name = "Unknown"

        # Вычисляем лимиты устройств
        extra_devices = 0
        device_limit_number = 0
        device_limit_bonus = 0
        
        if user.current_subscription:
            subscription = user.current_subscription
            extra_devices = subscription.extra_devices or 0
            plan_device_limit = subscription.plan.device_limit if subscription.plan and subscription.plan.device_limit > 0 else 0
            device_limit_number = plan_device_limit if plan_device_limit > 0 else subscription.device_limit
            device_limit_bonus = max(0, subscription.device_limit - plan_device_limit - extra_devices) if plan_device_limit > 0 else 0

        i18n_kwargs = {
            "is_trial": False,
            "user_id": str(user.telegram_id),
            "user_name": user.name,
            "username": user.username or False,
            "subscription_id": str(remna_user.uuid),
            "subscription_status": remna_user.status,
            "plan_name": plan_name,
            "traffic_used": i18n_format_bytes_to_unit(
                remna_user.used_traffic_bytes,
                min_unit=ByteUnitKey.MEGABYTE,
            ),
            "traffic_limit": (
                i18n_format_bytes_to_unit(remna_user.traffic_limit_bytes)
                if remna_user.traffic_limit_bytes > 0
                else i18n_format_traffic_limit(-1)
            ),
            "device_limit": (
                i18n_format_device_limit(remna_user.hwid_device_limit)
                if remna_user.hwid_device_limit
                else i18n_format_device_limit(-1)
            ),
            "device_limit_number": device_limit_number,
            "device_limit_bonus": device_limit_bonus,
            "extra_devices": extra_devices,
            "expire_time": i18n_format_expire_time(remna_user.expire_at),
        }

        if event == RemnaUserEvent.MODIFIED:
            logger.debug(f"RemnaUser '{remna_user.telegram_id}' modified")
            await self.sync_user(remna_user, creating=False)

        elif event == RemnaUserEvent.DELETED:
            logger.debug(f"RemnaUser '{remna_user.telegram_id}' deleted")
            await delete_current_subscription_task.kiq(remna_user)

        elif event in {
            RemnaUserEvent.REVOKED,
            RemnaUserEvent.ENABLED,
            RemnaUserEvent.DISABLED,
            RemnaUserEvent.LIMITED,
            RemnaUserEvent.EXPIRED,
        }:
            logger.debug(
                f"RemnaUser '{remna_user.telegram_id}' status changed to '{remna_user.status}'"
            )
            await update_status_current_subscription_task.kiq(
                user_telegram_id=remna_user.telegram_id,
                status=SubscriptionStatus(remna_user.status),
            )
            if event == RemnaUserEvent.LIMITED:
                await send_subscription_limited_notification_task.kiq(
                    remna_user=remna_user,
                    i18n_kwargs=i18n_kwargs,
                )
            elif event == RemnaUserEvent.EXPIRED:
                if remna_user.expire_at + timedelta(days=3) < datetime_now():
                    logger.debug(
                        f"Subscription for RemnaUser '{user.telegram_id}' expired more than "
                        "3 days ago, skipping - most likely an imported user"
                    )
                    return

                await send_subscription_expire_notification_task.kiq(
                    remna_user=remna_user,
                    ntf_type=UserNotificationType.EXPIRED,
                    i18n_kwargs=i18n_kwargs,
                )

        elif event == RemnaUserEvent.FIRST_CONNECTED:
            logger.debug(f"RemnaUser '{remna_user.telegram_id}' connected for the first time")
            await self.notification_service.system_notify(
                ntf_type=SystemNotificationType.USER_FIRST_CONNECTED,
                payload=MessagePayload.not_deleted(
                    i18n_key="ntf-event-user-first-connected",
                    i18n_kwargs=i18n_kwargs,
                    reply_markup=get_user_keyboard(user.telegram_id),
                ),
            )

        elif event in {
            RemnaUserEvent.EXPIRES_IN_72_HOURS,
            RemnaUserEvent.EXPIRES_IN_48_HOURS,
            RemnaUserEvent.EXPIRES_IN_24_HOURS,
            RemnaUserEvent.EXPIRED_24_HOURS_AGO,
        }:
            logger.debug(
                f"Sending expiration notification for RemnaUser '{remna_user.telegram_id}'"
            )
            expire_map = {
                RemnaUserEvent.EXPIRES_IN_72_HOURS: UserNotificationType.EXPIRES_IN_3_DAYS,
                RemnaUserEvent.EXPIRES_IN_48_HOURS: UserNotificationType.EXPIRES_IN_2_DAYS,
                RemnaUserEvent.EXPIRES_IN_24_HOURS: UserNotificationType.EXPIRES_IN_1_DAYS,
                RemnaUserEvent.EXPIRED_24_HOURS_AGO: UserNotificationType.EXPIRED_1_DAY_AGO,
            }
            await send_subscription_expire_notification_task.kiq(
                remna_user=remna_user,
                ntf_type=expire_map[RemnaUserEvent(event)],
                i18n_kwargs=i18n_kwargs,
            )
        else:
            logger.warning(f"Unhandled user event '{event}' for '{remna_user.telegram_id}'")

    async def handle_device_event(
        self,
        event: str,
        remna_user: RemnaUserDto,
        device: HwidUserDeviceDto,
    ) -> None:
        logger.info(f"Received device event '{event}' for RemnaUser '{remna_user.telegram_id}'")

        if not remna_user.telegram_id:
            logger.debug(f"Skipping RemnaUser '{remna_user.username}': telegram_id is empty")
            return

        user = await self.user_service.get(telegram_id=remna_user.telegram_id)

        if not user:
            logger.warning(f"No local user found for telegram_id '{remna_user.telegram_id}'")
            return

        if event == RemnaUserHwidDevicesEvent.ADDED:
            logger.debug(f"Device '{device.hwid}' added for RemnaUser '{remna_user.telegram_id}'")
            i18n_key = "ntf-event-user-hwid-added"

        elif event == RemnaUserHwidDevicesEvent.DELETED:
            logger.debug(f"Device '{device.hwid}' deleted for RemnaUser '{remna_user.telegram_id}'")
            i18n_key = "ntf-event-user-hwid-deleted"

        else:
            logger.warning(
                f"Unhandled device event '{event}' for RemnaUser '{remna_user.telegram_id}'"
            )
            return

        await send_system_notification_task.kiq(
            ntf_type=SystemNotificationType.USER_HWID,
            payload=MessagePayload.not_deleted(
                i18n_key=i18n_key,
                i18n_kwargs={
                    "user_id": str(user.telegram_id),
                    "user_name": user.name,
                    "username": user.username or False,
                    "hwid": device.hwid,
                    "platform": device.platform,
                    "device_model": device.device_model,
                    "os_version": device.os_version,
                    "user_agent": device.user_agent,
                },
                reply_markup=get_user_keyboard(user.telegram_id),
            ),
        )

    async def handle_node_event(self, event: str, node: NodeDto) -> None:
        logger.info(f"Received node event '{event}' for node '{node.name}'")

        if event == RemnaNodeEvent.CONNECTION_LOST:
            logger.warning(f"Connection lost for node '{node.name}'")
            i18n_key = "ntf-event-node-connection-lost"

        elif event == RemnaNodeEvent.CONNECTION_RESTORED:
            logger.info(f"Connection restored for node '{node.name}'")
            i18n_key = "ntf-event-node-connection-restored"

        elif event == RemnaNodeEvent.TRAFFIC_NOTIFY:
            # TODO: Temporarily shutting down the node (and plans?) before the traffic is reset
            logger.debug(f"Traffic threshold reached on node '{node.name}'")
            i18n_key = "ntf-event-node-traffic"

        else:
            logger.warning(f"Unhandled node event '{event}' for node '{node.name}'")
            return

        await self.notification_service.system_notify(
            ntf_type=SystemNotificationType.NODE_STATUS,
            payload=MessagePayload.not_deleted(
                i18n_key=i18n_key,
                i18n_kwargs={
                    "country": format_country_code(code=node.country_code),
                    "name": node.name,
                    "address": node.address,
                    "port": str(node.port),
                    "traffic_used": i18n_format_bytes_to_unit(node.traffic_used_bytes),
                    "traffic_limit": i18n_format_bytes_to_unit(node.traffic_limit_bytes),
                    "last_status_message": node.last_status_message or False,
                    "last_status_change": node.last_status_change.strftime(DATETIME_FORMAT)
                    if node.last_status_change
                    else False,
                },
            ),
        )
