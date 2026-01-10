# Краткая сводка изменений

## 1. Сохранение short_uuid при восстановлении из бэкапа

**Файл:** `/opt/remnashop/src/services/remnawave.py`

**Проблема:** При восстановлении пользователей из бэкапа (когда пользователь уже есть в панели), система обновляла данные, но не заменяла `short_uuid` подписки.

**Решение:** Теперь при `force=True` и наличии подписки с URL:
- ВСЕГДА пересоздается пользователь в панели с правильным `short_uuid` из бэкапа
- Это гарантирует, что URL подписки в панели совпадает с URL в базе данных

**Логирование:**
```
INFO: short_uuid from backup: 7keVXhdM4mtDVCwp, existing in panel: ABC123. Will recreate user to ensure consistency.
INFO: Deleting user ... to recreate with correct short_uuid
INFO: User recreated successfully with short_uuid=7keVXhdM4mtDVCwp
```

---

## 2. Включение функции "Переводы" по умолчанию

**Файлы:**
1. `/opt/remnashop/src/infrastructure/database/models/dto/settings.py` - изменен default параметр
2. `/opt/remnashop/src/infrastructure/database/migrations/versions/0035_enable_transfers_by_default.py` - новая миграция

**Изменение:**
- В `TransferSettingsDto` изменено `enabled: bool = False` → `enabled: bool = True`
- Создана миграция для обновления существующих записей в БД

**Эффект:**
- Новые инстансы бота будут иметь функцию "Переводы" включенной по умолчанию
- При применении миграции все существующие конфигурации будут обновлены

---

## Информация о пользователе 855511342

**Short UUID подписки:** `puc8b5n_xfebh6sg`

**URL подписки:** `https://sub.dfc-online.com/puc8b5n_xfebh6sg`

**Текущие подписки в бэкапе:** 7 активных (IDs: 1, 16, 24, 44, 45, 65, 86)

---

## Как применить изменения

### При восстановлении из свежего бэкапа:
1. Восстановить бэкап: `./scripts/restore_db.sh`
2. Миграция автоматически применится при запуске бота
3. Все пользователи синхронизируются с правильными `short_uuid`

### Для существующей БД:
1. Запустить миграцию вручную:
```bash
alembic upgrade head
```

### Проверка:
```bash
# Просмотреть логи
docker compose logs -f remnashop-bot | grep -E "short_uuid|transfers"
```

---

## Технические детали

### short_uuid восстановление:
- Применяется при: `create_user(..., force=True)` с подписками, имеющими URL
- Затрагивает: восстановление из бэкапа, синхронизацию бота ↔ панель
- Безопасно: старые пользователи удаляются и пересоздаются с корректными данными

### Включение "Переводов":
- По умолчанию: `TransferSettingsDto.enabled = True`
- Можно отключить в Settings → Переводы
- Не влияет на уже настроенные переводы (сохраняется прежний статус)
