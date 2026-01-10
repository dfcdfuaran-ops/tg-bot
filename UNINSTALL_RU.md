# Удаление TG-SELL-BOT

## Вариант 1: Полное удаление (рекомендуется)

Используйте скрипт автоматического удаления:

```bash
cd /opt/tg-sell-bot
bash uninstall.sh
```

Скрипт удалит:
- ✅ Все Docker контейнеры
- ✅ Все Docker volumes (базы данных, кэш)
- ✅ Docker образы
- ✅ Docker сети
- ✅ Все файлы проекта
- ✅ Временные файлы системы

## Вариант 2: Ручное удаление (пошагово)

### Шаг 1: Остановка контейнеров
```bash
cd /opt/tg-sell-bot
docker compose down
```

### Шаг 2: Удаление volumes (базы данных и кэша)
```bash
docker compose down -v
```

### Шаг 3: Удаление Docker образа
```bash
docker rmi remnashop:local -f
```

### Шаг 4: Удаление Docker сети (если создавалась отдельно)
```bash
docker network rm remnawave-network
```

### Шаг 5: Удаление файлов проекта
```bash
cd /opt
rm -rf tg-sell-bot remnashop
```

### Шаг 6: Очистка временных файлов
```bash
rm -f /tmp/tg-sell-bot-install.lock
```

## Проверка успешного удаления

```bash
# Проверить отсутствие контейнеров
docker ps -a | grep remnashop

# Проверить отсутствие volumes
docker volume ls | grep remnashop

# Проверить отсутствие образов
docker images | grep remnashop

# Проверить отсутствие папок
ls /opt/tg-sell-bot 2>/dev/null || echo "✓ Папка удалена"
```

## Переустановка после удаления

После полного удаления можно безопасно установить бота заново:

```bash
bash install.sh
```
