#!/bin/bash
# TG-SELL-BOT Complete Uninstall Script
# Полное удаление бота со всеми остатками

set -e

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
NC='\033[0m'

# Скрыть курсор
tput civis >/dev/null 2>&1 || true
trap 'tput cnorm >/dev/null 2>&1 || true' EXIT

# Заголовок
clear
echo -e "${BLUE}========================================${NC}"
echo -e "${RED}     ⚠️ ПОЛНОЕ УДАЛЕНИЕ TG-SELL-BOT${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Проверка текущего пути
if [ ! -f "docker-compose.yml" ]; then
  echo -e "${RED}✖ Ошибка: docker-compose.yml не найден в текущей папке${NC}"
  echo -e "${YELLOW}Пожалуйста перейдите в папку проекта и повторите:${NC}"
  echo -e "  cd /opt/tg-sell-bot"
  echo -e "  bash uninstall.sh"
  exit 1
fi

PROJECT_DIR="$(pwd)"

echo -e "${RED}❌ Будут удалены:${NC}"
echo -e "  • Все Docker контейнеры проекта"
echo -e "  • Все Docker volumes проекта"
echo -e "  • Docker образ бота"
echo -e "  • Все файлы в: $PROJECT_DIR"
echo ""
echo -e "${YELLOW}⚠️ Это действие необратимо!${NC}\n"

read -p "$(echo -e "${RED}Введите 'yes' для подтверждения удаления:${NC} ")" CONFIRM

if [ "$CONFIRM" != "yes" ]; then
  echo -e "${YELLOW}❌ Удаление отменено пользователем.${NC}\n"
  exit 0
fi

echo -e "\n${BLUE}========================================${NC}"
echo -e "${YELLOW}     🧹 ВЫПОЛНЕНИЕ ПОЛНОГО УДАЛЕНИЯ${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Функция для показа прогресса
show_progress() {
  echo -ne "${GREEN}✅${NC} $1\n"
}

# 1. Остановка и удаление контейнеров
echo -ne "${YELLOW}➜${NC} Остановка контейнеров... "
docker compose down 2>/dev/null || true
show_progress "Контейнеры остановлены"

# 2. Удаление volumes
echo -ne "${YELLOW}➜${NC} Удаление volumes... "
docker compose down -v 2>/dev/null || true
# Явное удаление volumes по имени
docker volume rm remnashop-db-data 2>/dev/null || true
docker volume rm remnashop-redis-data 2>/dev/null || true
docker volume rm tg-sell-bot-remnashop-db-data 2>/dev/null || true
docker volume rm tg-sell-bot-remnashop-redis-data 2>/dev/null || true
show_progress "Volumes удалены"

# 3. Удаление Docker образов
echo -ne "${YELLOW}➜${NC} Удаление Docker образов... "
docker rmi remnashop:local 2>/dev/null || true
docker rmi tg-sell-bot-remnashop:latest 2>/dev/null || true
docker image prune -f 2>/dev/null || true
show_progress "Docker образы удалены"

# 4. Удаление Docker сети
echo -ne "${YELLOW}➜${NC} Удаление Docker сети... "
docker network rm remnawave-network 2>/dev/null || true
docker network rm tg-sell-bot_default 2>/dev/null || true
show_progress "Docker сети удалены"

# 5. Удаление файлов проекта
echo -ne "${YELLOW}➜${NC} Удаление файлов проекта... "
cd /opt
rm -rf tg-sell-bot remnashop
show_progress "Файлы проекта удалены"

# 6. Очистка временных файлов
echo -ne "${YELLOW}➜${NC} Очистка временных файлов... "
rm -f /tmp/tg-sell-bot-install.lock
rm -f /tmp/tg-support-bot-install.lock
show_progress "Временные файлы удалены"

echo
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}     ✅ УДАЛЕНИЕ ЗАВЕРШЕНО УСПЕШНО${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo -e "${GREEN}✓${NC} Бот полностью удален из системы"
echo -e "${GREEN}✓${NC} Все Docker ресурсы очищены"
echo -e "${GREEN}✓${NC} Система готова к новой установке\n"
