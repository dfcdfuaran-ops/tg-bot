#!/bin/bash

# =============================================================================
# Скрипт для восстановления базы данных PostgreSQL из бэкапа через docker
# Восстанавливает все данные: пользователи, планы, подписки, рефералы, сквады
# =============================================================================

set -e

BACKUP_FILE="${1}"

if [ -z "$BACKUP_FILE" ]; then
  echo "Использование: $0 <путь_к_бэкапу.sql>"
  echo ""
  echo "Пример: $0 ./backups/remnashop_backup_2025-01-03.sql"
  exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
  echo "ОШИБКА: Файл бэкапа не найден: $BACKUP_FILE"
  exit 1
fi

echo "=== Восстановление базы данных remnashop ==="
echo "Файл: $BACKUP_FILE"
echo ""

# Проверяем доступность контейнера
if ! docker ps --format '{{.Names}}' | grep -q '^remnashop-db$'; then
  echo "ОШИБКА: Контейнер remnashop-db не запущен!"
  echo "Запустите: docker compose up -d remnashop-db"
  exit 1
fi

# Ожидаем готовности PostgreSQL
echo "Ожидание готовности PostgreSQL..."
for i in {1..30}; do
  if docker exec remnashop-db pg_isready -U remnashop -d remnashop > /dev/null 2>&1; then
    echo "PostgreSQL готов!"
    break
  fi
  if [ $i -eq 30 ]; then
    echo "ОШИБКА: PostgreSQL не готов после 30 секунд ожидания"
    exit 1
  fi
  sleep 1
done

echo ""
echo "⚠️  ВНИМАНИЕ: Все текущие данные будут перезаписаны!"
read -p "Продолжить? (y/N): " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Отменено пользователем"
  exit 0
fi

echo ""
echo "Восстанавливаем данные..."

# Останавливаем бота перед восстановлением
echo "Останавливаем бота..."
docker stop remnashop remnashop-taskiq-worker remnashop-taskiq-scheduler 2>/dev/null || true

# Восстанавливаем из бэкапа
# --single-transaction - все операции в одной транзакции (откат при ошибке)
# --set ON_ERROR_STOP=1 - останавливаться при первой ошибке
cat "$BACKUP_FILE" | docker exec -i remnashop-db psql \
  -U "remnashop" \
  -d "remnashop" \
  --single-transaction \
  --set ON_ERROR_STOP=1 \
  2>&1 | grep -v "^DROP" | grep -v "^ALTER" | grep -v "^SET" | grep -v "^SELECT" | head -20

RESULT=${PIPESTATUS[1]}

if [ $RESULT -eq 0 ]; then
  echo ""
  echo "=== Восстановление успешно завершено ==="
  
  # Показываем статистику
  echo ""
  echo "Статистика восстановленных данных:"
  docker exec remnashop-db psql -U remnashop -d remnashop -c "
    SELECT 'users' as table_name, COUNT(*) as count FROM users
    UNION ALL SELECT 'plans', COUNT(*) FROM plans
    UNION ALL SELECT 'subscriptions', COUNT(*) FROM subscriptions
    UNION ALL SELECT 'referrals', COUNT(*) FROM referrals
    UNION ALL SELECT 'transactions', COUNT(*) FROM transactions
    UNION ALL SELECT 'promocodes', COUNT(*) FROM promocodes
    UNION ALL SELECT 'payment_gateways', COUNT(*) FROM payment_gateways
    ORDER BY table_name;
  " 2>/dev/null
  
  echo ""
  echo "Запускаем бота..."
  docker start remnashop remnashop-taskiq-worker remnashop-taskiq-scheduler 2>/dev/null || true
  
  echo ""
  echo "SUCCESS"
  exit 0
else
  echo ""
  echo "ОШИБКА: Восстановление завершилось с ошибкой!"
  
  echo ""
  echo "Запускаем бота..."
  docker start remnashop remnashop-taskiq-worker remnashop-taskiq-scheduler 2>/dev/null || true
  
  exit 1
fi
