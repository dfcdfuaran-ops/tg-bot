#!/bin/bash
set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Путь к .env файлу
ENV_FILE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.env"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║        Быстрая установка Remnashop Bot (v1.0)             ║${NC}"
echo -e "${BLUE}║                                                            ║${NC}"
echo -e "${BLUE}║  Скрипт автоматически создаст .env и запустит проект     ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================
# ФУНКЦИИ
# ============================================================

log_info() {
    echo -e "${BLUE}ℹ ${NC}$1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

read_input() {
    local prompt="$1"
    local default="$2"
    local input
    
    if [ -z "$default" ]; then
        read -p "  $(echo -e ${YELLOW})$prompt:$(echo -e ${NC}) " input
    else
        read -p "  $(echo -e ${YELLOW})$prompt${NC} [${default}]: " input
        input="${input:-$default}"
    fi
    
    echo "$input"
}

generate_token() {
    openssl rand -hex 64 | tr -d '\n'
}

generate_password() {
    openssl rand -hex 32 | tr -d '\n'
}

generate_key() {
    openssl rand -base64 32 | tr -d '\n'
}

# ============================================================
# ПРОВЕРКИ ПРЕДУСЛОВИЙ
# ============================================================

log_info "Проверка предусловий..."

if ! command -v docker &> /dev/null; then
    log_error "Docker не установлен!"
    exit 1
fi

if ! command -v openssl &> /dev/null; then
    log_error "OpenSSL не установлен!"
    exit 1
fi

log_success "Docker и OpenSSL доступны"
echo ""

# ============================================================
# ПОДГОТОВКА ОКРУЖЕНИЯ
# ============================================================

log_info "Подготовка окружения..."

mkdir -p "$PROJECT_DIR/logs"
mkdir -p "$PROJECT_DIR/backups"
mkdir -p "$PROJECT_DIR/assets"
chmod 755 "$PROJECT_DIR/logs" "$PROJECT_DIR/backups" "$PROJECT_DIR/assets"

if ! docker network ls | grep -q "remnawave-network"; then
    log_info "Создание Docker сети remnawave-network..."
    docker network create remnawave-network 2>/dev/null || true
fi

log_success "Окружение подготовлено"
echo ""

# ============================================================
# СОЗДАНИЕ .env ФАЙЛА
# ============================================================

if [ ! -f "$ENV_FILE" ]; then
    log_info "Файл .env не найден. Создание на основе .env.example..."
    
    if [ ! -f "$PROJECT_DIR/.env.example" ]; then
        log_error "Файл .env.example не найден!"
        exit 1
    fi
    
    cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
    log_success "Файл .env создан"
else
    log_warning "Файл .env уже существует. Обновление параметров..."
fi

echo ""

# ============================================================
# ВВОД ОБЯЗАТЕЛЬНЫХ ПАРАМЕТРОВ
# ============================================================

log_info "Введите обязательные параметры конфигурации:"
echo ""

# APP_DOMAIN
APP_DOMAIN=$(read_input "Домен бота")
if [ -z "$APP_DOMAIN" ]; then
    log_error "Домен не может быть пустым!"
    exit 1
fi
sed -i "s|^APP_DOMAIN=.*|APP_DOMAIN=${APP_DOMAIN}|" "$ENV_FILE"

# BOT_TOKEN
echo ""
log_warning "Для получения BOT_TOKEN перейдите на https://t.me/BotFather"
BOT_TOKEN=$(read_input "Telegram BOT_TOKEN")
if [ -z "$BOT_TOKEN" ]; then
    log_error "BOT_TOKEN не может быть пустым!"
    exit 1
fi
sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=${BOT_TOKEN}|" "$ENV_FILE"

# BOT_DEV_ID
BOT_DEV_ID=$(read_input "Ваш Telegram ID (для прав разработчика)")
if [ -z "$BOT_DEV_ID" ]; then
    log_error "BOT_DEV_ID не может быть пустым!"
    exit 1
fi
sed -i "s|^BOT_DEV_ID=.*|BOT_DEV_ID=${BOT_DEV_ID}|" "$ENV_FILE"

# BOT_SUPPORT_USERNAME
BOT_SUPPORT_USERNAME=$(read_input "Username аккаунта поддержки (без @)" "support_bot")
sed -i "s|^BOT_SUPPORT_USERNAME=.*|BOT_SUPPORT_USERNAME=${BOT_SUPPORT_USERNAME}|" "$ENV_FILE"

# REMNAWAVE_TOKEN
echo ""
log_warning "REMNAWAVE_TOKEN можно получить из админ-панели Remnawave"
REMNAWAVE_TOKEN=$(read_input "REMNAWAVE_TOKEN")
if [ -z "$REMNAWAVE_TOKEN" ]; then
    log_error "REMNAWAVE_TOKEN не может быть пустым!"
    exit 1
fi
sed -i "s|^REMNAWAVE_TOKEN=.*|REMNAWAVE_TOKEN=${REMNAWAVE_TOKEN}|" "$ENV_FILE"

# REMNAWAVE_WEBHOOK_SECRET
REMNAWAVE_WEBHOOK_SECRET=$(read_input "REMNAWAVE_WEBHOOK_SECRET")
if [ -z "$REMNAWAVE_WEBHOOK_SECRET" ]; then
    log_error "REMNAWAVE_WEBHOOK_SECRET не может быть пустым!"
    exit 1
fi
sed -i "s|^REMNAWAVE_WEBHOOK_SECRET=.*|REMNAWAVE_WEBHOOK_SECRET=${REMNAWAVE_WEBHOOK_SECRET}|" "$ENV_FILE"

echo ""

# ============================================================
# АВТОГЕНЕРАЦИЯ КЛЮЧЕЙ И ПАРОЛЕЙ
# ============================================================

log_info "Автоматическая генерация ключей и паролей..."

if grep -q "^APP_CRYPT_KEY=$" "$ENV_FILE"; then
    APP_CRYPT_KEY=$(generate_key)
    sed -i "s|^APP_CRYPT_KEY=.*|APP_CRYPT_KEY=${APP_CRYPT_KEY}|" "$ENV_FILE"
    log_success "APP_CRYPT_KEY сгенерирован"
fi

if grep -q "^BOT_SECRET_TOKEN=$" "$ENV_FILE"; then
    BOT_SECRET_TOKEN=$(generate_token)
    sed -i "s|^BOT_SECRET_TOKEN=.*|BOT_SECRET_TOKEN=${BOT_SECRET_TOKEN}|" "$ENV_FILE"
    log_success "BOT_SECRET_TOKEN сгенерирован"
fi

if grep -q "^DATABASE_PASSWORD=$" "$ENV_FILE"; then
    DATABASE_PASSWORD=$(generate_password)
    sed -i "s|^DATABASE_PASSWORD=.*|DATABASE_PASSWORD=${DATABASE_PASSWORD}|" "$ENV_FILE"
    log_success "DATABASE_PASSWORD сгенерирован"
fi

if grep -q "^REDIS_PASSWORD=$" "$ENV_FILE"; then
    REDIS_PASSWORD=$(generate_password)
    sed -i "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=${REDIS_PASSWORD}|" "$ENV_FILE"
    log_success "REDIS_PASSWORD сгенерирован"
fi

echo ""

# ============================================================
# ЗАПУСК ПРОЕКТА
# ============================================================

log_info "Подготовка к запуску проекта..."

# Остановить старые контейнеры
log_info "Остановка старых контейнеров..."
docker compose -f "$PROJECT_DIR/docker-compose.yml" down -v 2>/dev/null || true

# Удалить старый образ
log_info "Удаление старого образа..."
docker rmi remnashop:local -f 2>/dev/null || true

# Очистить кэш
docker buildx prune -af 2>/dev/null || true

echo ""
log_info "Запуск проекта через Docker Compose..."
docker compose -f "$PROJECT_DIR/docker-compose.yml" up -d

echo ""
log_success "Проект запущен!"
echo ""

# ============================================================
# ИНФОРМАЦИЯ О ЗАВЕРШЕНИИ
# ============================================================

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                  УСТАНОВКА ЗАВЕРШЕНА ✓                    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "📁 Проект расположен в: ${YELLOW}$PROJECT_DIR${NC}"
echo -e "📋 Конфигурация сохранена в: ${YELLOW}$ENV_FILE${NC}"
echo ""
echo -e "🔍 Проверка логов:"
echo -e "   ${YELLOW}docker compose -f $PROJECT_DIR/docker-compose.yml logs -f${NC}"
echo ""
echo -e "🛑 Остановка проекта:"
echo -e "   ${YELLOW}docker compose -f $PROJECT_DIR/docker-compose.yml down${NC}"
echo ""
echo -e "ℹ️  Документация: ${YELLOW}$PROJECT_DIR/README.md${NC}"
echo ""
