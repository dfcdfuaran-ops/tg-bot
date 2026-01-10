#!/bin/bash
# version: 1.0.0
# TG-SELL-BOT Installation Script

set -e
exec < /dev/tty

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
WHITE='\033[1;37m'
NC='\033[0m'
DARKGRAY='\033[1;30m'
trap 'tput sgr0 >/dev/null 2>&1 || true' EXIT

# Пути установки
INSTALL_DIR="${INSTALL_DIR:-.}"
LOCK_FILE="/tmp/tg-sell-bot-install.lock"

# Очистка при неудачной установке
cleanup_on_fail() {
  echo
  echo -e "${RED}❌ Установка прервана или завершилась с ошибкой.${NC}"
  echo -e "${YELLOW}🧹 Выполняется очистка системы...${NC}"
  docker compose -f "$INSTALL_DIR/docker-compose.yml" down 2>/dev/null || true
  rm -f "$LOCK_FILE"
  echo -e "${GREEN}✅ Очистка завершена.${NC}\n"
  exit 1
}
trap cleanup_on_fail ERR INT

# Безопасный ввод
safe_read() {
  local prompt="$1"
  local varname="$2"
  echo -ne "$prompt"
  IFS= read -r "$varname" || { echo; cleanup_on_fail; }
}

# Спиннер прогресса установки
show_spinner() {
  local pid=$!
  local delay=0.08
  local spin=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
  local i=0 msg="$1"
  while kill -0 $pid 2>/dev/null; do
    printf "\r${GREEN}%s${NC}  %s" "${spin[$i]}" "$msg"
    i=$(( (i+1) % 10 ))
    sleep $delay
  done
  printf "\r${GREEN}✅${NC} %s\n" "$msg"
}

# Красивый вывод
print_action() { printf "${BLUE}➜${NC}  %b\n" "$1"; }
print_error()  { printf "${RED}✖ %b${NC}\n" "$1"; }
print_success() { printf "${GREEN}✅${NC} %b\n" "$1"; }

# ============================================================
# ЗАГОЛОВОК УСТАНОВКИ
# ============================================================

clear
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}   🚀 УСТАНОВКА TG-SELL-BOT${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Проверка Docker
if ! command -v docker &> /dev/null; then
  print_error "Docker не установлен. Пожалуйста установите Docker и повторите попытку."
  exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
  print_error "Docker Compose не установлен. Пожалуйста установите Docker Compose и повторите попытку."
  exit 1
fi

print_success "Docker окружение обнаружено\n"

# ============================================================
# ПОЛУЧЕНИЕ ДАННЫХ ОТ ПОЛЬЗОВАТЕЛЯ
# ============================================================

echo -e "${BLUE}========================================${NC}"
echo -e "${WHITE}  ⚙️ КОНФИГУРАЦИЯ БОТА${NC}"
echo -e "${BLUE}========================================${NC}\n"

safe_read "${YELLOW}➜ Введите домен бота (напр. bot.example.com):${NC} " BOT_DOMAIN
safe_read "${YELLOW}➜ Введите Токен телеграм бота:${NC} " BOT_TOKEN
safe_read "${YELLOW}➜ Введите телеграм ID разработчика:${NC} " ADMIN_ID
safe_read "${YELLOW}➜ Введите username группы поддержки (без @):${NC} " SUPPORT_CHANNEL
safe_read "${YELLOW}➜ Введите Токен Remnawave:${NC} " REMNAWAVE_TOKEN

touch "$LOCK_FILE"

echo
echo -e "${BLUE}========================================${NC}\n"

# ============================================================
# ВЫПОЛНЕНИЕ УСТАНОВКИ
# ============================================================

echo -e "${BLUE}========================================${NC}"
echo -e "${WHITE}  ⚡ ВЫПОЛНЕНИЕ УСТАНОВКИ${NC}"
echo -e "${BLUE}========================================${NC}\n"

# 1. Сборка Docker образа
(
    cd "$INSTALL_DIR"
    docker compose build >/dev/null 2>&1
) &
show_spinner "Сборка Docker образа"

# 2. Создание .env файла
(
cat > "$INSTALL_DIR/.env" << EOF
# Telegram Bot Configuration
BOT_TOKEN=$BOT_TOKEN
ADMIN_ID=$ADMIN_ID
BOT_DOMAIN=$BOT_DOMAIN
SUPPORT_CHANNEL=$SUPPORT_CHANNEL

# Database Configuration
DATABASE_USER=remnashop
DATABASE_PASSWORD=$(openssl rand -hex 16)
DATABASE_NAME=remnashop

# Redis Configuration
REDIS_PASSWORD=$(openssl rand -hex 16)

# Bot Configuration
SECRET_KEY=$(openssl rand -base64 32 | tr -d '\n')
ALGORITHM=HS256

# Remnawave Configuration
REMNAWAVE_TOKEN=$REMNAWAVE_TOKEN
REMNAWAVE_WEBHOOK_SECRET=$(openssl rand -hex 32)

# Application Settings
APP_ENV=production
DEBUG=false
LOG_LEVEL=info

# Asset Settings
RESET_ASSETS=false
EOF
) &
show_spinner "Создание конфигурации"

# 3. Создание необходимых папок
(
  mkdir -p "$INSTALL_DIR"/{logs,assets,backups}
) &
show_spinner "Создание структуры папок"

# 4. Запуск контейнеров
(
    cd "$INSTALL_DIR"
    docker compose up -d >/dev/null 2>&1
) &
show_spinner "Запуск сервисов"

# 5. Ожидание готовности БД
(
  sleep 10
) &
show_spinner "Инициализация базы данных"

# 6. Удаление скрипта установки и других временных файлов
(
  rm -f "$INSTALL_DIR/server-setup.sh" 2>/dev/null || true
  rm -f "$LOCK_FILE"
) &
show_spinner "Финальная очистка"

echo

# ============================================================
# ЗАВЕРШЕНИЕ УСТАНОВКИ
# ============================================================

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}    🎉 УСТАНОВКА ЗАВЕРШЕНА УСПЕШНО!${NC}"
echo -e "${BLUE}========================================${NC}\n"

print_success "Бот успешно установлен и запущен"
print_success "Домен: $BOT_DOMAIN"
print_success "Место нахождения: ${YELLOW}$INSTALL_DIR${NC}"

echo
echo -e "${BLUE}========================================${NC}"
echo -e "${DARKGRAY}  📋 ПОЛЕЗНЫЕ КОМАНДЫ${NC}"
echo -e "${BLUE}========================================${NC}\n"

echo -e "  ${YELLOW}cd $INSTALL_DIR${NC}"
echo -e "  ${YELLOW}docker compose logs -f${NC}              # Просмотр логов"
echo -e "  ${YELLOW}docker compose down${NC}                 # Остановка"
echo -e "  ${YELLOW}docker compose up -d${NC}                # Запуск"
echo -e "  ${YELLOW}docker compose restart${NC}              # Перезагрузка"

echo
echo -e "${BLUE}========================================${NC}\n"

print_success "Конфигурация сохранена в: ${YELLOW}$INSTALL_DIR/.env${NC}"
print_success "Логи доступны через: ${YELLOW}docker compose logs${NC}"

echo
