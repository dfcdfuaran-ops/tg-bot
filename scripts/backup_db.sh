#!/bin/bash

# =============================================================================
# Скрипт для создания полного дампа базы данных PostgreSQL через docker
# Сохраняет все данные: пользователи, планы, подписки, рефералы, сквады и т.д.
# =============================================================================

set -e

BACKUP_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y-%m-%d_%H-%M-%S)
FILENAME="${2:-${TIMESTAMP}.sql}"

# Создаем директорию если не существует
if [ ! -d "$BACKUP_DIR" ]; then
  mkdir -p "$BACKUP_DIR"
fi

FILEPATH="$BACKUP_DIR/$FILENAME"

echo "=== Создание бэкапа базы данных remnashop ==="
echo "Путь: $FILEPATH"
echo ""

# Проверяем доступность контейнера
if ! docker ps --format '{{.Names}}' | grep -q '^remnashop-db$'; then
  echo "ОШИБКА: Контейнер remnashop-db не запущен!"
  exit 1
fi

# Создаем полный дамп с правильными параметрами для переноса:
# --clean           - добавляет DROP команды перед CREATE (для восстановления на существующую БД)
# --if-exists       - использует IF EXISTS для DROP (не падает если объект не существует)
# --no-owner        - не включает владельца объектов (для переноса между серверами)
# --no-acl          - не включает права доступа (для переноса между серверами)

docker exec -t remnashop-db pg_dump \
  -U "remnashop" \
  -d "remnashop" \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  > "$FILEPATH"

# Проверяем результат
if [ $? -eq 0 ] && [ -s "$FILEPATH" ]; then
  # Подсчитываем статистику
  TABLES=$(grep -c "^COPY public\." "$FILEPATH" 2>/dev/null || echo "0")
  SIZE=$(du -h "$FILEPATH" | cut -f1)
  
  echo ""
  echo "=== Бэкап успешно создан ==="
  echo "Файл: $FILEPATH"
  echo "Размер: $SIZE"
  echo "Таблиц: $TABLES"
  echo ""
  echo "Содержит:"
  grep "^COPY public\." "$FILEPATH" | sed 's/COPY public\.//; s/ (.*//' | while read table; do
    echo "  ✓ $table"
  done
  echo ""
  echo "SUCCESS"
  exit 0
else
  echo "ОШИБКА: Не удалось создать бэкап!"
  rm -f "$FILEPATH"
  exit 1
fi
