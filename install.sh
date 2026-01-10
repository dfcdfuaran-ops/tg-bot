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

# Режим установки: dev или prod
INSTALL_MODE="dev"
if [ "$1" = "--prod" ] || [ "$1" = "-p" ]; then
    INSTALL_MODE="prod"
fi

if [ "$INSTALL_MODE" = "prod" ]; then
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║      Быстрая установка Remnashop Bot - PRODUCTION (v1.0)   ║${NC}"
    echo -e "${BLUE}║                                                            ║${NC}"
    echo -e "${BLUE}║  Режим: Установка на сервер (готовый Docker образ)       ║${NC}"
    echo -e "${BLUE}║  Используется: docker-compose.production.yml              ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
else
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║      Быстрая установка Remnashop Bot - DEVELOPMENT (v1.0) ║${NC}"
    echo -e "${BLUE}║                                                            ║${NC}"
    echo -e "${BLUE}║  Режим: Локальная разработка (с монтированием src)        ║${NC}"
    echo -e "${BLUE}║  Используется: docker-compose.yml                         ║${NC}"
    echo -e "${BLUE}║                                                            ║${NC}"
    echo -e "${BLUE}║  Для установки на сервер: ./install.sh --prod             ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
fi
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

read_webhook_secret() {
    local remnawave_env="/opt/remnawave/.env"
    
    if [ -f "$remnawave_env" ]; then
        local secret=$(grep "^WEBHOOK_SECRET_HEADER=" "$remnawave_env" | cut -d'=' -f2)
        if [ -n "$secret" ]; then
            echo "$secret"
            return
        fi
    fi
    
    # Если не найдено в файле, просим ввести вручную
    read_input "REMNAWAVE_WEBHOOK_SECRET"
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

configure_reverse_proxy() {
    local app_domain="$1"
    local choice="$2"
    
    if [ "$choice" = "caddy" ]; then
        configure_caddy "$app_domain"
    elif [ "$choice" = "nginx" ]; then
        configure_nginx "$app_domain"
    fi
}

configure_caddy() {
    local app_domain="$1"
    local caddy_file="/opt/remnawave/caddy/Caddyfile"
    
    if [ ! -f "$caddy_file" ]; then
        log_warning "Файл Caddyfile не найден в /opt/remnawave/caddy/"
        return
    fi
    
    # Проверить, есть ли уже конфигурация для этого домена
    if grep -q "https://${app_domain}" "$caddy_file"; then
        log_warning "Конфигурация для домена $app_domain уже существует в Caddyfile"
        return
    fi
    
    log_info "Добавляю конфигурацию в Caddyfile..."
    
    # Добавить конфигурацию в Caddyfile
    echo "" >> "$caddy_file"
    echo "https://${app_domain} {" >> "$caddy_file"
    echo "    reverse_proxy * http://remnashop:5000" >> "$caddy_file"
    echo "}" >> "$caddy_file"
    
    log_success "Конфигурация Caddy добавлена"
    log_info "Перезапустите Caddy для применения изменений:"
    log_info "  docker compose -f /opt/remnawave/caddy/docker-compose.yml restart caddy"
}

configure_nginx() {
    local app_domain="$1"
    local nginx_config="/etc/nginx/sites-available/${app_domain}.remnashop"
    
    log_warning "Nginx конфигурация требует ручной настройки"
    log_info "Создайте файл конфигурации: $nginx_config"
    log_info ""
    log_info "Пример конфигурации:"
    cat << 'EOF'
    
upstream remnashop {
    server localhost:5000;
}

server {
    listen 80;
    server_name APP_DOMAIN;
    
    location / {
        proxy_pass http://remnashop;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
    log_info ""
    log_info "После создания файла выполните:"
    log_info "  sudo ln -s /etc/nginx/sites-available/${app_domain}.remnashop /etc/nginx/sites-enabled/"
    log_info "  sudo nginx -t"
    log_info "  sudo systemctl restart nginx"
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
# ВЫБОР РЕВЕРС-ПРОКСИ
# ============================================================

log_info "Выберите реверс-прокси:"
echo "  1) Caddy (рекомендуется)"
echo "  2) Nginx"
echo "  3) Пропустить (ручная настройка)"
read -p "  Выбор [1-3]: " proxy_choice

case $proxy_choice in
    1)
        REVERSE_PROXY="caddy"
        log_success "Выбран Caddy"
        ;;
    2)
        REVERSE_PROXY="nginx"
        log_success "Выбран Nginx"
        ;;
    *)
        REVERSE_PROXY="none"
        log_info "Конфигурация реверс-прокси пропущена"
        ;;
esac

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
REMNAWAVE_WEBHOOK_SECRET=$(read_webhook_secret)
if [ -z "$REMNAWAVE_WEBHOOK_SECRET" ]; then
    log_error "REMNAWAVE_WEBHOOK_SECRET не может быть пустым!"
    exit 1
fi
sed -i "s|^REMNAWAVE_WEBHOOK_SECRET=.*|REMNAWAVE_WEBHOOK_SECRET=${REMNAWAVE_WEBHOOK_SECRET}|" "$ENV_FILE"

if [ -f "/opt/remnawave/.env" ] && grep -q "^WEBHOOK_SECRET_HEADER=$REMNAWAVE_WEBHOOK_SECRET" "/opt/remnawave/.env"; then
    log_success "REMNAWAVE_WEBHOOK_SECRET загружен из /opt/remnawave/.env"
else
    log_warning "REMNAWAVE_WEBHOOK_SECRET введен вручную"
fi

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
COMPOSE_FILE="docker-compose.yml"
if [ "$INSTALL_MODE" = "prod" ]; then
    COMPOSE_FILE="docker-compose.production.yml"
fi
docker compose -f "$PROJECT_DIR/$COMPOSE_FILE" down -v 2>/dev/null || true

# Удалить старый образ
log_info "Удаление старого образа..."
docker rmi remnashop:local -f 2>/dev/null || true

# Очистить кэш
docker buildx prune -af 2>/dev/null || true

echo ""

# ============================================================
# КОНФИГУРАЦИЯ РЕВЕРС-ПРОКСИ
# ============================================================

if [ "$REVERSE_PROXY" != "none" ]; then
    log_info "Конфигурация реверс-прокси..."
    configure_reverse_proxy "$APP_DOMAIN" "$REVERSE_PROXY"
    echo ""
    
    if [ "$REVERSE_PROXY" = "caddy" ]; then
        log_info "Перезапуск Caddy для применения изменений..."
        docker compose -f "/opt/remnawave/caddy/docker-compose.yml" restart caddy 2>/dev/null || log_warning "Не удалось перезапустить Caddy (проверьте, запущен ли он)"
        log_success "Caddy перезапущен"
        echo ""
    fi
fi

log_info "Сборка Docker образа..."
if [ "$INSTALL_MODE" = "prod" ]; then
    log_info "В режиме production образ загружается с GitHub Container Registry"
    log_warning "Убедитесь, что образ ghcr.io/dfteams/remna-tg-bot:latest опубликован!"
else
    docker compose -f "$PROJECT_DIR/docker-compose.yml" build --no-cache 2>&1 | tail -20
fi

echo ""
log_info "Запуск проекта через Docker Compose..."
docker compose -f "$PROJECT_DIR/$COMPOSE_FILE" up -d

echo ""
log_success "Проект запущен!"
echo ""

# ============================================================
# ОЧИСТКА НЕНУЖНЫХ ФАЙЛОВ НА СЕРВЕРЕ
# ============================================================

log_info "Очистка сервера от ненужных файлов..."

# Список файлов и папок для удаления
FILES_TO_REMOVE=(
    "BACKUP_RESTORE_GUIDE.md"
    "CHANGES_SUMMARY.md"
    "DETAILED_EXPLANATION.md"
    "INSTALL_RU.md"
    "INVITE_FIX.md"
    "README.md"
    "Makefile"
    "Dockerfile"
    "pyproject.toml"
    "uv.lock"
    "install.sh"
    "src/"
    "scripts/"
    "docs/"
    ".env.example"
    ".gitignore"
    ".dockerignore"
    ".git/"
)

for file in "${FILES_TO_REMOVE[@]}"; do
    if [ -e "$PROJECT_DIR/$file" ]; then
        rm -rf "$PROJECT_DIR/$file"
        log_success "Удален: $file"
    fi
done

echo ""
log_success "Сервер очищен от ненужных файлов"
echo ""

# ============================================================
# ИНФОРМАЦИЯ О ЗАВЕРШЕНИИ
# ============================================================

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                  УСТАНОВКА ЗАВЕРШЕНА ✓                    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
if [ "$INSTALL_MODE" = "prod" ]; then
    echo -e "📁 Проект расположен в: ${YELLOW}$PROJECT_DIR${NC}"
    echo -e "📋 Конфигурация сохранена в: ${YELLOW}$ENV_FILE${NC}"
    echo -e "🌐 Реверс-прокси: ${YELLOW}${REVERSE_PROXY^^}${NC}"
    echo -e "🐳 Режим: ${YELLOW}PRODUCTION (готовый образ)${NC}"
    echo ""
    echo -e "📁 В папке проекта остались только необходимые файлы:"
    echo -e "   ${YELLOW}.env${NC} - конфигурация"
    echo -e "   ${YELLOW}docker-compose.production.yml${NC} - конфиг Docker"
    echo -e "   ${YELLOW}assets/${NC} - ассеты бота"
    echo -e "   ${YELLOW}logs/${NC} - логи"
    echo -e "   ${YELLOW}backups/${NC} - бэкапы БД"
    echo ""
else
    echo -e "📁 Проект расположен в: ${YELLOW}$PROJECT_DIR${NC}"
    echo -e "📋 Конфигурация сохранена в: ${YELLOW}$ENV_FILE${NC}"
    echo -e "🌐 Реверс-прокси: ${YELLOW}${REVERSE_PROXY^^}${NC}"
    echo -e "🐳 Режим: ${YELLOW}DEVELOPMENT (с монтированием src)${NC}"
    echo ""
fi
echo -e "🔍 Проверка логов:"
echo -e "   ${YELLOW}docker compose -f $PROJECT_DIR/$COMPOSE_FILE logs -f${NC}"
echo ""

if [ "$REVERSE_PROXY" = "caddy" ]; then
    echo -e "📋 Логи Caddy:"
    echo -e "   ${YELLOW}docker compose -f /opt/remnawave/caddy/docker-compose.yml logs -f${NC}"
    echo ""
fi

echo -e "🛑 Остановка проекта:"
echo -e "   ${YELLOW}docker compose -f $PROJECT_DIR/$COMPOSE_FILE down${NC}"
echo ""
echo -e "ℹ️  Документация: ${YELLOW}$PROJECT_DIR/README.md${NC}"
echo ""
