from typing import Optional
from uuid import UUID

from aiogram import Bot
from fluentogram import TranslatorHub
from loguru import logger
from redis.asyncio import Redis

from src.core.config import AppConfig
from src.core.enums import PlanAvailability
from src.infrastructure.database import UnitOfWork
from src.infrastructure.database.models.dto import PlanDto, UserDto
from src.infrastructure.database.models.sql import Plan, PlanDuration, PlanPrice
from src.infrastructure.redis import RedisRepository

from .base import BaseService


class PlanService(BaseService):
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

    async def sync_plans_squads(self, valid_squad_uuids: set[UUID], default_squad_uuid: UUID) -> dict[str, int]:
        """
        Синхронизирует internal_squads и external_squad планов с доступными squad'ами в панели.
        Если у плана указаны несуществующие squad'ы, они заменяются/удаляются.
        
        Args:
            valid_squad_uuids: Множество UUID существующих squad'ов в панели (INTERNAL squads!)
            default_squad_uuid: UUID squad'а по умолчанию (первый из internal squads панели)
            
        Returns:
            Статистика: {"updated": N, "unchanged": M}
        """
        updated = 0
        unchanged = 0
        
        all_plans = await self.get_all()
        
        for plan in all_plans:
            plan_changed = False
            
            # ========== Проверка internal_squads ==========
            if not plan.internal_squads:
                # У плана нет internal_squads, присваиваем default
                plan.internal_squads = [default_squad_uuid]
                plan_changed = True
                logger.info(
                    f"Plan '{plan.name}' (ID: {plan.id}) had no internal_squads, "
                    f"assigned default squad: {default_squad_uuid}"
                )
            else:
                # Проверяем, все ли internal_squads существуют в панели
                valid_plan_squads = [
                    squad_uuid for squad_uuid in plan.internal_squads 
                    if squad_uuid in valid_squad_uuids
                ]
                
                if len(valid_plan_squads) != len(plan.internal_squads):
                    # Некоторые squad'ы не существуют
                    invalid_squads = [
                        str(squad_uuid) for squad_uuid in plan.internal_squads 
                        if squad_uuid not in valid_squad_uuids
                    ]
                    
                    if valid_plan_squads:
                        # Есть хотя бы один валидный squad
                        plan.internal_squads = valid_plan_squads
                    else:
                        # Все squad'ы невалидные, используем default
                        plan.internal_squads = [default_squad_uuid]
                    
                    plan_changed = True
                    logger.warning(
                        f"Plan '{plan.name}' (ID: {plan.id}) had invalid internal_squads: {invalid_squads}. "
                        f"Updated to: {[str(s) for s in plan.internal_squads]}"
                    )
            
            # ========== Проверка external_squad ==========
            # external_squad ссылается на ВНЕШНЮЮ таблицу external_squads в Remnawave,
            # которую мы не можем проверить через internal_squads API.
            # Очищаем external_squad чтобы избежать foreign key ошибок.
            if plan.external_squad:
                logger.warning(
                    f"Plan '{plan.name}' (ID: {plan.id}) had external_squad: {plan.external_squad}. "
                    f"Clearing it to avoid foreign key constraint errors."
                )
                plan.external_squad = None
                plan_changed = True
            
            # Сохраняем если были изменения
            if plan_changed:
                await self.update(plan)
                updated += 1
            else:
                unchanged += 1
                logger.debug(
                    f"Plan '{plan.name}' (ID: {plan.id}) squads are valid"
                )
        
        logger.info(f"Plans squads sync completed: {updated} updated, {unchanged} unchanged")
        return {"updated": updated, "unchanged": unchanged}

    async def create(self, plan: PlanDto) -> PlanDto:
        order_index = await self.uow.repository.plans.get_max_index()
        order_index = (order_index or 0) + 1
        plan.order_index = order_index

        db_plan = self._dto_to_model(plan)
        db_created_plan = await self.uow.repository.plans.create(db_plan)
        logger.info(f"Created plan '{plan.name}' with ID '{db_created_plan.id}'")
        return PlanDto.from_model(db_created_plan)  # type: ignore[return-value]

    async def get(self, plan_id: int) -> Optional[PlanDto]:
        db_plan = await self.uow.repository.plans.get(plan_id)

        if not db_plan:
            logger.warning(f"Plan '{plan_id}' not found")

        return PlanDto.from_model(db_plan)

    async def get_by_name(self, plan_name: str) -> Optional[PlanDto]:
        db_plan = await self.uow.repository.plans.get_by_name(plan_name)

        if not db_plan:
            logger.warning(f"Plan with name '{plan_name}' not found")

        return PlanDto.from_model(db_plan)

    async def get_by_tag(self, tag: str) -> Optional[PlanDto]:
        db_plan = await self.uow.repository.plans.get_by_tag(tag)

        if not db_plan:
            logger.debug(f"Plan with tag '{tag}' not found")

        return PlanDto.from_model(db_plan)

    async def get_all(self) -> list[PlanDto]:
        db_plans = await self.uow.repository.plans.get_all()
        return PlanDto.from_model_list(db_plans)

    async def update(self, plan: PlanDto) -> Optional[PlanDto]:
        db_plan = self._dto_to_model(plan)
        db_updated_plan = await self.uow.repository.plans.update(db_plan)

        if db_updated_plan:
            logger.info(f"Updated plan '{plan.name}' (ID: '{plan.id}') successfully")
        else:
            logger.warning(
                f"Attempted to update plan '{plan.name}' (ID: '{plan.id}'), "
                "but plan was not found or update failed"
            )

        return PlanDto.from_model(db_updated_plan)

    async def delete(self, plan_id: int) -> bool:
        result = await self.uow.repository.plans.delete(plan_id)

        if result:
            logger.info(f"Plan '{plan_id}' deleted successfully")
        else:
            logger.warning(f"Failed to delete plan '{plan_id}'")

        return result

    async def count(self) -> int:
        return await self.uow.repository.plans.count()

    # ---------------------------------------------------------------------

    async def get_trial_plan(self) -> Optional[PlanDto]:
        """DEPRECATED: Используйте get_appropriate_trial_plan(user)"""
        logger.warning("get_trial_plan() is deprecated")

        db_plans: list[Plan] = await self.uow.repository.plans.filter_by_availability(
            availability=PlanAvailability.TRIAL
        )

        active_plans = [p for p in db_plans if p.is_active]
        if active_plans:
            return PlanDto.from_model(active_plans[0])

        return None

    async def get_appropriate_trial_plan(self, user: UserDto, is_invited: bool = False) -> Optional[PlanDto]:
        """
        Get appropriate trial/invited plan for user to check if they can start a trial subscription.
        Приглашённые пользователи получают INVITED подписку.
        Остальные пользователи получают TRIAL подписку.
        """
        # Если пользователь приглашён - ищем INVITED план
        if is_invited:
            invited_plans: list[Plan] = await self.uow.repository.plans.filter_by_availability(
                availability=PlanAvailability.INVITED
            )
            active_invited = [p for p in invited_plans if p.is_active]
            if active_invited:
                plan = active_invited[0]
                logger.debug(
                    f"Available INVITED plan '{plan.name}' found "
                    f"for invited user '{user.telegram_id}' (for trial eligibility check)"
                )
                return PlanDto.from_model(plan)

        # 🎁 TRIAL - базовая подписка для остальных пользователей
        trial_plans: list[Plan] = await self.uow.repository.plans.filter_by_availability(
            availability=PlanAvailability.TRIAL
        )

        active_trial = [p for p in trial_plans if p.is_active]
        if active_trial:
            plan = active_trial[0]
            logger.debug(
                f"Available TRIAL plan '{plan.name}' found "
                f"for user '{user.telegram_id}' (for trial eligibility check)"
            )
            return PlanDto.from_model(plan)

        logger.warning(
            f"No TRIAL plan found for user '{user.telegram_id}'"
        )
        return None

    async def get_invited_plan(self) -> Optional[PlanDto]:
        """Get the INVITED plan for users who use a referral code."""
        invited_plans: list[Plan] = await self.uow.repository.plans.filter_by_availability(
            availability=PlanAvailability.INVITED
        )

        active_plans = [p for p in invited_plans if p.is_active]
        if active_plans:
            plan = active_plans[0]
            logger.info(f"Selected INVITED plan '{plan.name}'")
            return PlanDto.from_model(plan)

        logger.warning("No active INVITED plan found")
        return None

    # ---------------------------------------------------------------------

    async def get_available_plans(self, user: UserDto) -> list[PlanDto]:
        db_plans: list[Plan] = await self.uow.repository.plans.filter_active(is_active=True)
        result: list[Plan] = []

        for plan in db_plans:
            match plan.availability:
                case PlanAvailability.ALL:
                    result.append(plan)
                case PlanAvailability.NEW if not user.has_any_subscription:
                    result.append(plan)
                case PlanAvailability.EXISTING if user.has_any_subscription:
                    result.append(plan)
                case PlanAvailability.INVITED if user.is_invited_user:
                    result.append(plan)
                case PlanAvailability.ALLOWED if user.telegram_id in plan.allowed_user_ids:
                    result.append(plan)

        return PlanDto.from_model_list(result)

    async def get_allowed_plans(self) -> list[PlanDto]:
        db_plans = await self.uow.repository.plans.filter_by_availability(
            availability=PlanAvailability.ALLOWED,
        )
        return PlanDto.from_model_list(db_plans)

    async def move_plan_up(self, plan_id: int) -> bool:
        db_plans = await self.uow.repository.plans.get_all()
        db_plans.sort(key=lambda p: p.order_index)

        index = next((i for i, p in enumerate(db_plans) if p.id == plan_id), None)
        if index is None:
            return False

        if index == 0:
            db_plans.append(db_plans.pop(0))
        else:
            db_plans[index - 1], db_plans[index] = db_plans[index], db_plans[index - 1]

        for i, plan in enumerate(db_plans, start=1):
            plan.order_index = i

        logger.info(f"Plan '{plan_id}' reorder successfully")
        return True


    def _dto_to_model(self, plan_dto: PlanDto) -> Plan:
        db_plan = Plan(**plan_dto.model_dump(exclude={"durations"}))

        for duration_dto in plan_dto.durations:
            db_duration = PlanDuration(**duration_dto.model_dump(exclude={"prices"}))
            db_plan.durations.append(db_duration)
            db_duration.plan = db_plan

            for price_dto in duration_dto.prices:
                db_price = PlanPrice(**price_dto.model_dump())
                db_duration.prices.append(db_price)
                db_price.plan_duration = db_duration

        return db_plan
