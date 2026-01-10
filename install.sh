#!/bin/bash
set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Спинер
SPINNER=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
SPINNER_DELAY=0.08

# Путь к проекту
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${PROJECT_DIR}/.env"

# ============================================================
# ФУНКЦИИ
# ============================================================

show_spinner() {
    local i=0
    while kill -0 $1 2>/dev/null; do
        i=$(( (i+1) % 10 ))
        printf "\r${SPINNER[$i]} "
        sleep $SPINNER_DELAY
    done
}

log_header() {
    echo -e "\n${CYAN}════════════════════════════════════════════${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}════════════════════════════════════════════${NC}\n"
}

log_step() {
    echo -e "${BLUE}$1${NC}"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
    exit 1
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

step_start() {
    echo -ne "${BLUE}⠿${NC} $1 "
}

step_done() {
    echo -e "\r${GREEN}✓${NC} $1"
}

read_input() {
    local prompt="$1"
    local default="$2"
    local input
    
    if [ -z "$default" ]; then
        read -p "  ${YELLOW}➜${NC} ${prompt}: " input
    else
        read -p "  ${YELLOW}➜${NC} ${prompt} [${default}]: " input
        input="${input:-$default}"
    fi
    
    echo "$input"
}

generate_key() {
    openssl rand -base64 32 | tr -d '\n'
}

# ============================================================
# НАЧАЛО УСТАНОВКИ
# ============================================================

clear

log_header "УСТАНОВКА TG-SELL-BOT"

echo -e "Пожалуйста введите данные для начала установки:\n"

# Получаем данные от пользователя
BOT_DOMAIN=$(read_input "Введите домен бота")
BOT_TOKEN=$(read_input "Введите Токен телеграм бота")
ADMIN_ID=$(read_input "Введите телеграм ID разработчика")
SUPPORT_CHANNEL=$(read_input "Введите username группы поддержки (без @)")
REMNAWAVE_TOKEN=$(read_input "Введите Токен Remnawave")

# ============================================================
# ВЫПОЛНЕНИЕ УСТАНОВКИ
# ============================================================

log_header "ВЫПОЛНЕНИЕ УСТАНОВКИ"

# 1. Сборка Docker образа
step_start "Сборка Docker образа"
(
    cd "$PROJECT_DIR"
    docker compose build > /dev/null 2>&1
) &
show_spinner $!
wait
step_done "Сборка Docker образа"

# 2. Создание .env файла
step_start "Настройка файлов бота"
cat > "$ENV_FILE" << EOF
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
SECRET_KEY=$(generate_key)
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
step_done "Настройка файлов бота"

# 3. Создание необходимых папок
step_start "Создание структуры папок"
mkdir -p "$PROJECT_DIR"/{logs,assets,backups}
step_done "Создание структуры папок"

# 4. Запуск контейнеров
step_start "Запуск сервисов"
(
    cd "$PROJECT_DIR"
    docker compose up -d > /dev/null 2>&1
) &
show_spinner $!
wait
step_done "Запуск сервисов"

# 5. Ожидание готовности БД
step_start "Инициализация базы данных"
sleep 10
step_done "Инициализация базы данных"

# 6. Удаление скрипта установки
rm -f "$PROJECT_DIR/server-setup.sh"

# ============================================================
# ЗАВЕРШЕНИЕ
# ============================================================

log_header "УСТАНОВКА И НАСТРОЙКА ЗАВЕРШЕНА"

echo -e "Место нахождения бота: ${GREEN}${PROJECT_DIR}${NC}\n"

log_success "Бот успешно установлен и запущен"
log_success "Домен: ${BOT_DOMAIN}"
log_success "Токен Telegram бота сохранён в .env"

echo ""
log_warning "Важные команды:"
echo -e "  ${CYAN}cd ${PROJECT_DIR}${NC}"
echo -e "  ${CYAN}docker compose logs -f${NC}              # Просмотр логов"
echo -e "  ${CYAN}docker compose down${NC}                 # Остановка"
echo -e "  ${CYAN}docker compose up -d${NC}                # Запуск"

echo ""
