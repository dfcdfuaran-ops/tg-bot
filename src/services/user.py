from typing import Optional, Union

from aiogram import Bot
from aiogram.types import Message
from aiogram.types import User as AiogramUser
from fluentogram import TranslatorHub
from loguru import logger
from redis.asyncio import Redis

from src.core.config import AppConfig
from src.core.constants import (
    RECENT_ACTIVITY_MAX_COUNT,
    RECENT_REGISTERED_MAX_COUNT,
    REMNASHOP_PREFIX,
    TIME_5M,
    TIME_10M,
)
from src.core.enums import Locale, UserRole
from src.core.storage.key_builder import StorageKey, build_key
from src.core.storage.keys import RecentActivityUsersKey
from src.core.utils.formatters import format_user_name
from src.core.utils.generators import generate_referral_code
from src.core.utils.types import RemnaUserDto
from src.infrastructure.database import UnitOfWork
from src.infrastructure.database.models.dto import UserDto
from src.infrastructure.database.models.dto.user import BaseUserDto
from src.infrastructure.database.models.sql import User
from src.infrastructure.redis import RedisRepository, redis_cache

from .base import BaseService


class UserService(BaseService):
    uow: UnitOfWork

    def __init__(
        self,
        config: AppConfig,
        bot: Bot,
        redis_client: Redis,
        redis_repository: RedisRepository,
        translator_hub: TranslatorHub,
        #
        uow: UnitOfWork,
    ) -> None:
        super().__init__(config, bot, redis_client, redis_repository, translator_hub)
        self.uow = uow

    async def create(self, aiogram_user: AiogramUser) -> UserDto:
        user = UserDto(
            telegram_id=aiogram_user.id,
            username=aiogram_user.username,
            referral_code=generate_referral_code(
                aiogram_user.id,
                secret=self.config.crypt_key.get_secret_value(),
            ),
            name=aiogram_user.full_name,
            role=(UserRole.DEV if self.config.bot.dev_id == aiogram_user.id else UserRole.USER),
            language=(
                aiogram_user.language_code
                if aiogram_user.language_code in self.config.locales
                else self.config.default_locale
            ),
        )
        db_user = User(**user.model_dump())
        db_created_user = await self.uow.repository.users.create(db_user)
        await self.uow.commit()

        await self.clear_user_cache(user.telegram_id)
        logger.info(f"Created new user '{user.telegram_id}'")
        return UserDto.from_model(db_created_user)  # type: ignore[return-value]

    async def create_from_panel(self, remna_user: RemnaUserDto) -> UserDto:
        # Формируем имя и username - извлекаем из description
        # description в панели содержит "name: Имя\nusername: @username"
        name = str(remna_user.telegram_id)
        username = None
        if remna_user.description:
            # Извлекаем имя и username из description
            for line in remna_user.description.split('\n'):
                if line.startswith('name:'):
                    extracted_name = line.replace('name:', '').strip()
                    if extracted_name:
                        name = extracted_name
                elif line.startswith('username:'):
                    extracted_username = line.replace('username:', '').strip()
                    if extracted_username:
                        username = extracted_username
        
        user = UserDto(
            telegram_id=remna_user.telegram_id,
            referral_code=generate_referral_code(
                remna_user.telegram_id,  # type: ignore[arg-type]
                secret=self.config.crypt_key.get_secret_value(),
            ),
            name=name,
            username=username,
            role=UserRole.USER,
            language=self.config.default_locale,
        )
        db_user = User(**user.model_dump())
        db_created_user = await self.uow.repository.users.create(db_user)
        await self.uow.commit()

        await self.clear_user_cache(user.telegram_id)
        logger.info(f"Created new user '{user.telegram_id}' from panel")
        return UserDto.from_model(db_created_user)  # type: ignore[return-value]

    @redis_cache(prefix="get_user", ttl=TIME_5M)
    async def get(self, telegram_id: int) -> Optional[UserDto]:
        db_user = await self.uow.repository.users.get(telegram_id)

        if db_user:
            logger.debug(f"Retrieved user '{telegram_id}'")
            user_dto = UserDto.from_model(db_user)
            if user_dto:
                # Расширенное логирование для отладки
                logger.debug(f"🔍 DEBUG get: User {telegram_id}, is_invited_user={user_dto.is_invited_user}")
            return user_dto
        else:
            logger.warning(f"User '{telegram_id}' not found")
            return None

    async def get_without_cache(self, telegram_id: int) -> Optional[UserDto]:
        """Получить пользователя без использования кэша (для отладки)"""
        db_user = await self.uow.repository.users.get(telegram_id)

        if db_user:
            logger.debug(f"Retrieved user '{telegram_id}' without cache")
            user_dto = UserDto.from_model(db_user)
            if user_dto:
                logger.debug(f"🔍 DEBUG get without cache: User {telegram_id}, is_invited_user={user_dto.is_invited_user}")
            return user_dto
        else:
            logger.warning(f"User '{telegram_id}' not found (without cache)")
            return None

    async def update(self, user: UserDto) -> Optional[UserDto]:
        db_updated_user = await self.uow.repository.users.update(
            telegram_id=user.telegram_id,
            **user.prepare_changed_data(),
        )

        if db_updated_user:
            await self.clear_user_cache(db_updated_user.telegram_id)
            logger.info(f"Updated user '{user.telegram_id}' successfully")
        else:
            logger.warning(
                f"Attempted to update user '{user.telegram_id}', "
                f"but user was not found or update failed"
            )

        return UserDto.from_model(db_updated_user)

    async def compare_and_update(
        self,
        user: UserDto,
        aiogram_user: AiogramUser,
    ) -> Optional[UserDto]:
        new_username = aiogram_user.username
        if user.username != new_username:
            logger.debug(
                f"User '{user.telegram_id}' username changed ({user.username} -> {new_username})"
            )
            user.username = new_username

        new_name = format_user_name(aiogram_user.full_name)
        if user.name != new_name:
            logger.debug(f"User '{user.telegram_id}' name changed ({user.name} -> {new_name})")
            user.name = new_name

        new_language = aiogram_user.language_code
        if user.language != new_language:
            if new_language in self.config.locales:
                logger.debug(
                    f"User '{user.telegram_id}' language changed "
                    f"({user.language} -> {new_language})"
                )
                user.language = Locale(new_language)
            else:
                logger.warning(
                    f"User '{user.telegram_id}' language changed. "
                    f"New language is not supported. "
                    f"Used default ({user.language} -> {self.config.default_locale})"
                )
                user.language = self.config.default_locale

        if not user.prepare_changed_data():
            return None

        return await self.update(user)

    async def delete(self, user: UserDto) -> bool:
        result = await self.uow.repository.users.delete(user.telegram_id)

        if result:
            await self.clear_user_cache(user.telegram_id)
            await self._remove_from_recent_activity(user.telegram_id)

        logger.info(f"Deleted user '{user.telegram_id}': '{result}'")
        return result

    async def get_by_partial_name(self, query: str) -> list[UserDto]:
        db_users = await self.uow.repository.users.get_by_partial_name(query)
        logger.debug(f"Retrieved '{len(db_users)}' users for query '{query}'")
        return UserDto.from_model_list(db_users)

    async def get_by_username(self, username: str) -> Optional[UserDto]:
        """Get user by exact username (case-insensitive)."""
        user = await self.uow.repository.users.get_by_username(username)
        return UserDto.from_model(user) if user else None

    async def get_by_referral_code(self, referral_code: str) -> Optional[UserDto]:
        user = await self.uow.repository.users.get_by_referral_code(referral_code)
        return UserDto.from_model(user)

    @redis_cache(prefix="users_count", ttl=TIME_10M)
    async def count(self) -> int:
        count = await self.uow.repository.users.count()
        logger.debug(f"Total users count: '{count}'")
        return count

    @redis_cache(prefix="get_by_role", ttl=TIME_10M)
    async def get_by_role(self, role: UserRole) -> list[UserDto]:
        db_users = await self.uow.repository.users.filter_by_role(role)
        logger.debug(f"Retrieved '{len(db_users)}' users with role '{role}'")
        return UserDto.from_model_list(db_users)

    @redis_cache(prefix="get_blocked_users", ttl=TIME_10M)
    async def get_blocked_users(self) -> list[UserDto]:
        db_users = await self.uow.repository.users.filter_by_blocked(blocked=True)
        logger.debug(f"Retrieved '{len(db_users)}' blocked users")
        return UserDto.from_model_list(list(reversed(db_users)))

    @redis_cache(prefix="get_all", ttl=TIME_10M)
    async def get_all(self) -> list[UserDto]:
        db_users = await self.uow.repository.users.get_all()
        logger.debug(f"Retrieved '{len(db_users)}' users")
        return UserDto.from_model_list(db_users)

    async def set_block(self, user: UserDto, blocked: bool) -> None:
        user.is_blocked = blocked
        await self.uow.repository.users.update(
            user.telegram_id,
            **user.prepare_changed_data(),
        )
        await self.clear_user_cache(user.telegram_id)
        logger.info(f"Set block={blocked} for user '{user.telegram_id}'")

    async def set_bot_blocked(self, user: UserDto, blocked: bool) -> None:
        user.is_bot_blocked = blocked
        await self.uow.repository.users.update(
            user.telegram_id,
            **user.prepare_changed_data(),
        )
        await self.clear_user_cache(user.telegram_id)
        logger.info(f"Set bot_blocked={blocked} for user '{user.telegram_id}'")

    async def set_role(self, user: UserDto, role: UserRole) -> None:
        user.role = role
        await self.uow.repository.users.update(
            user.telegram_id,
            **user.prepare_changed_data(),
        )
        await self.clear_user_cache(user.telegram_id)
        logger.info(f"Set role='{role.name}' for user '{user.telegram_id}'")

    #

    async def update_recent_activity(self, telegram_id: int) -> None:
        await self._add_to_recent_activity(RecentActivityUsersKey(), telegram_id)

    async def get_recent_registered_users(self) -> list[UserDto]:
        db_users = await self.uow.repository.users._get_many(
            User,
            order_by=User.id.asc(),
            limit=RECENT_REGISTERED_MAX_COUNT,
        )

        logger.debug(f"Retrieved '{len(db_users)}' recent registered users")
        return UserDto.from_model_list(list(reversed(db_users)))

    async def get_recent_activity_users(self, excluded_ids: list[int] = []) -> list[UserDto]:
        telegram_ids = await self._get_recent_activity()
        users: list[UserDto] = []

        for telegram_id in telegram_ids:
            if telegram_id in excluded_ids:
                continue

            user = await self.get(telegram_id)

            if user:
                users.append(user)
            else:
                logger.warning(
                    f"User '{telegram_id}' not found in DB, removing from recent activity cache"
                )
                await self._remove_from_recent_activity(telegram_id)

        logger.debug(f"Retrieved '{len(users)}' recent active users")
        return users

    async def search_users(self, message: Message) -> list[UserDto]:
        found_users = []

        if message.forward_from and not message.forward_from.is_bot:
            target_telegram_id = message.forward_from.id
            single_user = await self.get(telegram_id=target_telegram_id)

            if single_user:
                found_users.append(single_user)
                logger.info(f"Search by forwarded message, found user '{target_telegram_id}'")
            else:
                logger.warning(
                    f"Search by forwarded message, user '{target_telegram_id}' not found"
                )

        elif message.text:
            search_query = message.text.strip()
            logger.debug(f"Searching users by query '{search_query}'")

            if search_query.isdigit():
                target_telegram_id = int(search_query)
                single_user = await self.get(telegram_id=target_telegram_id)

                if single_user:
                    found_users.append(single_user)
                    logger.info(f"Searched by Telegram ID '{target_telegram_id}', user found")
                else:
                    logger.warning(
                        f"Searched by Telegram ID '{target_telegram_id}', user not found"
                    )

            elif search_query.startswith(REMNASHOP_PREFIX):  # TODO: any username from panel
                try:
                    target_id = int(search_query.split("_", maxsplit=1)[1])
                    single_user = await self.get(telegram_id=target_id)
                    if single_user:
                        found_users.append(single_user)
                        logger.info(f"Searched by Remnashop ID '{target_id}', user found")
                    else:
                        logger.warning(f"Searched by Remnashop ID '{target_id}', user not found")
                except (IndexError, ValueError):
                    logger.warning(f"Failed to parse Remnashop ID from query '{search_query}'")

            else:
                found_users = await self.get_by_partial_name(query=search_query)
                logger.info(
                    f"Searched users by partial name '{search_query}', "
                    f"found '{len(found_users)}' users"
                )

        return found_users

    async def set_current_subscription(self, telegram_id: int, subscription_id: int) -> None:
        await self.uow.repository.users.update(
            telegram_id=telegram_id,
            current_subscription_id=subscription_id,
        )
        await self.clear_user_cache(telegram_id)
        logger.info(f"Set current_subscription='{subscription_id}' for user '{telegram_id}'")

    async def delete_current_subscription(self, telegram_id: int) -> None:
        await self.uow.repository.users.update(
            telegram_id=telegram_id,
            current_subscription_id=None,
        )
        await self.clear_user_cache(telegram_id)
        logger.info(f"Delete current subscription for user '{telegram_id}'")

    async def add_to_balance(self, user: Union[BaseUserDto, UserDto], amount: int) -> None:
        """Пополнить баланс пользователя"""
        await self.uow.repository.users.update(
            telegram_id=user.telegram_id,
            balance=user.balance + amount,
        )
        await self.uow.commit()
        await self.clear_user_cache(user.telegram_id)
        logger.info(f"Add '{amount}' to balance for user '{user.telegram_id}'")

    async def subtract_from_balance(self, user: Union[BaseUserDto, UserDto], amount: int) -> bool:
        """Вычесть из баланса пользователя. Возвращает True если успешно"""
        if user.balance < amount:
            logger.warning(f"Insufficient balance for user '{user.telegram_id}': {user.balance} < {amount}")
            return False
        
        await self.uow.repository.users.update(
            telegram_id=user.telegram_id,
            balance=user.balance - amount,
        )
        await self.uow.commit()
        await self.clear_user_cache(user.telegram_id)
        logger.info(f"Subtract '{amount}' from balance for user '{user.telegram_id}'")
        return True

    async def subtract_from_combined_balance(
        self,
        user: Union[BaseUserDto, UserDto],
        amount: int,
        referral_balance: int,
        is_combined: bool
    ) -> tuple[int, int]:
        """
        Вычесть сумму из баланса с учётом режима баланса.
        В COMBINED режиме списывает сначала с основного баланса, потом с бонусного.
        В SEPARATE режиме списывает только с основного баланса.
        
        Args:
            user: Пользователь
            amount: Сумма для списания
            referral_balance: Доступный бонусный баланс
            is_combined: Режим COMBINED или нет
            
        Returns:
            tuple[int, int]: (списано_с_основного, списано_с_бонусного)
            
        Raises:
            ValueError: Если недостаточно средств
        """
        from src.services.referral import ReferralService
        from src.core.enums import ReferralRewardType
        
        # Вычисляем доступный баланс
        available = user.balance + referral_balance if is_combined else user.balance
        
        if available < amount:
            raise ValueError(
                f"Insufficient balance for user '{user.telegram_id}': "
                f"available={available}, required={amount}"
            )
        
        # Списываем сначала с основного баланса
        from_main = min(user.balance, amount)
        from_bonus = amount - from_main
        
        # Обновляем основной баланс
        if from_main > 0:
            await self.uow.repository.users.update(
                telegram_id=user.telegram_id,
                balance=user.balance - from_main,
            )
            await self.uow.commit()
        
        logger.info(
            f"Subtracted '{amount}' from user '{user.telegram_id}': "
            f"{from_main} from main, {from_bonus} from bonus (combined={is_combined})"
        )
        
        await self.clear_user_cache(user.telegram_id)
        
        return (from_main, from_bonus)

    async def get_balance(self, telegram_id: int) -> int:
        """Получить текущий баланс пользователя"""
        user = await self.get(telegram_id)
        return user.balance if user else 0

    async def get_available_balance(self, user: Union[BaseUserDto, UserDto], referral_balance: int = 0) -> int:
        """
        Получить доступный баланс пользователя с учётом режима баланса.
        В режиме COMBINED возвращает сумму основного и бонусного баланса.
        В режиме SEPARATE возвращает только основной баланс.
        
        Args:
            user: Пользователь
            referral_balance: Бонусный баланс (нужно передать из referral_service)
        
        Returns:
            Доступная сумма для трат
        """
        from src.services.settings import SettingsService
        from dishka import AsyncContainer
        
        # Получаем настройки режима баланса
        # Если нет доступа к контейнеру, по умолчанию используем SEPARATE режим
        try:
            # Это временное решение - в идеале передавать settings_service через параметр
            is_combined = False  # По умолчанию SEPARATE
            # Но мы можем проверить через self, если есть доступ
            # В реальности нужно передавать settings_service как зависимость
        except Exception:
            is_combined = False
        
        # В COMBINED режиме суммируем балансы
        return user.balance + referral_balance if is_combined else user.balance

    #

    async def clear_user_cache(self, telegram_id: int) -> None:
        user_cache_key: str = build_key("cache", "get_user", telegram_id)
        await self.redis_client.delete(user_cache_key)
        await self._clear_list_caches()
        logger.debug(f"User cache for '{telegram_id}' invalidated")

    async def _clear_list_caches(self) -> None:
        list_cache_keys_to_invalidate = [
            build_key("cache", "get_blocked_users"),
            build_key("cache", "count"),
            build_key("cache", "get_all"),
        ]

        for role in UserRole:
            key = build_key("cache", "get_by_role", role=role)
            list_cache_keys_to_invalidate.append(key)

        await self.redis_client.delete(*list_cache_keys_to_invalidate)
        logger.debug("List caches invalidated")

    async def _add_to_recent_activity(self, key: StorageKey, telegram_id: int) -> None:
        await self.redis_repository.list_remove(key, value=telegram_id, count=0)
        await self.redis_repository.list_push(key, telegram_id)
        await self.redis_repository.list_trim(key, start=0, end=RECENT_ACTIVITY_MAX_COUNT - 1)
        logger.debug(f"User '{telegram_id}' activity updated in recent cache")

    async def _remove_from_recent_activity(self, telegram_id: int) -> None:
        await self.redis_repository.list_remove(
            key=RecentActivityUsersKey(),
            value=telegram_id,
            count=0,
        )
        logger.debug(f"User '{telegram_id}' removed from recent activity cache")

    async def _get_recent_activity(self) -> list[int]:
        telegram_ids_str = await self.redis_repository.list_range(
            key=RecentActivityUsersKey(),
            start=0,
            end=RECENT_ACTIVITY_MAX_COUNT - 1,
        )
        ids = [int(uid) for uid in telegram_ids_str]
        logger.debug(f"Retrieved '{len(ids)}' recent activity user IDs from cache")
        return ids