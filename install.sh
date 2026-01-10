#!/bin/bash
# version: 1.0.0
# TG-SELL-BOT Installation Script

set -e
exec < /dev/tty

# Скрыть курсор
tput civis >/dev/null 2>&1 || true

# Цвета
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
WHITE='\033[1;37m'
NC='\033[0m'
DARKGRAY='\033[1;30m'

# Показать курсор при выходе
trap 'tput cnorm >/dev/null 2>&1 || true; tput sgr0 >/dev/null 2>&1 || true' EXIT

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
  tput civis 2>/dev/null || true
  while kill -0 $pid 2>/dev/null; do
    printf "\r${GREEN}%s${NC}  %s" "${spin[$i]}" "$msg"
    i=$(( (i+1) % 10 ))
    sleep $delay
  done
  printf "\r${GREEN}✅${NC} %s\n" "$msg"
  tput cnorm 2>/dev/null || true
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
echo -e "${GREEN}                  🚀 УСТАНОВКА TG-SELL-BOT${NC}"
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
# АВТООПРЕДЕЛЕНИЕ РЕВЕРС-ПРОКСИ
# ============================================================

if [ -d "/opt/remnawave/caddy" ]; then
  REVERSE_PROXY="caddy"
  print_success "Обнаружен реверс прокси Caddy"
  print_success "Применен вариант установки для Caddy\n"
elif [ -d "/opt/remnawave/nginx" ]; then
  REVERSE_PROXY="nginx"
  print_success "Обнаружен реверс прокси Nginx"
  print_success "Применен вариант установки для Nginx\n"
else
  REVERSE_PROXY="none"
  print_success "Реверс-прокси не обнаружен"
  print_success "Установка будет выполнена без настройки прокси\n"
fi

# ============================================================
# ПОЛУЧЕНИЕ ДАННЫХ ОТ ПОЛЬЗОВАТЕЛЯ
# ============================================================

echo -e "${BLUE}========================================${NC}"
echo -e "${WHITE}             ⚙️ НАСТРОЙКА КОНФИГУРАЦИИ БОТА${NC}"
echo -e "${BLUE}========================================${NC}\n"

safe_read "${YELLOW}➜ Введите домен бота (напр. bot.example.com):${NC} " BOT_DOMAIN
safe_read "${YELLOW}➜ Введите Токен телеграм бота:${NC} " BOT_TOKEN
safe_read "${YELLOW}➜ Введите телеграм ID разработчика:${NC} " ADMIN_ID
safe_read "${YELLOW}➜ Введите username группы поддержки (без @):${NC} " SUPPORT_CHANNEL
safe_read "${YELLOW}➜ Введите Токен Remnawave:${NC} " REMNAWAVE_TOKEN

touch "$LOCK_FILE"

echo

# ============================================================
# ВЫПОЛНЕНИЕ УСТАНОВКИ
# ============================================================

echo -e "${BLUE}========================================${NC}"
echo -e "${WHITE}                       ⚡ ПРОЦЕСС УСТАНОВКИ${NC}"
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
BOT_SECRET_TOKEN=$(openssl rand -hex 32)
BOT_DEV_ID=$ADMIN_ID
BOT_SUPPORT_USERNAME=$SUPPORT_CHANNEL

APP_DOMAIN=$BOT_DOMAIN
APP_CRYPT_KEY=$(openssl rand -base64 32 | tr -d '\n')

# Database Configuration
DATABASE_USER=remnashop
DATABASE_PASSWORD=$(openssl rand -hex 16)
DATABASE_NAME=remnashop
DATABASE_HOST=remnashop-db
DATABASE_PORT=5432

# Redis Configuration
REDIS_PASSWORD=$(openssl rand -hex 16)
REDIS_HOST=remnashop-redis
REDIS_PORT=6379

# Remnawave Configuration
REMNAWAVE_TOKEN=$REMNAWAVE_TOKEN
REMNAWAVE_WEBHOOK_SECRET=$(openssl rand -hex 32)

# Application Settings
APP_ENV=production
APP_DEBUG=false
APP_LOG_LEVEL=info

# Asset Settings
APP_RESET_ASSETS=false
EOF
) &
show_spinner "Создание конфигурации"

# 3. Создание папок для данных
(
  mkdir -p "$INSTALL_DIR"/{assets,backups,logs}
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

# 6. Удаление ненужных файлов и папок
(
  # Оставить только: assets, backups, logs, .env, docker-compose.yml
  # Удалить исходный код
  rm -rf "$INSTALL_DIR"/src 2>/dev/null || true
  # Удалить скрипты и документацию
  rm -rf "$INSTALL_DIR"/{scripts,docs} 2>/dev/null || true
  # Удалить гит и посредные файлы
  rm -rf "$INSTALL_DIR"/.git 2>/dev/null || true
  rm -rf "$INSTALL_DIR"/.venv 2>/dev/null || true
  rm -rf "$INSTALL_DIR"/__pycache__ 2>/dev/null || true
  # Удалить конфигурационные и служебные файлы
  rm -f "$INSTALL_DIR"/{.gitignore,.dockerignore,.env.example,.python-version,.editorconfig} 2>/dev/null || true
  rm -f "$INSTALL_DIR"/{Makefile,pyproject.toml,uv.lock} 2>/dev/null || true
  rm -f "$INSTALL_DIR"/{install.sh,uninstall.sh} 2>/dev/null || true
  rm -f "$INSTALL_DIR"/{README.md,INSTALL_RU.md,BACKUP_RESTORE_GUIDE.md,CHANGES_SUMMARY.md,DETAILED_EXPLANATION.md,INVITE_FIX.md} 2>/dev/null || true
  rm -f "$LOCK_FILE"
) &
show_spinner "Очистка остаточных файлов"

echo

# ============================================================
# ЗАВЕРШЕНИЕ УСТАНОВКИ
# ============================================================

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}             🎉 УСТАНОВКА ЗАВЕРШЕНА УСПЕШНО!${NC}"
echo -e "${BLUE}========================================${NC}\n"

print_success "Бот успешно установлен и запущен"
print_success "Домен: $BOT_DOMAIN"
print_success "Место нахождения: ${YELLOW}$INSTALL_DIR${NC}"

echo
echo -e "${BLUE}========================================${NC}\n"

print_success "Конфигурация сохранена в: ${YELLOW}$INSTALL_DIR/.env${NC}"
print_success "Логи доступны через: ${YELLOW}docker compose logs${NC}"

echo

cd /opt
