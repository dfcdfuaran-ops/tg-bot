# Руководство по восстановлению из бэкапа с сохранением short_uuid

## Проблема

При восстановлении пользователей из бэкапа важно сохранить их `short_uuid` подписки в панели Remnawave, так как этот идентификатор используется в URL подписки (например, `https://sub.domain.com/SHORT_UUID`). Если `short_uuid` не совпадает с тем, что был в бэкапе, пользователи не смогут получить доступ по старым ссылкам.

## Решение

Система автоматически:

1. **При создании пользователя из бэкапа:**
   - Извлекает `short_uuid` из URL подписки в базе данных
   - Передает его в API Remnawave при создании пользователя
   - Панель создает пользователя с этим `short_uuid`

2. **При обновлении существующего пользователя (`force=True`):**
   - Получает информацию о существующем пользователе из панели
   - Сравнивает `short_uuid` в панели с `short_uuid` из бэкапа
   - Если они не совпадают:
     - Удаляет старого пользователя
     - Создает нового с правильным `short_uuid` из бэкапа
   - Если совпадают:
     - Обновляет параметры существующего пользователя

## Пример работы

### Структура URL в бэкапе
```sql
COPY public.subscriptions (id, user_remna_id, user_telegram_id, ..., url, ...) FROM stdin;
2   1e221a25-dcda-42e9-ade7-2fc629ff1541   1221936130   ...   https://sub.dfc-online.com/7keVXhdM4mtDVCwp   ...
```

Здесь `short_uuid` = `7keVXhdM4mtDVCwp`

### Логика восстановления

```python
# Код в /opt/remnashop/src/services/remnawave.py

# 1. Извлечение short_uuid из URL
if subscription.url:
    short_uuid = subscription.url.rstrip('/').split('/')[-1]
    # short_uuid = "7keVXhdM4mtDVCwp"

# 2. Создание пользователя с этим short_uuid
await self.remnawave.users.create_user(
    CreateUserRequestDto(
        uuid=subscription.user_remna_id,
        short_uuid=short_uuid,  # <- Передаем short_uuid из бэкапа
        ...
    )
)

# 3. При конфликте (пользователь уже существует) и force=True
if need_recreate:  # short_uuid не совпадает
    # Удаляем старого
    await self.remnawave.users.delete_user(old_remna_user.uuid)
    # Создаем с правильным short_uuid
    created = await _do_create()
```

## Логирование

Система выводит подробные логи:

```
INFO: Extracted short_uuid from URL: 7keVXhdM4mtDVCwp
INFO: Creating RemnaUser 'remnashop_1221936130' from subscription 'Стандарт'

# При конфликте:
WARNING: User 'remnashop_1221936130' already exists. Force flag enabled, checking if we need to recreate or update
INFO: Found existing user by telegram_id '1221936130': uuid=..., short_uuid=ABC123
WARNING: short_uuid mismatch: existing=ABC123, desired=7keVXhdM4mtDVCwp. Will recreate user to preserve short_uuid from backup.
INFO: Deleting user ... to recreate with correct short_uuid
INFO: User recreated successfully with short_uuid=7keVXhdM4mtDVCwp
```

## Когда это применяется

1. **Восстановление из бэкапа PostgreSQL** - все URL и short_uuid сохраняются
2. **Импорт пользователей из другой панели** - при наличии URL подписки
3. **Миграция данных** - сохраняется совместимость со старыми ссылками

## Важные моменты

- `short_uuid` **нельзя** изменить через `UpdateUserRequestDto` - это поле устанавливается только при создании
- При обновлении без изменения `short_uuid` система использует обычное обновление (быстрее)
- Пересоздание пользователя происходит только при несовпадении `short_uuid`
- Все параметры подписки (трафик, устройства, дата истечения) восстанавливаются из бэкапа

## Проверка

После восстановления можно проверить:

1. **В панели Remnawave:**
   - Зайти в Users
   - Найти пользователя
   - Проверить, что short_uuid совпадает с URL

2. **По URL:**
   - Открыть URL подписки из бэкапа
   - Убедиться, что подписка доступна

3. **В логах:**
   - Искать сообщения о `short_uuid`
   - Проверить, были ли пересоздания пользователей
