# Изменения для сохранения short_uuid при восстановлении из бэкапа

## Проблема
При восстановлении пользователей из бэкапа PostgreSQL или синхронизации данных бота с панелью Remnawave, `short_uuid` подписки не сохранялся. Это приводило к тому, что старые ссылки на подписки переставали работать.

## Решение

### Изменения в `/opt/remnashop/src/services/remnawave.py`

В методе `create_user` добавлена логика проверки и сохранения `short_uuid`:

1. **При создании нового пользователя:**
   - Извлекается `short_uuid` из URL подписки (если доступен)
   - Передается в API через `CreateUserRequestDto`

2. **При обновлении существующего пользователя (force=True):**
   - Получаются данные существующего пользователя из панели
   - Сравнивается `short_uuid` в панели с `short_uuid` из бэкапа
   - **Если не совпадают:**
     - Удаляется старый пользователь
     - Создается новый с правильным `short_uuid`
   - **Если совпадают:**
     - Выполняется обычное обновление

### Ключевые изменения

```python
# Извлечение short_uuid из URL
if subscription and subscription.url:
    desired_short_uuid = subscription.url.rstrip('/').split('/')[-1]
    if old_remna_user.short_uuid != desired_short_uuid:
        # Пересоздаем пользователя
        need_recreate = True
```

### Логирование

Добавлены подробные логи для отслеживания процесса:

- `INFO: Extracted short_uuid from URL: ...`
- `WARNING: short_uuid mismatch: existing=..., desired=...`
- `INFO: Deleting user ... to recreate with correct short_uuid`
- `INFO: User recreated successfully with short_uuid=...`

## Применение

Изменения автоматически применяются в следующих сценариях:

1. **Восстановление из SQL бэкапа** (`scripts/restore_db.sh`)
   - Все URL подписок из бэкапа сохраняются в БД
   - При синхронизации бота с панелью используется правильный `short_uuid`

2. **Синхронизация бота с панелью** (`sync_all_users_from_bot_to_panel_task`)
   - При создании пользователей в панели используется `short_uuid` из БД
   - При обновлении проверяется совпадение

3. **Ручная синхронизация через бота**
   - Через интерфейс Dashboard → Users → User → Sync

## Тестирование

### Проверка после восстановления:

1. Восстановить бэкап:
```bash
cd /opt/remnashop
./scripts/restore_db.sh backups/remnashop_backup_2.sql
```

2. Запустить синхронизацию (через бота или вручную)

3. Проверить логи:
```bash
docker compose logs -f remnashop-bot | grep short_uuid
```

4. Проверить панель Remnawave:
   - Зайти в Users
   - Найти пользователя
   - Убедиться, что short_uuid совпадает с URL из бэкапа

### Пример успешного лога:

```
INFO: Extracted short_uuid from URL: 7keVXhdM4mtDVCwp
INFO: Creating RemnaUser 'remnashop_1221936130' from subscription 'Стандарт'
INFO: RemnaUser 'remnashop_1221936130' created successfully
```

### Пример лога с пересозданием:

```
WARNING: User 'remnashop_1221936130' already exists. Force flag enabled, checking if we need to recreate or update
INFO: Found existing user by telegram_id '1221936130': uuid=..., short_uuid=ABC123
WARNING: short_uuid mismatch: existing=ABC123, desired=7keVXhdM4mtDVCwp. Will recreate user to preserve short_uuid from backup.
INFO: Deleting user ... to recreate with correct short_uuid
INFO: User recreated successfully with short_uuid=7keVXhdM4mtDVCwp
```

## Важные замечания

- `short_uuid` не может быть изменен через API обновления - только при создании
- Пересоздание пользователя происходит только при несовпадении `short_uuid`
- Все данные подписки сохраняются (трафик, устройства, срок действия)
- При создании нового пользователя (не из бэкапа) панель сама генерирует `short_uuid`

## Обратная совместимость

- Если `subscription.url` отсутствует, создание работает как раньше
- Если `short_uuid` совпадает, пересоздание не выполняется
- Старая логика обновления сохранена для случаев без `subscription`
