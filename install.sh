#!/bin/bash
set -e
exec < /dev/tty

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

# Функция для копирования файлов установки в /opt/tg-sell-bot
copy_installation_files() {
    local SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
    
    # Если мы уже в /opt/tg-sell-bot, ничего не делаем
    if [ "$SCRIPT_DIR" = "/opt/tg-sell-bot" ]; then
        return 0
    fi
    
    print_action "Подготовка файлов установки..."
    
    # Создаем целевую директорию
    mkdir -p "$PROJECT_DIR"
    
    # Определяем, что копировать
    local FILES_TO_COPY=(
        "docker-compose.yml"
        "Dockerfile"
        ".env.example"
    )
    
    # Ищем файлы в текущей директории
    for file in "${FILES_TO_COPY[@]}"; do
        if [ -f "$SCRIPT_DIR/$file" ]; then
            cp "$SCRIPT_DIR/$file" "$PROJECT_DIR/"
            print_success "Скопирован $file"
        fi
    done
    
    # Копируем директории, если они существуют
    if [ -d "$SCRIPT_DIR/src" ]; then
        cp -r "$SCRIPT_DIR/src" "$PROJECT_DIR/"
        print_success "Скопирована директория src"
    fi
    
    if [ -d "$SCRIPT_DIR/scripts" ]; then
        cp -r "$SCRIPT_DIR/scripts" "$PROJECT_DIR/"
        print_success "Скопирована директория scripts"
    fi
    
    # Копируем сам скрипт установки
    if [ -f "$SCRIPT_DIR/install.sh" ]; then
        cp "$SCRIPT_DIR/install.sh" "$PROJECT_DIR/"
        print_success "Скопирован скрипт установки"
    fi
    
    return 0
}

# ============================================================
# ПРОВЕРКИ ПРЕДУСЛОВИЙ И ПОДГОТОВКА
# ============================================================

# 0. Копирование файлов установки в /opt/tg-sell-bot
echo -e "${BLUE}========================================${NC}"
echo -e "${WHITE}      📦 ПОДГОТОВКА ФАЙЛОВ${NC}"
echo -e "${BLUE}========================================${NC}"
echo

copy_installation_files

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

# 2. Подготовка окружения
(
  mkdir -p "$PROJECT_DIR/logs"
  mkdir -p "$PROJECT_DIR/backups"
  mkdir -p "$PROJECT_DIR/assets"
  chmod 755 "$PROJECT_DIR/logs" "$PROJECT_DIR/backups" "$PROJECT_DIR/assets"

  if ! docker network ls | grep -q "remnawave-network"; then
      docker network create remnawave-network 2>/dev/null || true
  fi
) &
show_spinner "Создание окружения"

# 3. Создание .env файла
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

# 4. Автоопределение реверс-прокси
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
sed -i "s|^APP_DOMAIN=.*|APP_DOMAIN=${APP_DOMAIN}|" "$ENV_FILE"

# BOT_TOKEN
echo ""
safe_read "${YELLOW}➜ Введите Токен телеграм бота:${NC} " BOT_TOKEN
if [ -z "$BOT_TOKEN" ]; then
    print_error "BOT_TOKEN не может быть пустым!"
    exit 1
fi
sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=${BOT_TOKEN}|" "$ENV_FILE"

# BOT_DEV_ID
safe_read "${YELLOW}➜ Введите телеграм ID разработчика:${NC} " BOT_DEV_ID
if [ -z "$BOT_DEV_ID" ]; then
    print_error "BOT_DEV_ID не может быть пустым!"
    exit 1
fi
sed -i "s|^BOT_DEV_ID=.*|BOT_DEV_ID=${BOT_DEV_ID}|" "$ENV_FILE"

# BOT_SUPPORT_USERNAME
safe_read "${YELLOW}➜ Введите username группы поддержки (без @):${NC} " BOT_SUPPORT_USERNAME
echo
sed -i "s|^BOT_SUPPORT_USERNAME=.*|BOT_SUPPORT_USERNAME=${BOT_SUPPORT_USERNAME}|" "$ENV_FILE"

# REMNAWAVE_TOKEN
safe_read "${YELLOW}➜ Введите API Токен Remnawave:${NC} " REMNAWAVE_TOKEN
if [ -z "$REMNAWAVE_TOKEN" ]; then
    print_error "REMNAWAVE_TOKEN не может быть пустым!"
    exit 1
fi
sed -i "s|^REMNAWAVE_TOKEN=.*|REMNAWAVE_TOKEN=${REMNAWAVE_TOKEN}|" "$ENV_FILE"

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
    sed -i "s|^APP_CRYPT_KEY=.*|APP_CRYPT_KEY=${APP_CRYPT_KEY}|" "$ENV_FILE"
  fi

  if grep -q "^BOT_SECRET_TOKEN=$" "$ENV_FILE"; then
    BOT_SECRET_TOKEN=$(openssl rand -hex 32)
    sed -i "s|^BOT_SECRET_TOKEN=.*|BOT_SECRET_TOKEN=${BOT_SECRET_TOKEN}|" "$ENV_FILE"
  fi

  if grep -q "^DATABASE_PASSWORD=$" "$ENV_FILE"; then
    DATABASE_PASSWORD=$(openssl rand -hex 16)
    sed -i "s|^DATABASE_PASSWORD=.*|DATABASE_PASSWORD=${DATABASE_PASSWORD}|" "$ENV_FILE"
  fi

  if grep -q "^REDIS_PASSWORD=$" "$ENV_FILE"; then
    REDIS_PASSWORD=$(openssl rand -hex 16)
    sed -i "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=${REDIS_PASSWORD}|" "$ENV_FILE"
  fi

  if grep -q "^REMNAWAVE_WEBHOOK_SECRET=$" "$ENV_FILE"; then
    REMNAWAVE_WEBHOOK_SECRET=$(openssl rand -hex 32)
    sed -i "s|^REMNAWAVE_WEBHOOK_SECRET=.*|REMNAWAVE_WEBHOOK_SECRET=${REMNAWAVE_WEBHOOK_SECRET}|" "$ENV_FILE"
  fi
) &
show_spinner "Создание конфигурации"

# ============================================================
# СИНХРОНИЗАЦИЯ WEBHOOK С REMNAWAVE (ПОСЛЕ ВВОДА APP_DOMAIN)
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
          if grep -q "^REMNAWAVE_WEBHOOK_SECRET=" "$ENV_FILE"; then
              sed -i "s|^REMNAWAVE_WEBHOOK_SECRET=.*|REMNAWAVE_WEBHOOK_SECRET=${REMNAWAVE_SECRET}|" "$ENV_FILE"
          else
              echo "REMNAWAVE_WEBHOOK_SECRET=${REMNAWAVE_SECRET}" >> "$ENV_FILE"
          fi
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

# 7. Очистка ненужных файлов
(
  # Очищаем только временные файлы в /opt/tg-sell-bot
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

echo -e "${WHITE}📁 Файлы установлены в:${NC} ${GREEN}$PROJECT_DIR${NC}"
echo -e "${WHITE}🌐 Домен бота:${NC} ${GREEN}https://$APP_DOMAIN${NC}"
echo -e "${WHITE}⚙️  Файл конфигурации:${NC} ${GREEN}$ENV_FILE${NC}"
echo

cd /opt
