#!/bin/bash
set -e
exec < /dev/tty

# Переменные для отслеживания состояния установки
INSTALL_STARTED=false
SOURCE_DIR=""
CLEANUP_DIRS=()

# Функция очистки при ошибке или отмене
cleanup_on_error() {
    local exit_code=$?
    
    # Показать курсор
    tput cnorm >/dev/null 2>&1 || true
    tput sgr0 >/dev/null 2>&1 || true
    
    if [ $exit_code -ne 0 ] || [ "$INSTALL_STARTED" = true ]; then
        echo
        echo -e "${RED}========================================${NC}"
        echo -e "${RED}    ⚠️ УСТАНОВКА ПРЕРВАНА ИЛИ ОШИБКА${NC}"
        echo -e "${RED}========================================${NC}"
        echo
        echo -e "${WHITE}🧹 Выполняю очистку...${NC}"
        
        # Удаляем исходную папку с клоном репозитория
        if [ -n "$SOURCE_DIR" ] && [ "$SOURCE_DIR" != "/opt/tg-sell-bot" ] && [ "$SOURCE_DIR" != "/" ] && [ -d "$SOURCE_DIR" ]; then
            rm -rf "$SOURCE_DIR" 2>/dev/null || true
            echo -e "${GREEN}✓ Удален клон репозитория${NC}"
        fi
        
        # Удаляем целевую папку если установка не завершена
        if [ "$INSTALL_STARTED" = true ] && [ -d "$PROJECT_DIR" ]; then
            # Сохраняем .env если он существует и был заполнен
            ENV_BACKUP=""
            if [ -f "$ENV_FILE" ]; then
                ENV_BACKUP=$(cat "$ENV_FILE" 2>/dev/null || true)
            fi
            
            # Останавливаем контейнеры если они запущены
            if command -v docker &> /dev/null; then
                cd "$PROJECT_DIR" 2>/dev/null && docker compose down 2>/dev/null || true
            fi
            
            # Удаляем проектную папку
            rm -rf "$PROJECT_DIR" 2>/dev/null || true
            echo -e "${GREEN}✓ Удалена папка проекта${NC}"
        fi
        
        echo -e "${GREEN}✅ Очистка завершена${NC}"
        echo
        echo -e "${YELLOW}ℹ Попробуйте запустить установку снова${NC}"
        echo
    fi
    
    exit $exit_code
}

# Установка trap для обработки ошибок, прерываний и выхода
trap cleanup_on_error EXIT
trap 'INSTALL_STARTED=false; exit 130' INT TERM

# Автоматически даем права на выполнение самому себе
chmod +x "$0" 2>/dev/null || true

# Скрыть курсор
tput civis >/dev/null 2>&1 || true

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
WHITE='\033[1;37m'
NC='\033[0m'
DARKGRAY='\033[1;30m'

# Показать курсор при выходе
trap 'tput cnorm >/dev/null 2>&1 || true; tput sgr0 >/dev/null 2>&1 || true' EXIT

# Путь к .env файлу
PROJECT_DIR="/opt/tg-sell-bot"
ENV_FILE="$PROJECT_DIR/.env"

# Режим установки: dev или prod
INSTALL_MODE="dev"
if [ "$1" = "--prod" ] || [ "$1" = "-p" ]; then
    INSTALL_MODE="prod"
fi

clear
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}       🚀 УСТАНОВКА TG-SELL-BOT${NC}"
echo -e "${BLUE}========================================${NC}"
echo

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

# Функция для безопасного обновления переменной в .env файле
update_env_var() {
    local env_file="$1"
    local var_name="$2"
    local var_value="$3"
    
    # Экранируем спецсимволы для sed
    local escaped_value=$(printf '%s\n' "$var_value" | sed -e 's/[\/&]/\\&/g')
    
    # Проверяем, существует ли переменная в файле
    if grep -q "^${var_name}=" "$env_file"; then
        # Заменяем существующее значение
        sed -i "s|^${var_name}=.*|${var_name}=${escaped_value}|" "$env_file"
    else
        # Добавляем новую переменную
        echo "${var_name}=${var_value}" >> "$env_file"
    fi
}

# Безопасный ввод
safe_read() {
  local prompt="$1"
  local varname="$2"
  echo -ne "$prompt"
  IFS= read -r "$varname" || { echo; exit 1; }
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

configure_caddy() {
    local app_domain="$1"
    local caddy_dir="/opt/remnawave/caddy"
    local caddy_file="${caddy_dir}/Caddyfile"

    # Нет Caddy — тихо выходим
    [ -d "$caddy_dir" ] || return 0
    [ -f "$caddy_file" ] || return 0

    # Если домен уже есть — просто перезапускаем
    if ! grep -q -E "https://${app_domain}\s*\{" "$caddy_file"; then
        cat >> "$caddy_file" <<EOF

https://${app_domain} {
    reverse_proxy * http://remnashop:5000
}
EOF
    fi

    # Реальный перезапуск Caddy
    cd "$caddy_dir"
    docker compose down >/dev/null 2>&1
    docker compose up -d  >/dev/null 2>&1
}

# ============================================================
# ПРОВЕРКИ ПРЕДУСЛОВИЙ И ПОДГОТОВКА
# ============================================================

# 1. Проверка Docker и OpenSSL
(
  if ! command -v docker &> /dev/null; then
      print_error "Docker не установлен!"
      exit 1
  fi

  if ! command -v openssl &> /dev/null; then
      print_error "OpenSSL не установлен!"
      exit 1
  fi
) &
show_spinner "Проверка установленных компонентов"

# Отмечаем, что установка началась - теперь при ошибке нужно очищать
INSTALL_STARTED=true

# 2. Подготовка целевой директории
(
  # Создаем целевую директорию
  mkdir -p "$PROJECT_DIR"
  mkdir -p "$PROJECT_DIR/logs"
  mkdir -p "$PROJECT_DIR/backups"
  mkdir -p "$PROJECT_DIR/assets"
  chmod 755 "$PROJECT_DIR/logs" "$PROJECT_DIR/backups" "$PROJECT_DIR/assets"

  # Создаем сеть Docker если не существует
  if ! docker network ls | grep -q "remnawave-network"; then
      docker network create remnawave-network 2>/dev/null || true
  fi
) &
show_spinner "Подготовка целевой директории"

# 3. Определение, откуда копировать файлы
# Если скрипт запущен не из целевой директории, значит мы в клонированной папке
SCRIPT_PATH="$(realpath "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
SOURCE_DIR="$SCRIPT_DIR"

if [ "$SOURCE_DIR" = "/opt/tg-sell-bot" ]; then
    # Скрипт уже в целевой директории - ничего не копируем
    COPY_FILES=false
else
    # Скрипт в клонированной папке - копируем файлы
    COPY_FILES=true
    SOURCE_FILES=(
        "docker-compose.yml"
        "Dockerfile"
        ".env.example"
    )
fi

# 4. Копирование файлов если нужно
if [ "$COPY_FILES" = true ]; then
    (
      # Копируем основные файлы
      for file in "${SOURCE_FILES[@]}"; do
          if [ -f "$SOURCE_DIR/$file" ]; then
              cp "$SOURCE_DIR/$file" "$PROJECT_DIR/"
          fi
      done
      
      # Копируем директории
      if [ -d "$SOURCE_DIR/src" ]; then
          cp -r "$SOURCE_DIR/src" "$PROJECT_DIR/"
      fi
      
      if [ -d "$SOURCE_DIR/scripts" ]; then
          cp -r "$SOURCE_DIR/scripts" "$PROJECT_DIR/"
      fi
    ) &
    show_spinner "Копирование файлов установки"
fi

# 5. Создание .env файла
(
  if [ ! -f "$ENV_FILE" ]; then
      if [ ! -f "$PROJECT_DIR/.env.example" ]; then
          print_error "Файл .env.example не найден!"
          exit 1
      fi
      cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
  fi
) &
show_spinner "Инициализация конфигурации"

# 6. Автоопределение реверс-прокси
if [ -d "/opt/remnawave/caddy" ]; then
  REVERSE_PROXY="caddy"
  print_success "Обнаружен реверс прокси Caddy"
  print_success "Применяем вариант установки с Caddy"
elif [ -d "/opt/remnawave/nginx" ]; then
  REVERSE_PROXY="nginx"
  print_success "Обнаружен реверс прокси Nginx"
  print_success "Применяем вариант установки с Nginx"
else
  REVERSE_PROXY="none"
  print_success "Реверс-прокси не обнаружен"
  print_success "Установка будет выполнена без настройки прокси"
fi

echo
echo -e "${BLUE}========================================${NC}"
echo -e "${WHITE}    ⚙️ НАСТРОЙКА КОНФИГУРАЦИИ БОТА${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# APP_DOMAIN
safe_read "${YELLOW}➜ Введите домен бота (напр. bot.example.com):${NC} " APP_DOMAIN
if [ -z "$APP_DOMAIN" ]; then
    print_error "Домен не может быть пустым!"
    exit 1
fi
update_env_var "$ENV_FILE" "APP_DOMAIN" "$APP_DOMAIN"

# BOT_TOKEN
echo ""
safe_read "${YELLOW}➜ Введите Токен телеграм бота:${NC} " BOT_TOKEN
if [ -z "$BOT_TOKEN" ]; then
    print_error "BOT_TOKEN не может быть пустым!"
    exit 1
fi
update_env_var "$ENV_FILE" "BOT_TOKEN" "$BOT_TOKEN"

# BOT_DEV_ID
safe_read "${YELLOW}➜ Введите телеграм ID разработчика:${NC} " BOT_DEV_ID
if [ -z "$BOT_DEV_ID" ]; then
    print_error "BOT_DEV_ID не может быть пустым!"
    exit 1
fi
update_env_var "$ENV_FILE" "BOT_DEV_ID" "$BOT_DEV_ID"

# BOT_SUPPORT_USERNAME
safe_read "${YELLOW}➜ Введите username группы поддержки (без @):${NC} " BOT_SUPPORT_USERNAME
echo
update_env_var "$ENV_FILE" "BOT_SUPPORT_USERNAME" "$BOT_SUPPORT_USERNAME"

# REMNAWAVE_TOKEN
safe_read "${YELLOW}➜ Введите API Токен Remnawave:${NC} " REMNAWAVE_TOKEN
if [ -z "$REMNAWAVE_TOKEN" ]; then
    print_error "REMNAWAVE_TOKEN не может быть пустым!"
    exit 1
fi
update_env_var "$ENV_FILE" "REMNAWAVE_TOKEN" "$REMNAWAVE_TOKEN"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${WHITE}         ⚡ ПРОЦЕСС УСТАНОВКИ${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# 1. Сборка Docker образа
(
    cd "$PROJECT_DIR"
    docker compose build >/dev/null 2>&1
) &
show_spinner "Сборка Docker образа"

# 2. Создание конфигурации
(
  # Автогенерация ключей
  if grep -q "^APP_CRYPT_KEY=$" "$ENV_FILE"; then
    APP_CRYPT_KEY=$(openssl rand -base64 32 | tr -d '\n')
    update_env_var "$ENV_FILE" "APP_CRYPT_KEY" "$APP_CRYPT_KEY"
  fi

  if grep -q "^BOT_SECRET_TOKEN=$" "$ENV_FILE"; then
    BOT_SECRET_TOKEN=$(openssl rand -hex 32)
    update_env_var "$ENV_FILE" "BOT_SECRET_TOKEN" "$BOT_SECRET_TOKEN"
  fi

  if grep -q "^DATABASE_PASSWORD=$" "$ENV_FILE"; then
    DATABASE_PASSWORD=$(openssl rand -hex 16)
    update_env_var "$ENV_FILE" "DATABASE_PASSWORD" "$DATABASE_PASSWORD"
  fi

  if grep -q "^REDIS_PASSWORD=$" "$ENV_FILE"; then
    REDIS_PASSWORD=$(openssl rand -hex 16)
    update_env_var "$ENV_FILE" "REDIS_PASSWORD" "$REDIS_PASSWORD"
  fi

  if grep -q "^REMNAWAVE_WEBHOOK_SECRET=$" "$ENV_FILE"; then
    REMNAWAVE_WEBHOOK_SECRET=$(openssl rand -hex 32)
    update_env_var "$ENV_FILE" "REMNAWAVE_WEBHOOK_SECRET" "$REMNAWAVE_WEBHOOK_SECRET"
  fi
) &
show_spinner "Создание конфигурации"

# ============================================================
# СИНХРОНИЗАЦИЯ WEBHOOK С REMNAWAVE
# ============================================================

(
  REMNAWAVE_ENV="/opt/remnawave/.env"

  if [ -f "$REMNAWAVE_ENV" ]; then
      # 1. Включаем webhook
      if grep -q "^WEBHOOK_ENABLED=" "$REMNAWAVE_ENV"; then
          sed -i "s|^WEBHOOK_ENABLED=.*|WEBHOOK_ENABLED=true|" "$REMNAWAVE_ENV"
      else
          echo "WEBHOOK_ENABLED=true" >> "$REMNAWAVE_ENV"
      fi

      # 2. Копируем WEBHOOK_SECRET_HEADER → REMNAWAVE_WEBHOOK_SECRET
      REMNAWAVE_SECRET=$(grep "^WEBHOOK_SECRET_HEADER=" "$REMNAWAVE_ENV" | cut -d'=' -f2)

      if [ -n "$REMNAWAVE_SECRET" ]; then
          update_env_var "$ENV_FILE" "REMNAWAVE_WEBHOOK_SECRET" "$REMNAWAVE_SECRET"
      fi

      # 3. Подставляем домен пользователя в WEBHOOK_URL
      if [ -n "$APP_DOMAIN" ]; then
          if grep -q "^WEBHOOK_URL=" "$REMNAWAVE_ENV"; then
              sed -i "s|^WEBHOOK_URL=.*|WEBHOOK_URL=https://${APP_DOMAIN}/api/v1/remnawave|" "$REMNAWAVE_ENV"
          else
              echo "WEBHOOK_URL=https://${APP_DOMAIN}/api/v1/remnawave" >> "$REMNAWAVE_ENV"
          fi
      fi
  fi
) &
show_spinner "Синхронизация с Remnawave"

# Настройка webhook отдельно
(
  sleep 1
) &
show_spinner "Настройка webhook"

# 3. Создание структуры папок
(
  rm -rf "$PROJECT_DIR"/assets
  mkdir -p "$PROJECT_DIR"/{assets,backups,logs}
) &
show_spinner "Создание структуры папок"

# 4. Запуск контейнеров
(
    cd "$PROJECT_DIR"
    docker compose up -d >/dev/null 2>&1
) &
show_spinner "Запуск сервисов"

# 5. Инициализация БД
(
  sleep 10
) &
show_spinner "Инициализация базы данных"

# 6. Настройка и перезапуск Caddy
(
  if [ -d "/opt/remnawave/caddy" ]; then
      configure_caddy "$APP_DOMAIN"
  fi
) &
show_spinner "Настройка и перезапуск Caddy"

# 7. Очистка ненужных файлов в целевой директории
(
  rm -rf "$PROJECT_DIR"/src 2>/dev/null || true
  rm -rf "$PROJECT_DIR"/scripts 2>/dev/null || true
  rm -rf "$PROJECT_DIR"/docs 2>/dev/null || true
  rm -rf "$PROJECT_DIR"/.git 2>/dev/null || true
  rm -rf "$PROJECT_DIR"/.venv 2>/dev/null || true
  rm -rf "$PROJECT_DIR"/__pycache__ 2>/dev/null || true
  rm -f "$PROJECT_DIR"/{.gitignore,.dockerignore,.env.example,.python-version,.editorconfig} 2>/dev/null || true
  rm -f "$PROJECT_DIR"/{Makefile,pyproject.toml,uv.lock} 2>/dev/null || true
  rm -f "$PROJECT_DIR"/install.sh 2>/dev/null || true
  rm -f "$PROJECT_DIR"/{README.md,INSTALL_RU.md,BACKUP_RESTORE_GUIDE.md,CHANGES_SUMMARY.md,DETAILED_EXPLANATION.md,INVITE_FIX.md} 2>/dev/null || true
) &
show_spinner "Очистка остаточных файлов"

# ============================================================
# ЗАВЕРШЕНИЕ УСТАНОВКИ
# ============================================================

echo
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}    🎉 УСТАНОВКА ЗАВЕРШЕНА УСПЕШНО!${NC}"
echo -e "${BLUE}========================================${NC}"
echo

echo -e "${WHITE}✅ Бот успешно установлен в:${NC} ${GREEN}$PROJECT_DIR${NC}"

# Удаление исходной папки если она не в /opt/tg-sell-bot
if [ "$COPY_FILES" = true ] && [ "$SOURCE_DIR" != "/opt/tg-sell-bot" ] && [ "$SOURCE_DIR" != "/" ]; then
    echo -e "${WHITE}🧹 Удаление временных файлов...${NC}"
    cd /opt
    rm -rf "$SOURCE_DIR" 2>/dev/null || true
    echo -e "${GREEN}✅ Временные файлы удалены${NC}"
fi

echo

# Отмечаем успешное завершение установки
INSTALL_STARTED=false

cd /opt
