from aiogram_dialog import DialogManager, SubManager
from aiogram_dialog.widgets.kbd import Button
from aiogram.types import CallbackQuery, Message
from dishka import FromDishka
from dishka.integrations.aiogram_dialog import inject
from aiogram import Bot
from redis.asyncio import Redis
import asyncio
import os
import shutil
import json
import sqlite3
import urllib.request
import urllib.error
import subprocess
from datetime import datetime
from loguru import logger
from src.core.constants import USER_KEY
from src.core.utils.message_payload import MessagePayload
from src.core.utils.validators import is_double_click
from src.core.utils.formatters import format_user_log as log
from src.services.notification import NotificationService
from src.infrastructure.taskiq.tasks.importer import sync_bot_to_panel_task
from src.infrastructure.redis.repository import RedisRepository
from fluentogram import TranslatorRunner


async def on_back_to_dashboard(callback: CallbackQuery, button, manager: DialogManager):
    """Обработчик для кнопки 'Назад' - возвращает в предыдущее состояние."""
    from src.bot.states import DashboardDB, Dashboard
    
    # Получаем текущее состояние
    current_state = manager.current_context().state
    
    # Если на странице загрузки, вернуться в главное меню БД
    if current_state == DashboardDB.LOAD:
        await manager.switch_to(DashboardDB.MAIN)
    # Если на главном меню БД, открыть Dashboard
    elif current_state == DashboardDB.MAIN:
        await manager.start(Dashboard.MAIN)


@inject
async def on_save_db(
    callback: CallbackQuery,
    button,
    manager: DialogManager,
    notification_service: FromDishka[NotificationService],
):
    """Обработчик для сохранения дампа базы данных."""
    try:
        user = manager.middleware_data.get(USER_KEY)
        backup_dir = "/opt/remnashop/backups"
        os.makedirs(backup_dir, exist_ok=True)
        
        # Формируем имя файла с датой и временем
        now = datetime.now()
        filename = f"{now.strftime('%d-%m-%y_%H-%M')}.sql"
        filepath = os.path.join(backup_dir, filename)
        
        # Выполняем команду в отдельном потоке
        loop = asyncio.get_event_loop()
        
        def backup_db():
            # Используем pg_dump через прямое подключение к БД в контейнере
            import os as os_module
            import socket
            
            # Получаем данные из переменных окружения
            db_password = os_module.getenv('DATABASE_PASSWORD', 'remnashop')
            db_user = os_module.getenv('DATABASE_USER', 'remnashop')
            db_name = os_module.getenv('DATABASE_NAME', 'remnashop')
            db_host = os_module.getenv('DATABASE_HOST', 'remnashop-db')
            db_port = os_module.getenv('DATABASE_PORT', '5432')
            
            # Формируем команду с параметрами подключения
            # Используем те же флаги, что и в backup_db.sh для полной совместимости
            cmd = [
                'pg_dump',
                '-h', db_host,
                '-p', db_port,
                '-U', db_user,
                '--clean',          # Добавляет DROP команды перед CREATE
                '--if-exists',      # Использует IF EXISTS для DROP
                '--no-owner',       # Не включает владельца объектов
                '--no-acl',         # Не включает права доступа
                db_name
            ]
            
            env = os_module.environ.copy()
            env['PGPASSWORD'] = db_password
            
            result = subprocess.run(cmd, capture_output=True, text=True, env=env)
            
            # Пишем результат в файл
            if result.returncode == 0 and result.stdout:
                with open(filepath, 'w') as f:
                    f.write(result.stdout)
            
            return result
        
        result = await loop.run_in_executor(None, backup_db)
        
        if result.returncode == 0 and os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(i18n_key="ntf-db-save-success"),
            )
        else:
            logger.error(f"Ошибка при создании дампа: returncode={result.returncode}, stderr={result.stderr}")
            # Удаляем пустой файл
            if os.path.exists(filepath):
                os.remove(filepath)
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(i18n_key="ntf-db-save-failed"),
            )
    except Exception as e:
        logger.exception(f"Exception in on_save_db: {e}")
        user = manager.middleware_data.get(USER_KEY)
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-db-save-failed"),
        )


async def on_load_db(callback: CallbackQuery, button, manager: DialogManager):
    from src.bot.states import DashboardDB
    await manager.switch_to(DashboardDB.LOAD)


@inject
async def on_export_db(
    callback: CallbackQuery,
    button,
    manager: DialogManager,
    notification_service: FromDishka[NotificationService],
):
    """Экспорт базы данных PostgreSQL в SQLite файл для просмотра в DB Browser."""
    user = manager.middleware_data.get(USER_KEY)
    
    await notification_service.notify_user(
        user=user,
        payload=MessagePayload(i18n_key="ntf-db-export-start"),
    )
    
    export_dir = "/opt/remnashop/backups/db"
    os.makedirs(export_dir, exist_ok=True)
    sqlite_path = os.path.join(export_dir, "remnashop.db")
    
    # Удаляем старый файл если есть
    if os.path.exists(sqlite_path):
        os.remove(sqlite_path)
    
    loop = asyncio.get_event_loop()
    
    def export_to_sqlite():
        db_password = os.getenv('DATABASE_PASSWORD', 'remnashop')
        db_user = os.getenv('DATABASE_USER', 'remnashop')
        db_name = os.getenv('DATABASE_NAME', 'remnashop')
        db_host = os.getenv('DATABASE_HOST', 'remnashop-db')
        db_port = os.getenv('DATABASE_PORT', '5432')
        
        env = os.environ.copy()
        env['PGPASSWORD'] = db_password
        
        # Создаём SQLite базу данных
        sqlite_conn = sqlite3.connect(sqlite_path)
        sqlite_cursor = sqlite_conn.cursor()
        
        try:
            # Получаем список всех таблиц из PostgreSQL
            tables_cmd = [
                'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', db_name,
                '-t', '-c', "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
            ]
            result = subprocess.run(tables_cmd, capture_output=True, text=True, env=env)
            tables = [t.strip() for t in result.stdout.strip().split('\n') if t.strip()]
            
            logger.info(f"Found {len(tables)} tables to export: {tables}")
            
            for table in tables:
                if not table or table == 'alembic_version':
                    continue
                    
                # Получаем структуру таблицы
                columns_cmd = [
                    'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', db_name,
                    '-t', '-c', f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position;"
                ]
                result = subprocess.run(columns_cmd, capture_output=True, text=True, env=env)
                
                columns = []
                sqlite_columns = []
                for line in result.stdout.strip().split('\n'):
                    if '|' in line:
                        parts = [p.strip() for p in line.split('|')]
                        if len(parts) >= 2:
                            col_name = parts[0]
                            col_type = parts[1]
                            columns.append(col_name)
                            # Преобразуем PostgreSQL типы в SQLite
                            if 'int' in col_type or 'serial' in col_type:
                                sqlite_type = 'INTEGER'
                            elif 'bool' in col_type:
                                sqlite_type = 'INTEGER'
                            elif 'timestamp' in col_type or 'date' in col_type:
                                sqlite_type = 'TEXT'
                            elif 'numeric' in col_type or 'decimal' in col_type or 'float' in col_type or 'double' in col_type:
                                sqlite_type = 'REAL'
                            elif 'uuid' in col_type:
                                sqlite_type = 'TEXT'
                            elif 'json' in col_type:
                                sqlite_type = 'TEXT'
                            elif 'ARRAY' in col_type:
                                sqlite_type = 'TEXT'
                            else:
                                sqlite_type = 'TEXT'
                            sqlite_columns.append(f'"{col_name}" {sqlite_type}')
                
                if not columns:
                    continue
                
                # Создаём таблицу в SQLite
                create_sql = f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(sqlite_columns)})'
                sqlite_cursor.execute(create_sql)
                logger.debug(f"Created table: {table}")
                
                # Получаем данные из PostgreSQL в CSV формате
                columns_quoted = ", ".join([f'"{c}"' for c in columns])
                select_query = f'SELECT {columns_quoted} FROM "{table}";'
                data_cmd = [
                    'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', db_name,
                    '-t', '-A', '-F', '\t',
                    '-c', select_query
                ]
                result = subprocess.run(data_cmd, capture_output=True, text=True, env=env)
                
                # Вставляем данные в SQLite
                rows_inserted = 0
                for line in result.stdout.strip().split('\n'):
                    if not line:
                        continue
                    values = line.split('\t')
                    
                    # Дополняем недостающие поля None (когда последние колонки NULL, psql не выводит разделитель)
                    while len(values) < len(columns):
                        values.append('')
                    
                    # Пропускаем строки с избыточными полями
                    if len(values) > len(columns):
                        logger.warning(f"Row has {len(values)} fields, expected {len(columns)}, skipping")
                        continue
                    
                    # Преобразуем значения
                    processed_values = []
                    for v in values:
                        if v == '' or v == '\\N':
                            processed_values.append(None)
                        elif v == 't':
                            processed_values.append(1)
                        elif v == 'f':
                            processed_values.append(0)
                        else:
                            processed_values.append(v)
                    
                    placeholders = ', '.join(['?' for _ in columns])
                    insert_sql = f'INSERT INTO "{table}" VALUES ({placeholders})'
                    try:
                        sqlite_cursor.execute(insert_sql, processed_values)
                        rows_inserted += 1
                    except Exception as e:
                        logger.warning(f"Error inserting row into {table}: {e}")
                
                logger.info(f"Exported {rows_inserted} rows from table: {table}")
            
            sqlite_conn.commit()
            return True, None
            
        except Exception as e:
            logger.exception(f"Export error: {e}")
            return False, str(e)
        finally:
            sqlite_conn.close()
    
    try:
        success, error_msg = await loop.run_in_executor(None, export_to_sqlite)
        
        if success and os.path.exists(sqlite_path) and os.path.getsize(sqlite_path) > 0:
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(
                    i18n_key="ntf-db-export-success",
                    i18n_kwargs={"path": sqlite_path},
                ),
            )
            logger.info(f"Database exported successfully to {sqlite_path}")
        else:
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(
                    i18n_key="ntf-db-export-error",
                    i18n_kwargs={"error": error_msg or "Unknown error"},
                ),
            )
    except Exception as e:
        logger.exception(f"Export failed: {e}")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(
                i18n_key="ntf-db-export-error",
                i18n_kwargs={"error": str(e)},
            ),
        )


async def on_import_db(callback: CallbackQuery, button, manager: DialogManager):
    await callback.answer("Импорт в разработке.", show_alert=True)


async def on_convert_db(callback: CallbackQuery, button, manager: DialogManager):
    await callback.answer("Функция конвертации пока не реализована.", show_alert=True)


@inject
async def backups_getter(dialog_manager: DialogManager, **kwargs) -> dict:
    """Геттер списка последних бэкапов для меню загрузки."""
    backup_dir = "/opt/remnashop/backups"
    try:
        files = [f for f in os.listdir(backup_dir) if os.path.isfile(os.path.join(backup_dir, f))]
    except Exception:
        files = []

    # сортируем по времени модификации (новые первыми)
    files = sorted(files, key=lambda n: os.path.getmtime(os.path.join(backup_dir, n)), reverse=True)
    items = []
    for idx, name in enumerate(files[:10]):
        items.append({"index": str(idx), "name": name, "path": os.path.join(backup_dir, name)})

    dialog_manager.dialog_data["backups_map"] = {str(idx): item["path"] for idx, item in enumerate(items)}

    return {"backups": items, "has_backups": len(items) > 0}


@inject
async def on_restore_backup(
    callback: CallbackQuery,
    widget: Button,
    sub_manager: SubManager,
    notification_service: FromDishka[NotificationService],
    i18n: FromDishka[TranslatorRunner],
    redis_client: FromDishka[Redis],
):
    # Получаем ID выбранного элемента из SubManager
    selected_index = sub_manager.item_id
    logger.info(f"Selected backup index: {selected_index}")

    user = sub_manager.middleware_data.get(USER_KEY)
    manager = sub_manager.manager

    backups_map = manager.dialog_data.get("backups_map", {})
    local_path = backups_map.get(selected_index)
    if not local_path or not os.path.exists(local_path):
        logger.error(f"Backup file not found: {local_path}")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-db-restore-failed"),
        )
        return

    # Проверка двойного клика для подтверждения операции восстановления
    if is_double_click(manager, key=f"restore_backup_confirm_{selected_index}", cooldown=5):
        logger.info(f"Starting database restore from backup: {local_path}")
    else:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-double-click-confirm"),
        )
        logger.debug(f"{user.username if user else 'Unknown'} Awaiting confirmation to restore backup '{local_path}'")
        return

    # Получаем данные для подключения к БД из переменных окружения
    db_password = os.getenv('DATABASE_PASSWORD', 'remnashop')
    db_user = os.getenv('DATABASE_USER', 'remnashop')
    db_name = os.getenv('DATABASE_NAME', 'remnashop')
    db_host = os.getenv('DATABASE_HOST', 'remnashop-db')
    db_port = os.getenv('DATABASE_PORT', '5432')

    loop = asyncio.get_event_loop()

    # Отправляем начальное уведомление о подготовке к восстановлению
    preparing_notification = await notification_service.notify_user(
        user=user,
        payload=MessagePayload.not_deleted(
            i18n_key="ntf-db-restore-preparing",
            add_close_button=False,
        ),
    )

    def restore_db():
        import re
        env = os.environ.copy()
        env['PGPASSWORD'] = db_password

        # Предобработка дампа: удаление \restrict/\unrestrict строк
        try:
            with open(local_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Удаляем строки \restrict и \unrestrict (защита дампа)
            content = re.sub(r'^\\restrict\s+.*$', '', content, flags=re.MULTILINE)
            content = re.sub(r'^\\unrestrict\s+.*$', '', content, flags=re.MULTILINE)
            
            with open(local_path, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info("Preprocessed dump: removed \\restrict/\\unrestrict lines")
        except Exception as e:
            logger.warning(f"Failed to preprocess dump: {e}")

        # 1. Завершаем все активные соединения к базе
        logger.info("Step 1: Terminating active connections")
        terminate_cmd = [
            'psql',
            '-h', db_host,
            '-p', db_port,
            '-U', db_user,
            '-d', 'postgres',
            '-c', f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();"
        ]
        subprocess.run(terminate_cmd, capture_output=True, text=True, env=env)

        # 2. Очистка базы - удаляем схему и создаём заново
        logger.info("Step 2: Dropping and recreating schema")
        drop_cmd = [
            'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', db_name,
            '-c', 'DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO public;'
        ]
        result_drop = subprocess.run(drop_cmd, capture_output=True, text=True, env=env)
        if result_drop.returncode != 0:
            logger.error(f"Failed to drop schema: {result_drop.stderr}")
            return False, f"Drop schema failed: {result_drop.stderr}"
        
        # 3. Восстановление базы данных из дампа
        logger.info(f"Step 3: Restoring database from backup: {local_path}")
        
        restore_cmd = [
            'psql',
            '-h', db_host,
            '-p', db_port,
            '-U', db_user,
            '-d', db_name,
            '-f', local_path
        ]
        result_restore = subprocess.run(restore_cmd, capture_output=True, text=True, env=env)
        
        if result_restore.returncode != 0:
            logger.warning(f"Restore completed with warnings: {result_restore.stderr}")
        logger.info("Database restored successfully")

        return True, None

    try:
        success, error_msg = await loop.run_in_executor(None, restore_db)

        if success:
            # Очистка всего Redis кэша после восстановления базы
            logger.info("Step 3: Clearing Redis cache after database restore")
            cache_keys = await redis_client.keys("cache:*")
            if cache_keys:
                await redis_client.delete(*cache_keys)
                logger.info(f"Cleared {len(cache_keys)} cache keys")
            
            # Применяем миграции базы данных
            logger.info("Step 4: Applying database migrations after restore")
            def apply_migrations():
                import subprocess
                result = subprocess.run(
                    ["alembic", "-c", "src/infrastructure/database/alembic.ini", "upgrade", "head"],
                    capture_output=True,
                    text=True,
                    cwd="/opt/remnashop"
                )
                if result.returncode != 0:
                    logger.error(f"Migration failed: {result.stderr}")
                    return False
                logger.info("Migrations applied successfully")
                return True
            
            migrations_success = await loop.run_in_executor(None, apply_migrations)
            if not migrations_success:
                # Удаляем уведомление о подготовке при ошибке
                if preparing_notification:
                    await preparing_notification.delete()
                await notification_service.notify_user(
                    user=user,
                    payload=MessagePayload(i18n_key="ntf-db-restore-failed"),
                )
                return
            
            # Удаляем уведомление о подготовке перед показом уведомления о синхронизации
            if preparing_notification:
                await preparing_notification.delete()
            
            # Запускаем синхронизацию данных из бота в панель Remnawave
            logger.info("Step 5: Starting sync from bot to Remnawave panel")
            sync_notification = await notification_service.notify_user(
                user=user,
                payload=MessagePayload.not_deleted(
                    i18n_key="ntf-importer-sync-started",
                    add_close_button=False,
                ),
            )
            
            try:
                task = await sync_bot_to_panel_task.kiq()
                result = await task.wait_result()
                sync_result = result.return_value
                
                if sync_notification:
                    await sync_notification.delete()
                
                if sync_result:
                    logger.info(f"Sync completed: {sync_result}")
                    
                    # Формируем подробное уведомление с результатами синхронизации
                    total = sync_result.get('total_bot_users', 0)
                    created = sync_result.get('created', 0)
                    updated = sync_result.get('updated', 0)
                    skipped = sync_result.get('skipped', 0)
                    errors = sync_result.get('errors', 0)
                    error_users = sync_result.get('error_users', {})
                    skipped_users = sync_result.get('skipped_users', [])
                    
                    logger.info(f"Preparing to send sync report: total={total}, created={created}, updated={updated}, skipped={skipped}, errors={errors}")
                    
                    # Формируем единое сообщение со всей статистикой
                    sync_message = "✅ <b>Восстановление завершено!</b>\n\n"
                    
                    # Раздел пропущенных пользователей
                    if skipped_users and skipped > 0:
                        sync_message += "<b>⊘ Пропущены пользователи без подписок:</b>\n"
                        sync_message += "<blockquote>"
                        for user_info in skipped_users:
                            sync_message += f"• {user_info}\n"
                        sync_message += "</blockquote>"
                    
                    # Раздел ошибок
                    if error_users:
                        if skipped_users and skipped > 0:
                            sync_message += "\n"
                        sync_message += "<b>❌ Ошибки синхронизации:</b>\n"
                        sync_message += "<blockquote>"
                        for user_info, error_reason in error_users.items():
                            sync_message += f"• {user_info}\n  {error_reason}\n\n"
                        sync_message += "</blockquote>"
                    
                    # Раздел итого
                    if error_users or (skipped_users and skipped > 0):
                        sync_message += "\n"
                    sync_message += "<b>📊 Итого:</b>\n"
                    sync_message += "<blockquote>"
                    sync_message += f"Всего в боте: {total}\n"
                    sync_message += f"Создано: {created}\n"
                    sync_message += f"Обновлено: {updated}\n"
                    sync_message += f"Пропущено: {skipped}\n"
                    sync_message += f"Ошибок: {errors}"
                    sync_message += "</blockquote>"
                    
                    # Отправляем единое сообщение
                    await notification_service.notify_user(
                        user=user,
                        payload=MessagePayload(
                            text=sync_message,
                            add_close_button=True,
                            auto_delete_after=None,
                        ),
                    )
                    
                    logger.info("Sync report notification sent")
                else:
                    logger.warning("Sync returned no results")
            except Exception as sync_error:
                logger.exception(f"Sync with panel failed: {sync_error}")
                if sync_notification:
                    await sync_notification.delete()
                
                error_message = f"❌ Ошибка синхронизации: {str(sync_error)}"
                await notification_service.notify_user(
                    user=user,
                    payload=MessagePayload(text=error_message, add_close_button=True, auto_delete_after=None),
                )

            from src.bot.states import Dashboard
            await manager.start(Dashboard.MAIN)
        else:
            logger.error(f"Restore from backup failed: {error_msg}")
            # Удаляем уведомление о подготовке при ошибке
            if preparing_notification:
                await preparing_notification.delete()
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(i18n_key="ntf-db-restore-failed"),
            )
    except Exception as e:
        logger.exception(f"Restore from backup failed: {e}")
        # Удаляем уведомление о подготовке при ошибке
        if preparing_notification:
            await preparing_notification.delete()
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-db-restore-failed"),
        )


@inject
async def on_db_file_input(
    message: Message,
    widget,
    dialog_manager: DialogManager,
    bot: FromDishka[Bot],
    notification_service: FromDishka[NotificationService],
    redis_client: FromDishka[Redis],
):
    # Обработка загруженного файла дампа: сохраняем в ./backups и восстанавливаем
    dialog_manager.show_mode = None
    user = dialog_manager.middleware_data.get(USER_KEY)

    document = message.document
    if not document:
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-importer-not-file"),
        )
        return

    backup_dir = "/opt/remnashop/backups"
    os.makedirs(backup_dir, exist_ok=True)
    local_file_path = os.path.join(backup_dir, document.file_name)

    file = await bot.get_file(document.file_id)
    if not file.file_path:
        logger.error(f"File path not found for document '{document.file_name}'")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-importer-db-failed"),
        )
        return

    try:
        await bot.download_file(file.file_path, destination=local_file_path)
        logger.info(f"Received DB dump: {local_file_path}")

        # Получаем данные для подключения к БД из переменных окружения
        db_password = os.getenv('DATABASE_PASSWORD', 'remnashop')
        db_user = os.getenv('DATABASE_USER', 'remnashop')
        db_name = os.getenv('DATABASE_NAME', 'remnashop')
        db_host = os.getenv('DATABASE_HOST', 'remnashop-db')
        db_port = os.getenv('DATABASE_PORT', '5432')

        loop = asyncio.get_event_loop()

        # Отправляем начальное уведомление о подготовке к восстановлению
        preparing_notification = await notification_service.notify_user(
            user=user,
            payload=MessagePayload.not_deleted(
                i18n_key="ntf-db-restore-preparing",
                add_close_button=False,
            ),
        )

        def restore_db():
            import re
            env = os.environ.copy()
            env['PGPASSWORD'] = db_password

            # Предобработка дампа: удаление \restrict/\unrestrict строк
            try:
                with open(local_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Удаляем строки \restrict и \unrestrict (защита дампа)
                content = re.sub(r'^\\restrict\s+.*$', '', content, flags=re.MULTILINE)
                content = re.sub(r'^\\unrestrict\s+.*$', '', content, flags=re.MULTILINE)
                
                with open(local_file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info("Preprocessed dump: removed \\restrict/\\unrestrict lines")
            except Exception as e:
                logger.warning(f"Failed to preprocess dump: {e}")

            # Завершаем все активные соединения к базе
            terminate_cmd = [
                'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', 'postgres',
                '-c', f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();"
            ]
            subprocess.run(terminate_cmd, capture_output=True, text=True, env=env)

            # Очистка базы - удаляем схему и создаём заново
            drop_cmd = [
                'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', db_name,
                '-c', 'DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public; GRANT ALL ON SCHEMA public TO public;'
            ]
            result_drop = subprocess.run(drop_cmd, capture_output=True, text=True, env=env)
            if result_drop.returncode != 0:
                logger.error(f"Failed to drop schema: {result_drop.stderr}")
                return False, f"Drop schema failed: {result_drop.stderr}"

            # Восстановление из дампа
            restore_cmd = [
                'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', db_name,
                '-f', local_file_path
            ]
            result_restore = subprocess.run(restore_cmd, capture_output=True, text=True, env=env)
            if result_restore.returncode != 0:
                logger.warning(f"Restore completed with warnings: {result_restore.stderr}")

            return True, None

        success, error_msg = await loop.run_in_executor(None, restore_db)

        if success:
            # Очистка Redis кэша
            cache_keys = await redis_client.keys("cache:*")
            if cache_keys:
                await redis_client.delete(*cache_keys)
                logger.info(f"Cleared {len(cache_keys)} cache keys")

            # Применяем миграции базы данных
            logger.info("Applying database migrations after restore")
            def apply_migrations():
                import subprocess
                result = subprocess.run(
                    ["alembic", "-c", "src/infrastructure/database/alembic.ini", "upgrade", "head"],
                    capture_output=True,
                    text=True,
                    cwd="/opt/remnashop"
                )
                if result.returncode != 0:
                    logger.error(f"Migration failed: {result.stderr}")
                    return False
                logger.info("Migrations applied successfully")
                return True
            
            migrations_success = await loop.run_in_executor(None, apply_migrations)
            if not migrations_success:
                # Удаляем уведомление о подготовке при ошибке
                if preparing_notification:
                    await preparing_notification.delete()
                await notification_service.notify_user(
                    user=user,
                    payload=MessagePayload(i18n_key="ntf-db-restore-failed"),
                )
                return

            # Удаляем уведомление о подготовке перед показом уведомления о синхронизации
            if preparing_notification:
                await preparing_notification.delete()

            # Запускаем синхронизацию данных
            sync_notification = await notification_service.notify_user(
                user=user,
                payload=MessagePayload.not_deleted(
                    i18n_key="ntf-importer-sync-started",
                    add_close_button=False,
                ),
            )

            sync_result = None
            try:
                task = await sync_bot_to_panel_task.kiq()
                result = await task.wait_result()
                sync_result = result.return_value

                if sync_notification:
                    await sync_notification.delete()

                if sync_result:
                    logger.info(f"Sync completed: {sync_result}")
                    
                    # Формируем подробное уведомление с результатами синхронизации
                    total = sync_result.get('total_bot_users', 0)
                    created = sync_result.get('created', 0)
                    updated = sync_result.get('updated', 0)
                    skipped = sync_result.get('skipped', 0)
                    errors = sync_result.get('errors', 0)
                    error_users = sync_result.get('error_users', {})
                    skipped_users = sync_result.get('skipped_users', [])
                    
                    logger.info(f"Preparing to send sync report: total={total}, created={created}, updated={updated}, skipped={skipped}, errors={errors}")
                    
                    # Формируем единое сообщение со всей статистикой
                    sync_message = "✅ <b>Восстановление завершено!</b>\n\n"
                    
                    # Раздел пропущенных пользователей
                    if skipped_users and skipped > 0:
                        sync_message += "<b>⊘ Пропущены пользователи без подписок:</b>\n"
                        sync_message += "<blockquote>"
                        for user_info in skipped_users:
                            sync_message += f"• {user_info}\n"
                        sync_message += "</blockquote>"
                    
                    # Раздел ошибок
                    if error_users:
                        if skipped_users and skipped > 0:
                            sync_message += "\n"
                        sync_message += "<b>❌ Ошибки синхронизации:</b>\n"
                        sync_message += "<blockquote>"
                        for user_info, error_reason in error_users.items():
                            sync_message += f"• {user_info}\n  {error_reason}\n\n"
                        sync_message += "</blockquote>"
                    
                    # Раздел итого
                    if error_users or (skipped_users and skipped > 0):
                        sync_message += "\n"
                    sync_message += "<b>📊 Итого:</b>\n"
                    sync_message += "<blockquote>"
                    sync_message += f"Всего в боте: {total}\n"
                    sync_message += f"Создано: {created}\n"
                    sync_message += f"Обновлено: {updated}\n"
                    sync_message += f"Пропущено: {skipped}\n"
                    sync_message += f"Ошибок: {errors}"
                    sync_message += "</blockquote>"
                    
                    # Отправляем единое сообщение
                    await notification_service.notify_user(
                        user=user,
                        payload=MessagePayload(
                            text=sync_message,
                            add_close_button=True,
                            auto_delete_after=None,
                        ),
                    )
                    
                    logger.info("Sync report notification sent")
            except Exception as sync_error:
                logger.exception(f"Sync with panel failed: {sync_error}")
                if sync_notification:
                    await sync_notification.delete()
                
                error_message = f"❌ Ошибка синхронизации: {str(sync_error)}"
                await notification_service.notify_user(
                    user=user,
                    payload=MessagePayload(text=error_message, add_close_button=True, auto_delete_after=None),
                )

            from src.bot.states import Dashboard
            await dialog_manager.start(Dashboard.MAIN)
        else:
            # Удаляем уведомление о подготовке при ошибке
            if preparing_notification:
                await preparing_notification.delete()
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(i18n_key="ntf-db-restore-failed"),
            )
    except Exception as e:
        logger.exception("Restore failed")
        # Удаляем уведомление о подготовке при ошибке
        if preparing_notification:
            await preparing_notification.delete()
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-db-restore-failed"),
        )


@inject
async def on_delete_backup(
    callback: CallbackQuery,
    widget: Button,
    sub_manager: SubManager,
    notification_service: FromDishka[NotificationService],
):
    """Удаление выбранного файла бэкапа."""
    selected_index = sub_manager.item_id
    logger.info(f"Deleting backup with index: {selected_index}")

    user = sub_manager.middleware_data.get(USER_KEY)
    manager = sub_manager.manager

    backups_map = manager.dialog_data.get("backups_map", {})
    local_path = backups_map.get(selected_index)
    
    if not local_path or not os.path.exists(local_path):
        logger.error(f"Backup file not found: {local_path}")
        await callback.answer("Файл не найден", show_alert=True)
        return

    try:
        os.remove(local_path)
        logger.info(f"Backup file deleted: {local_path}")
        await callback.answer("Бэкап удален", show_alert=False)
        
        # Обновляем окно чтобы отобразить изменения
        from src.bot.states import DashboardDB
        await manager.switch_to(DashboardDB.LOAD)
    except Exception as e:
        logger.exception(f"Failed to delete backup: {e}")
        await callback.answer("Ошибка удаления", show_alert=True)


@inject
async def on_export_backup_to_db(
    callback: CallbackQuery,
    widget: Button,
    sub_manager: SubManager,
    notification_service: FromDishka[NotificationService],
    bot: FromDishka[Bot],
):
    """Конвертация выбранного бэкапа в SQLite и отправка в Telegram."""
    selected_index = sub_manager.item_id
    logger.info(f"Exporting backup with index: {selected_index}")

    user = sub_manager.middleware_data.get(USER_KEY)
    manager = sub_manager.manager

    backups_map = manager.dialog_data.get("backups_map", {})
    backup_path = backups_map.get(selected_index)
    
    if not backup_path or not os.path.exists(backup_path):
        logger.error(f"Backup file not found: {backup_path}")
        await callback.answer("Файл не найден", show_alert=True)
        return
    
    # Убираем всплывающее уведомление
    await callback.answer()
    
    # Отправляем сообщение о конвертации
    status_msg = await bot.send_message(
        chat_id=user.telegram_id,
        text="⚠️ Происходит конвертация в SQL",
    )
    
    export_dir = "/opt/remnashop/backups/db"
    os.makedirs(export_dir, exist_ok=True)
    
    # Используем фиксированное имя для sqlite файла
    sqlite_path = os.path.join(export_dir, "sql_convert.db")
    
    # Удаляем старый файл если есть
    if os.path.exists(sqlite_path):
        os.remove(sqlite_path)
    
    loop = asyncio.get_event_loop()
    
    def export_backup_to_sqlite():
        db_password = os.getenv('DATABASE_PASSWORD', 'remnashop')
        db_user = os.getenv('DATABASE_USER', 'remnashop')
        db_name = os.getenv('DATABASE_NAME', 'remnashop')
        db_host = os.getenv('DATABASE_HOST', 'remnashop-db')
        db_port = os.getenv('DATABASE_PORT', '5432')
        
        env = os.environ.copy()
        env['PGPASSWORD'] = db_password
        
        # Создаём временную базу для восстановления бэкапа
        temp_db_name = f"temp_export_{selected_index}"
        
        try:
            # Создаём временную БД
            create_db_cmd = [
                'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', 'postgres',
                '-c', f'DROP DATABASE IF EXISTS {temp_db_name};'
            ]
            subprocess.run(create_db_cmd, capture_output=True, text=True, env=env)
            
            create_db_cmd = [
                'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', 'postgres',
                '-c', f'CREATE DATABASE {temp_db_name};'
            ]
            result = subprocess.run(create_db_cmd, capture_output=True, text=True, env=env)
            if result.returncode != 0:
                return False, f"Failed to create temp DB: {result.stderr}"
            
            # Восстанавливаем бэкап во временную БД
            with open(backup_path, 'r') as f:
                restore_cmd = [
                    'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', temp_db_name
                ]
                result = subprocess.run(restore_cmd, stdin=f, capture_output=True, text=True, env=env)
                if result.returncode != 0:
                    logger.warning(f"Restore warnings: {result.stderr}")
            
            # Создаём SQLite базу данных
            sqlite_conn = sqlite3.connect(sqlite_path)
            sqlite_cursor = sqlite_conn.cursor()
            
            try:
                # Получаем список всех таблиц
                tables_cmd = [
                    'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', temp_db_name,
                    '-t', '-c', "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
                ]
                result = subprocess.run(tables_cmd, capture_output=True, text=True, env=env)
                tables = [t.strip() for t in result.stdout.strip().split('\n') if t.strip()]
                
                for table in tables:
                    if not table or table == 'alembic_version':
                        continue
                        
                    # Получаем структуру таблицы
                    columns_cmd = [
                        'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', temp_db_name,
                        '-t', '-c', f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table}' ORDER BY ordinal_position;"
                    ]
                    result = subprocess.run(columns_cmd, capture_output=True, text=True, env=env)
                    
                    columns = []
                    sqlite_columns = []
                    for line in result.stdout.strip().split('\n'):
                        if '|' in line:
                            parts = [p.strip() for p in line.split('|')]
                            if len(parts) >= 2:
                                col_name = parts[0]
                                col_type = parts[1]
                                columns.append(col_name)
                                # Преобразуем PostgreSQL типы в SQLite
                                if 'int' in col_type or 'serial' in col_type:
                                    sqlite_type = 'INTEGER'
                                elif 'bool' in col_type:
                                    sqlite_type = 'INTEGER'
                                elif 'timestamp' in col_type or 'date' in col_type:
                                    sqlite_type = 'TEXT'
                                elif 'numeric' in col_type or 'decimal' in col_type or 'float' in col_type or 'double' in col_type:
                                    sqlite_type = 'REAL'
                                elif 'uuid' in col_type:
                                    sqlite_type = 'TEXT'
                                elif 'json' in col_type:
                                    sqlite_type = 'TEXT'
                                elif 'ARRAY' in col_type:
                                    sqlite_type = 'TEXT'
                                else:
                                    sqlite_type = 'TEXT'
                                sqlite_columns.append(f'"{col_name}" {sqlite_type}')
                    
                    if not columns:
                        continue
                    
                    # Создаём таблицу в SQLite
                    create_sql = f'CREATE TABLE IF NOT EXISTS "{table}" ({", ".join(sqlite_columns)})'
                    sqlite_cursor.execute(create_sql)
                    
                    # Получаем данные из PostgreSQL
                    columns_quoted = ", ".join([f'"{c}"' for c in columns])
                    select_query = f'SELECT {columns_quoted} FROM "{table}";'
                    data_cmd = [
                        'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', temp_db_name,
                        '-t', '-A', '-F', '\t',
                        '-c', select_query
                    ]
                    result = subprocess.run(data_cmd, capture_output=True, text=True, env=env)
                    
                    # Вставляем данные в SQLite
                    for line in result.stdout.strip().split('\n'):
                        if not line:
                            continue
                        values = line.split('\t')
                        
                        # Дополняем недостающие поля None (когда последние колонки NULL, psql не выводит разделитель)
                        while len(values) < len(columns):
                            values.append('')
                        
                        # Пропускаем строки с избыточными полями
                        if len(values) > len(columns):
                            logger.warning(f"Row has {len(values)} fields, expected {len(columns)}, skipping")
                            continue
                        
                        processed_values = []
                        for v in values:
                            if v == '' or v == '\\N':
                                processed_values.append(None)
                            elif v == 't':
                                processed_values.append(1)
                            elif v == 'f':
                                processed_values.append(0)
                            else:
                                processed_values.append(v)
                        
                        placeholders = ', '.join(['?' for _ in columns])
                        insert_sql = f'INSERT INTO "{table}" VALUES ({placeholders})'
                        try:
                            sqlite_cursor.execute(insert_sql, processed_values)
                        except Exception as e:
                            logger.warning(f"Error inserting row into {table}: {e}")
                
                sqlite_conn.commit()
                return True, None
                
            finally:
                sqlite_conn.close()
                # Удаляем временную БД
                drop_db_cmd = [
                    'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', 'postgres',
                    '-c', f'DROP DATABASE IF EXISTS {temp_db_name};'
                ]
                subprocess.run(drop_db_cmd, capture_output=True, text=True, env=env)
                
        except Exception as e:
            logger.exception(f"Export backup error: {e}")
            # Очистка временной БД в случае ошибки
            drop_db_cmd = [
                'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', 'postgres',
                '-c', f'DROP DATABASE IF EXISTS {temp_db_name};'
            ]
            subprocess.run(drop_db_cmd, capture_output=True, text=True, env=env)
            return False, str(e)
    
    try:
        success, error_msg = await loop.run_in_executor(None, export_backup_to_sqlite)
        
        if success and os.path.exists(sqlite_path) and os.path.getsize(sqlite_path) > 0:
            # Удаляем сообщение о конвертации
            try:
                await status_msg.delete()
            except Exception:
                pass
            
            # Отправляем файл с кнопкой закрытия
            from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
            
            db_file = FSInputFile(sqlite_path, filename="sql_convert.db")
            
            # Создаем кнопку "Закрыть" с крестиком
            close_button = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Закрыть", callback_data="delete_message")]
            ])
            
            await bot.send_document(
                chat_id=user.telegram_id,
                document=db_file,
                caption="✅ Файл был сконвертирован!",
                reply_markup=close_button
            )
            logger.info(f"Backup exported and sent to Telegram: {sqlite_path}")
        else:
            try:
                await status_msg.delete()
            except Exception:
                pass
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(
                    i18n_key="ntf-db-export-error",
                    i18n_kwargs={"error": error_msg or "Unknown error"},
                ),
            )
    except Exception as e:
        logger.exception(f"Export backup failed: {e}")
        # Удаляем сообщение о конвертации в случае ошибки
        try:
            await status_msg.delete()
        except:
            pass
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(
                i18n_key="ntf-db-export-error",
                i18n_kwargs={"error": str(e)},
            ),
        )


async def sync_getter(dialog_manager: DialogManager, **kwargs):
    """Getter для окна процесса синхронизации."""
    return {
        "sync_status": dialog_manager.dialog_data.get("sync_status", "waiting"),
        "sync_result": dialog_manager.dialog_data.get("sync_result", ""),
    }


@inject
async def on_sync_manage(
    callback: CallbackQuery,
    button,
    manager: DialogManager,
    notification_service: FromDishka[NotificationService],
):
    """
    Placeholder для функции управления синхронизацией.
    """
    await notification_service.notify_user(
        user=callback.from_user,
        payload=MessagePayload(text="Находится в разработке..."),
    )


@inject
async def on_sync_from_bot(
    callback: CallbackQuery,
    button,
    manager: DialogManager,
    notification_service: FromDishka[NotificationService],
    redis_repository: FromDishka[RedisRepository],
):
    """
    Синхронизация: данные из бота -> панель Remnawave.
    - Создаёт новых пользователей в панели если их нет
    - Обновляет существующих с приоритетом данных из бота
    """
    from src.core.storage.keys import SyncRunningKey
    from src.infrastructure.taskiq.tasks.importer import sync_bot_to_panel_task
    from src.core.utils.validators import is_double_click
    
    user = manager.middleware_data.get(USER_KEY)
    key = SyncRunningKey()

    # Проверяем, не запущена ли уже синхронизация
    if await redis_repository.get(key, bool, False):
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-importer-sync-already-running"),
        )
        return

    # Требуем двойной клик для подтверждения
    if is_double_click(manager, key="sync_from_bot_confirm", cooldown=5):
        await redis_repository.set(key, value=True, ex=3600)

        # Шаг 1: Подготовка данных
        preparing_notification = await notification_service.notify_user(
            user=user,
            payload=MessagePayload.not_deleted(
                i18n_key="ntf-remnawave-sync-preparing",
                add_close_button=False,
            ),
        )

        try:
            # Удаляем уведомление о подготовке
            if preparing_notification:
                await preparing_notification.delete()
            
            # Шаг 2: Синхронизация данных
            sync_notification = await notification_service.notify_user(
                user=user,
                payload=MessagePayload.not_deleted(
                    i18n_key="ntf-remnawave-sync-started",
                    add_close_button=False,
                ),
            )

            # Запускаем задачу синхронизации и ждём результат
            task = await sync_bot_to_panel_task.kiq()
            result = await task.wait_result()
            sync_result = result.return_value

            # Удаляем уведомление о синхронизации
            if sync_notification:
                await sync_notification.delete()

            if not sync_result:
                await notification_service.notify_user(
                    user=user,
                    payload=MessagePayload(
                        i18n_key="ntf-remnawave-sync-no-users",
                        add_close_button=True,
                    ),
                )
                return

            # Шаг 3: Показываем уведомление с результатами и кнопкой "Закрыть"
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(
                    i18n_key="ntf-remnawave-sync-bot-to-panel-completed",
                    i18n_kwargs={
                        "total_bot_users": sync_result.get("total_bot_users", 0),
                        "created": sync_result.get("created", 0),
                        "updated": sync_result.get("updated", 0),
                        "skipped": sync_result.get("skipped", 0),
                        "errors": sync_result.get("errors", 0),
                    },
                    add_close_button=True,
                ),
            )
            
            logger.info(f"{log(user)} Sync bot to panel completed: {sync_result}")
            
        except Exception as e:
            logger.exception(f"Sync bot to panel failed: {e}")
            if preparing_notification:
                try:
                    await preparing_notification.delete()
                except Exception:
                    pass
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(
                    i18n_key="ntf-remnawave-sync-failed",
                    i18n_kwargs={"error": str(e)},
                    add_close_button=True,
                ),
            )
        finally:
            # Снимаем блокировку
            await redis_repository.delete(key)
        
        return

    # Первый клик - показываем уведомление с просьбой нажать еще раз
    await notification_service.notify_user(
        user=user,
        payload=MessagePayload(i18n_key="ntf-remnawave-sync-confirm"),
    )


@inject
async def on_sync_from_panel(
    callback: CallbackQuery,
    button,
    manager: DialogManager,
    notification_service: FromDishka[NotificationService],
    redis_repository: FromDishka[RedisRepository],
):
    """
    Синхронизация: данные из панели Remnawave -> бот.
    - Создаёт новых пользователей в боте если их нет
    - Обновляет существующих с приоритетом данных из панели
    """
    from src.core.storage.keys import SyncRunningKey
    from src.infrastructure.taskiq.tasks.sync import sync_panel_to_bot_task
    from src.core.utils.validators import is_double_click
    
    user = manager.middleware_data.get(USER_KEY)
    key = SyncRunningKey()

    # Проверяем, не запущена ли уже синхронизация
    if await redis_repository.get(key, bool, False):
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(i18n_key="ntf-importer-sync-already-running"),
        )
        return

    # Требуем двойной клик для подтверждения
    if is_double_click(manager, key="sync_from_panel_confirm", cooldown=5):
        await redis_repository.set(key, value=True, ex=3600)

        # Шаг 1: Подготовка данных
        preparing_notification = await notification_service.notify_user(
            user=user,
            payload=MessagePayload.not_deleted(
                i18n_key="ntf-remnawave-sync-preparing",
                add_close_button=False,
            ),
        )

        try:
            # Удаляем уведомление о подготовке
            if preparing_notification:
                await preparing_notification.delete()
            
            # Шаг 2: Синхронизация данных
            sync_notification = await notification_service.notify_user(
                user=user,
                payload=MessagePayload.not_deleted(
                    i18n_key="ntf-remnawave-sync-started",
                    add_close_button=False,
                ),
            )

            # Запускаем задачу синхронизации и ждём результат
            task = await sync_panel_to_bot_task.kiq(user.telegram_id)
            result = await task.wait_result()
            sync_result = result.return_value

            # Удаляем уведомление о синхронизации
            if sync_notification:
                await sync_notification.delete()

            if not sync_result:
                await notification_service.notify_user(
                    user=user,
                    payload=MessagePayload(
                        i18n_key="ntf-remnawave-sync-no-users",
                        add_close_button=True,
                    ),
                )
                return

            # Шаг 3: Показываем уведомление с результатами и кнопкой "Закрыть"
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(
                    i18n_key="ntf-remnawave-sync-panel-to-bot-completed",
                    i18n_kwargs={
                        "total_panel_users": sync_result.get("total_panel_users", 0),
                        "created": sync_result.get("created", 0),
                        "synced": sync_result.get("synced", 0),
                        "skipped": sync_result.get("skipped", 0),
                        "errors": sync_result.get("errors", 0),
                    },
                    add_close_button=True,
                ),
            )
            
            logger.info(f"{log(user)} Sync panel to bot completed: {sync_result}")
            
        except Exception as e:
            logger.exception(f"Sync panel to bot failed: {e}")
            if preparing_notification:
                try:
                    await preparing_notification.delete()
                except Exception:
                    pass
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(
                    i18n_key="ntf-remnawave-sync-failed",
                    i18n_kwargs={"error": str(e)},
                    add_close_button=True,
                ),
            )
        finally:
            # Снимаем блокировку
            await redis_repository.delete(key)
        
        return

    # Первый клик - показываем уведомление с просьбой нажать еще раз
    await notification_service.notify_user(
        user=user,
        payload=MessagePayload(i18n_key="ntf-remnawave-sync-confirm"),
    )


@inject
async def on_clear_all(
    callback: CallbackQuery,
    button,
    manager: DialogManager,
):
    """Обработчик для первого нажатия на кнопку очистки всех данных."""
    from src.bot.states import DashboardDB
    await manager.switch_to(DashboardDB.CLEAR_ALL_CONFIRM)


@inject
async def on_clear_users(
    callback: CallbackQuery,
    button,
    manager: DialogManager,
):
    """Обработчик для первого нажатия на кнопку очистки пользователей."""
    from src.bot.states import DashboardDB
    await manager.switch_to(DashboardDB.CLEAR_USERS_CONFIRM)


@inject
async def on_clear_all_confirm(
    callback: CallbackQuery,
    button,
    manager: DialogManager,
    notification_service: FromDishka[NotificationService],
    redis_client: FromDishka[Redis],
):
    """Обработчик для подтверждения полной очистки базы данных."""
    user = manager.middleware_data.get(USER_KEY)
    
    await notification_service.notify_user(
        user=user,
        payload=MessagePayload(i18n_key="ntf-db-clear-all-start"),
    )
    
    loop = asyncio.get_event_loop()
    
    def clear_all_db():
        """Полная очистка базы данных."""
        import os as os_module
        
        db_password = os_module.getenv('DATABASE_PASSWORD', 'remnashop')
        db_user = os_module.getenv('DATABASE_USER', 'remnashop')
        db_name = os_module.getenv('DATABASE_NAME', 'remnashop')
        db_host = os_module.getenv('DATABASE_HOST', 'remnashop-db')
        db_port = os_module.getenv('DATABASE_PORT', '5432')
        
        env = os_module.environ.copy()
        env['PGPASSWORD'] = db_password
        
        # SQL запрос для подсчета записей перед удалением
        count_query = """
        SELECT 
            (SELECT COUNT(*) FROM users) as users,
            (SELECT COUNT(*) FROM subscriptions) as subscriptions,
            (SELECT COUNT(*) FROM transactions) as transactions,
            (SELECT COUNT(*) FROM promocodes) as promocodes,
            (SELECT COUNT(*) FROM promocode_activations) as activations,
            (SELECT COUNT(*) FROM referrals) as referrals,
            (SELECT COUNT(*) FROM referral_rewards) as rewards,
            (SELECT COUNT(*) FROM notifications) as notifications;
        """
        
        # Получаем количество записей до удаления
        count_cmd = [
            'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', db_name,
            '-t', '-c', count_query
        ]
        result = subprocess.run(count_cmd, capture_output=True, text=True, env=env)
        
        counts = {}
        if result.returncode == 0:
            values = result.stdout.strip().split('|')
            counts = {
                'users': int(values[0].strip()),
                'subscriptions': int(values[1].strip()),
                'transactions': int(values[2].strip()),
                'promocodes': int(values[3].strip()),
                'activations': int(values[4].strip()),
                'referrals': int(values[5].strip()),
                'rewards': int(values[6].strip()),
                'notifications': int(values[7].strip()),
            }
        
        # SQL запрос для удаления всех данных
        delete_query = """
        BEGIN;
        DELETE FROM referral_rewards;
        DELETE FROM referrals;
        DELETE FROM promocode_activations;
        DELETE FROM transactions;
        DELETE FROM subscriptions;
        DELETE FROM users;
        DELETE FROM promocodes;
        DELETE FROM notifications;
        COMMIT;
        """
        
        # Выполняем очистку
        delete_cmd = [
            'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', db_name,
            '-c', delete_query
        ]
        result = subprocess.run(delete_cmd, capture_output=True, text=True, env=env)
        
        if result.returncode != 0:
            return False, result.stderr, counts
        
        return True, None, counts
    
    try:
        success, error, counts = await loop.run_in_executor(None, clear_all_db)
        
        if success:
            # Очищаем кэш Redis
            await redis_client.flushall()
            logger.info(f"{log(user)} Database cleared successfully")
            
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(
                    i18n_key="ntf-db-clear-all-success",
                    i18n_kwargs=counts,
                ),
            )
        else:
            logger.error(f"{log(user)} Failed to clear database: {error}")
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(
                    i18n_key="ntf-db-clear-all-failed",
                    i18n_kwargs={"error": error},
                ),
            )
    except Exception as e:
        logger.exception(f"{log(user)} Error clearing database: {e}")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(
                i18n_key="ntf-db-clear-all-failed",
                i18n_kwargs={"error": str(e)},
            ),
        )
    
    from src.bot.states import DashboardDB
    await manager.switch_to(DashboardDB.MAIN)


@inject
async def on_clear_users_confirm(
    callback: CallbackQuery,
    button,
    manager: DialogManager,
    notification_service: FromDishka[NotificationService],
    redis_client: FromDishka[Redis],
):
    """Обработчик для подтверждения очистки пользователей."""
    user = manager.middleware_data.get(USER_KEY)
    
    await notification_service.notify_user(
        user=user,
        payload=MessagePayload(i18n_key="ntf-db-clear-users-start"),
    )
    
    loop = asyncio.get_event_loop()
    
    def clear_users_db():
        """Очистка пользователей из базы данных."""
        import os as os_module
        
        db_password = os_module.getenv('DATABASE_PASSWORD', 'remnashop')
        db_user = os_module.getenv('DATABASE_USER', 'remnashop')
        db_name = os_module.getenv('DATABASE_NAME', 'remnashop')
        db_host = os_module.getenv('DATABASE_HOST', 'remnashop-db')
        db_port = os_module.getenv('DATABASE_PORT', '5432')
        
        env = os_module.environ.copy()
        env['PGPASSWORD'] = db_password
        
        # SQL запрос для подсчета записей перед удалением
        count_query = """
        SELECT 
            (SELECT COUNT(*) FROM users) as users,
            (SELECT COUNT(*) FROM subscriptions) as subscriptions,
            (SELECT COUNT(*) FROM transactions) as transactions,
            (SELECT COUNT(*) FROM promocode_activations) as activations,
            (SELECT COUNT(*) FROM referrals) as referrals,
            (SELECT COUNT(*) FROM referral_rewards) as rewards;
        """
        
        # Получаем количество записей до удаления
        count_cmd = [
            'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', db_name,
            '-t', '-c', count_query
        ]
        result = subprocess.run(count_cmd, capture_output=True, text=True, env=env)
        
        counts = {}
        if result.returncode == 0:
            values = result.stdout.strip().split('|')
            counts = {
                'users': int(values[0].strip()),
                'subscriptions': int(values[1].strip()),
                'transactions': int(values[2].strip()),
                'activations': int(values[3].strip()),
                'referrals': int(values[4].strip()),
                'rewards': int(values[5].strip()),
            }
        
        # SQL запрос для удаления пользователей и связанных данных
        delete_query = """
        BEGIN;
        DELETE FROM referral_rewards;
        DELETE FROM referrals;
        DELETE FROM promocode_activations;
        DELETE FROM transactions;
        DELETE FROM subscriptions;
        DELETE FROM users;
        COMMIT;
        """
        
        # Выполняем очистку
        delete_cmd = [
            'psql', '-h', db_host, '-p', db_port, '-U', db_user, '-d', db_name,
            '-c', delete_query
        ]
        result = subprocess.run(delete_cmd, capture_output=True, text=True, env=env)
        
        if result.returncode != 0:
            return False, result.stderr, counts
        
        return True, None, counts
    
    try:
        success, error, counts = await loop.run_in_executor(None, clear_users_db)
        
        if success:
            # Очищаем кэш Redis
            await redis_client.flushall()
            logger.info(f"{log(user)} Users cleared successfully")
            
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(
                    i18n_key="ntf-db-clear-users-success",
                    i18n_kwargs=counts,
                ),
            )
        else:
            logger.error(f"{log(user)} Failed to clear users: {error}")
            await notification_service.notify_user(
                user=user,
                payload=MessagePayload(
                    i18n_key="ntf-db-clear-users-failed",
                    i18n_kwargs={"error": error},
                ),
            )
    except Exception as e:
        logger.exception(f"{log(user)} Error clearing users: {e}")
        await notification_service.notify_user(
            user=user,
            payload=MessagePayload(
                i18n_key="ntf-db-clear-users-failed",
                i18n_kwargs={"error": str(e)},
            ),
        )
    
    from src.bot.states import DashboardDB
    await manager.switch_to(DashboardDB.MAIN)
