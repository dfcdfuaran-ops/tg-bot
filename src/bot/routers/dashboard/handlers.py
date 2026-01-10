import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from aiogram.types import CallbackQuery
from aiogram_dialog import DialogManager
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from loguru import logger
from sqlalchemy import ARRAY, JSON, BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, create_engine, select
from sqlalchemy import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateTable

from src.core.constants import BASE_DIR, USER_KEY
from src.core.utils.formatters import format_user_log as log
from src.core.utils.message_payload import MessagePayload
from src.infrastructure.database.models.sql import (
    BaseSql,
    Broadcast,
    BroadcastMessage,
    PaymentGateway,
    Plan,
    PlanDuration,
    PlanPrice,
    Promocode,
    PromocodeActivation,
    Referral,
    ReferralReward,
    Settings,
    Subscription,
    Transaction,
    User,
)
from src.infrastructure.database.models.dto import UserDto
from src.services.notification import NotificationService

# Список всех моделей для экспорта
ALL_MODELS = [
    User,
    Subscription,
    Transaction,
    Plan,
    PlanDuration,
    PlanPrice,
    Referral,
    ReferralReward,
    Promocode,
    PromocodeActivation,
    PaymentGateway,
    Broadcast,
    BroadcastMessage,
    Settings,
]


def create_sqlite_schema(engine) -> None:
    """Создает схему SQLite с преобразованием типов данных PostgreSQL в SQLite-совместимые."""
    from sqlalchemy import text
    
    # Используем raw SQL для создания таблиц, чтобы избежать проблем с форматированием
    with engine.connect() as conn:
        # Users
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL UNIQUE,
                username TEXT,
                referral_code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                language TEXT NOT NULL,
                personal_discount INTEGER NOT NULL,
                purchase_discount INTEGER NOT NULL,
                balance INTEGER NOT NULL,
                is_blocked INTEGER NOT NULL,
                is_bot_blocked INTEGER NOT NULL,
                is_rules_accepted INTEGER NOT NULL,
                current_subscription_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))
        
        # Subscriptions
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_remna_id TEXT NOT NULL,
                user_telegram_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                is_trial INTEGER NOT NULL,
                traffic_limit INTEGER NOT NULL,
                device_limit INTEGER NOT NULL,
                traffic_limit_strategy TEXT NOT NULL,
                tag TEXT,
                internal_squads TEXT NOT NULL,
                external_squad TEXT,
                expire_at TEXT NOT NULL,
                url TEXT NOT NULL,
                plan TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_telegram_id) REFERENCES users(telegram_id)
            )
        """))
        
        # Transactions
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payment_id TEXT NOT NULL UNIQUE,
                user_telegram_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                is_test INTEGER NOT NULL,
                purchase_type TEXT NOT NULL,
                gateway_type TEXT NOT NULL,
                pricing TEXT NOT NULL,
                currency TEXT NOT NULL,
                plan TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_telegram_id) REFERENCES users(telegram_id)
            )
        """))
        
        # Plans
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_index INTEGER NOT NULL,
                is_active INTEGER NOT NULL,
                type TEXT NOT NULL,
                availability TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                tag TEXT,
                traffic_limit INTEGER NOT NULL,
                device_limit INTEGER NOT NULL,
                traffic_limit_strategy TEXT NOT NULL,
                allowed_user_ids TEXT,
                internal_squads TEXT NOT NULL,
                external_squad TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))
        
        # Plan Durations
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS plan_durations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                days INTEGER NOT NULL,
                FOREIGN KEY (plan_id) REFERENCES plans(id)
            )
        """))
        
        # Plan Prices
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS plan_prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_duration_id INTEGER NOT NULL,
                currency TEXT NOT NULL,
                price REAL NOT NULL,
                FOREIGN KEY (plan_duration_id) REFERENCES plan_durations(id)
            )
        """))
        
        # Referrals
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_telegram_id INTEGER NOT NULL,
                referred_telegram_id INTEGER NOT NULL,
                level TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (referrer_telegram_id) REFERENCES users(telegram_id),
                FOREIGN KEY (referred_telegram_id) REFERENCES users(telegram_id)
            )
        """))
        
        # Referral Rewards
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS referral_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referral_id INTEGER,
                user_telegram_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                amount INTEGER NOT NULL,
                is_issued INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (referral_id) REFERENCES referrals(id),
                FOREIGN KEY (user_telegram_id) REFERENCES users(telegram_id)
            )
        """))
        
        # Promocodes
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS promocodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                is_active INTEGER NOT NULL,
                reward_type TEXT NOT NULL,
                reward INTEGER,
                plan TEXT,
                lifetime INTEGER,
                max_activations INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))
        
        # Promocode Activations
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS promocode_activations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                promocode_id INTEGER NOT NULL,
                user_telegram_id INTEGER NOT NULL,
                activated_at TEXT NOT NULL,
                FOREIGN KEY (promocode_id) REFERENCES promocodes(id),
                FOREIGN KEY (user_telegram_id) REFERENCES users(telegram_id)
            )
        """))
        
        # Payment Gateways
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS payment_gateways (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_index INTEGER NOT NULL,
                type TEXT NOT NULL UNIQUE,
                currency TEXT NOT NULL,
                is_active INTEGER NOT NULL,
                settings TEXT
            )
        """))
        
        # Broadcasts
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS broadcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                audience TEXT NOT NULL,
                total_count INTEGER NOT NULL,
                success_count INTEGER NOT NULL,
                failed_count INTEGER NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """))
        
        # Broadcast Messages
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS broadcast_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                broadcast_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                message_id INTEGER,
                status TEXT NOT NULL,
                FOREIGN KEY (broadcast_id) REFERENCES broadcasts(id)
            )
        """))
        
        # Settings
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rules_required INTEGER NOT NULL,
                channel_required INTEGER NOT NULL,
                rules_link TEXT NOT NULL,
                channel_id INTEGER,
                channel_link TEXT NOT NULL,
                access_mode TEXT NOT NULL,
                purchases_allowed INTEGER NOT NULL,
                registration_allowed INTEGER NOT NULL,
                default_currency TEXT NOT NULL,
                user_notifications TEXT NOT NULL,
                system_notifications TEXT NOT NULL,
                referral TEXT NOT NULL
            )
        """))
        
        conn.commit()


@inject
async def on_save_database(
    callback: CallbackQuery,
    widget: Any,
    dialog_manager: DialogManager,
    notification_service: FromDishka[NotificationService],
    session_maker: FromDishka[async_sessionmaker[AsyncSession]],
) -> None:
    """Обработчик для кнопки сохранения базы данных в SQLite файл."""
    user: UserDto = dialog_manager.middleware_data[USER_KEY]
    await callback.answer()
    
    db_path = BASE_DIR / "remna.db"
    
    try:
        logger.info(f"{log(user)} Starting database export to {db_path}")
        
        # Уведомляем пользователя о начале процесса
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-db-export-start"),
        )
        
        # Создаем SQLite движок и сессию
        sqlite_url = f"sqlite:///{db_path}"
        sqlite_engine = create_engine(sqlite_url, echo=False)
        
        # Создаем все таблицы в SQLite с правильными типами
        try:
            create_sqlite_schema(sqlite_engine)
        except Exception as schema_error:
            logger.error(f"{log(user)} Failed to create SQLite schema: {schema_error}", exc_info=True)
            raise
        
        # Создаем синхронную сессию для SQLite
        sqlite_session_maker = sessionmaker(bind=sqlite_engine)
        
        # Экспортируем данные из PostgreSQL в SQLite
        try:
            async with session_maker() as pg_session:
                with sqlite_session_maker() as sqlite_session:
                    await export_data_to_sqlite(pg_session, sqlite_session)
                    sqlite_session.commit()
        except Exception as export_error:
            logger.error(f"{log(user)} Failed to export data: {export_error}", exc_info=True)
            raise
        
        logger.info(f"{log(user)} Database export completed successfully")
        
        # Уведомляем пользователя об успешном завершении
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(
                i18n_key="ntf-db-export-success",
                i18n_kwargs={"path": str(db_path)},
            ),
        )
        
    except Exception as e:
        error_message = str(e)
        # Убираем объекты из сообщения об ошибке
        if "<" in error_message and ">" in error_message:
            # Извлекаем только текст ошибки до первого объекта
            error_message = error_message.split("<")[0].strip()
        # Экранируем фигурные скобки для Fluent
        error_message = error_message.replace("{", "{{").replace("}", "}}")
        logger.error(f"{log(user)} Failed to export database: {e}", exc_info=True)
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(
                i18n_key="ntf-db-export-error",
                i18n_kwargs={"error": error_message[:200]},
            ),
        )


async def export_data_to_sqlite(
    pg_session: AsyncSession,
    sqlite_session: Session,
) -> None:
    """Экспортирует данные из PostgreSQL в SQLite с использованием streaming."""
    BATCH_SIZE = 100  # Обрабатываем по 100 записей за раз для экономии памяти
    
    for model in ALL_MODELS:
        try:
            # Используем streaming для экономии памяти
            result = await pg_session.stream_scalars(select(model))
            
            table = model.__table__
            columns = [col.name for col in table.columns]
            
            record_count = 0
            batch_data = []
            
            async for record in result:
                # Создаем словарь с данными записи
                data = {}
                for col in columns:
                    value = getattr(record, col, None)
                    # Преобразуем значения для SQLite
                    if value is None:
                        data[col] = None
                    elif isinstance(value, UUID):
                        # UUID преобразуем в строку
                        data[col] = str(value)
                    elif isinstance(value, (list, dict)):
                        # Массивы и JSON сохраняем как строки JSON
                        data[col] = json.dumps(value, default=str) if value else None
                    elif isinstance(value, datetime):
                        # datetime преобразуем в ISO формат
                        data[col] = value.isoformat()
                    elif isinstance(value, Decimal):
                        # Decimal преобразуем в float
                        data[col] = float(value)
                    elif hasattr(value, "value"):  # Enum
                        # Enum преобразуем в значение
                        data[col] = value.value if hasattr(value, "value") else str(value)
                    elif not isinstance(value, (int, float, str, bool)):
                        # Другие объекты преобразуем в строку
                        data[col] = str(value)
                    else:
                        data[col] = value
                
                batch_data.append(data)
                record_count += 1
                
                # Вставляем пачками для экономии памяти
                if len(batch_data) >= BATCH_SIZE:
                    for row_data in batch_data:
                        insert_stmt = table.insert().values(**row_data)
                        sqlite_session.execute(insert_stmt)
                    batch_data = []
            
            # Вставляем оставшиеся записи
            if batch_data:
                for row_data in batch_data:
                    insert_stmt = table.insert().values(**row_data)
                    sqlite_session.execute(insert_stmt)
            
            if record_count > 0:
                logger.debug(f"Exported {record_count} records from {model.__tablename__}")
            else:
                logger.debug(f"No records found for {model.__tablename__}")
            
        except Exception as e:
            logger.error(f"Error exporting {model.__tablename__}: {e}", exc_info=True)
            # Продолжаем экспорт других таблиц даже при ошибке

