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

# Путь к проекту (всегда /opt/tg-sell-bot на хосте)
PROJECT_DIR="/opt/tg-sell-bot"
ENV_FILE="$PROJECT_DIR/.env"
ENV_EXAMPLE_FILE="$PROJECT_DIR/.env.example"

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
    cat << EOF
    
upstream remnashop {
    server localhost:5000;
}

server {
    listen 80;
    server_name ${app_domain};
    
    location / {
        proxy_pass http://remnashop;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
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
# ПРОВЕРКИ ПРЕДУСЛОВИЙ И ПОДГОТОВКА
# ============================================================

# 0. Создание директории проекта, если её нет
(
  if [ ! -d "$PROJECT_DIR" ]; then
      mkdir -p "$PROJECT_DIR"
      log_info "Создана директория проекта: $PROJECT_DIR"
  fi
) &
show_spinner "Подготовка директории проекта"

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

# 2. Подготовка структуры каталогов
(
  mkdir -p "$PROJECT_DIR/logs"
  mkdir -p "$PROJECT_DIR/backups"
  mkdir -p "$PROJECT_DIR/assets"
  chmod 755 "$PROJECT_DIR/logs" "$PROJECT_DIR/backups" "$PROJECT_DIR/assets"

  if ! docker network ls | grep -q "remnawave-network"; then
      docker network create remnawave-network 2>/dev/null || true
  fi
) &
show_spinner "Создание структуры каталогов"

# 3. Проверка наличия .env.example
(
  if [ ! -f "$ENV_EXAMPLE_FILE" ]; then
      print_error "Файл .env.example не найден!"
      print_error "Пожалуйста, убедитесь что вы скопировали проект в $PROJECT_DIR"
      print_error "и что файл .env.example существует"
      exit 1
  fi
) &
show_spinner "Проверка файлов конфигурации"

# 4. Создание .env файла из примера
(
  if [ ! -f "$ENV_FILE" ]; then
      cp "$ENV_EXAMPLE_FILE" "$ENV_FILE"
      log_success "Создан файл конфигурации: $ENV_FILE"
  else
      log_warning "Файл .env уже существует, оставляю без изменений"
  fi
) &
show_spinner "Инициализация конфигурации"

# 5. Автоопределение реверс-прокси
(
  if [ -d "/opt/remnawave/caddy" ]; then
    REVERSE_PROXY="caddy"
  elif [ -d "/opt/remnawave/nginx" ]; then
    REVERSE_PROXY="nginx"
  else
    REVERSE_PROXY="none"
  fi
) &
show_spinner "Определение реверс-прокси"

echo
if [ "$REVERSE_PROXY" = "caddy" ]; then
  print_success "Обнаружен реверс прокси Caddy"
  print_success "Применяем вариант установки с Caddy"
elif [ "$REVERSE_PROXY" = "nginx" ]; then
  print_success "Обнаружен реверс прокси Nginx"
  print_success "Применяем вариант установки с Nginx"
else
  print_success "Реверс-прокси не обнаружен"
  print_success "Установка будет выполнена без настройки прокси"
fi

echo
echo -e "${BLUE}========================================${NC}"
echo -e "${WHITE}    ⚙️ НАСТРОЙКА КОНФИГУРАЦИИ БОТА${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# Проверка существования .env файла перед редактированием
if [ ! -f "$ENV_FILE" ]; then
    print_error "Файл .env не существует! Создайте его из .env.example"
    exit 1
fi

# APP_DOMAIN
safe_read "${YELLOW}➜ Введите домен бота (напр. bot.example.com):${NC} " APP_DOMAIN
if [ -z "$APP_DOMAIN" ]; then
    print_error "Домен не может быть пустым!"
    exit 1
fi
sed -i "s|^APP_DOMAIN=.*|APP_DOMAIN=${APP_DOMAIN}|" "$ENV_FILE"
print_success "APP_DOMAIN установлен: $APP_DOMAIN"

# BOT_TOKEN
echo ""
safe_read "${YELLOW}➜ Введите Токен телеграм бота:${NC} " BOT_TOKEN
if [ -z "$BOT_TOKEN" ]; then
    print_error "BOT_TOKEN не может быть пустым!"
    exit 1
fi
sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=${BOT_TOKEN}|" "$ENV_FILE"
print_success "BOT_TOKEN установлен"

# BOT_DEV_ID
safe_read "${YELLOW}➜ Введите телеграм ID разработчика:${NC} " BOT_DEV_ID
if [ -z "$BOT_DEV_ID" ]; then
    print_error "BOT_DEV_ID не может быть пустым!"
    exit 1
fi
sed -i "s|^BOT_DEV_ID=.*|BOT_DEV_ID=${BOT_DEV_ID}|" "$ENV_FILE"
print_success "BOT_DEV_ID установлен: $BOT_DEV_ID"

# BOT_SUPPORT_USERNAME
safe_read "${YELLOW}➜ Введите username группы поддержки (без @):${NC} " BOT_SUPPORT_USERNAME
sed -i "s|^BOT_SUPPORT_USERNAME=.*|BOT_SUPPORT_USERNAME=${BOT_SUPPORT_USERNAME}|" "$ENV_FILE"
print_success "BOT_SUPPORT_USERNAME установлен: $BOT_SUPPORT_USERNAME"

# REMNAWAVE_TOKEN
echo ""
safe_read "${YELLOW}➜ Введите API Токен Remnawave:${NC} " REMNAWAVE_TOKEN
if [ -z "$REMNAWAVE_TOKEN" ]; then
    print_error "REMNAWAVE_TOKEN не может быть пустым!"
    exit 1
fi
sed -i "s|^REMNAWAVE_TOKEN=.*|REMNAWAVE_TOKEN=${REMNAWAVE_TOKEN}|" "$ENV_FILE"
print_success "REMNAWAVE_TOKEN установлен"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${WHITE}         ⚡ ПРОЦЕСС УСТАНОВКИ${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# 1. Генерация секретов и паролей
(
  # Автогенерация ключей
  if grep -q "^APP_CRYPT_KEY=$" "$ENV_FILE" || grep -q "^APP_CRYPT_KEY=\"\"$" "$ENV_FILE"; then
    APP_CRYPT_KEY=$(openssl rand -base64 32 | tr -d '\n')
    sed -i "s|^APP_CRYPT_KEY=.*|APP_CRYPT_KEY=${APP_CRYPT_KEY}|" "$ENV_FILE"
  fi

  if grep -q "^BOT_SECRET_TOKEN=$" "$ENV_FILE" || grep -q "^BOT_SECRET_TOKEN=\"\"$" "$ENV_FILE"; then
    BOT_SECRET_TOKEN=$(openssl rand -hex 32)
    sed -i "s|^BOT_SECRET_TOKEN=.*|BOT_SECRET_TOKEN=${BOT_SECRET_TOKEN}|" "$ENV_FILE"
  fi

  if grep -q "^DATABASE_PASSWORD=$" "$ENV_FILE" || grep -q "^DATABASE_PASSWORD=\"\"$" "$ENV_FILE"; then
    DATABASE_PASSWORD=$(openssl rand -hex 16)
    sed -i "s|^DATABASE_PASSWORD=.*|DATABASE_PASSWORD=${DATABASE_PASSWORD}|" "$ENV_FILE"
  fi

  if grep -q "^REDIS_PASSWORD=$" "$ENV_FILE" || grep -q "^REDIS_PASSWORD=\"\"$" "$ENV_FILE"; then
    REDIS_PASSWORD=$(openssl rand -hex 16)
    sed -i "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=${REDIS_PASSWORD}|" "$ENV_FILE"
  fi

  if grep -q "^REMNAWAVE_WEBHOOK_SECRET=$" "$ENV_FILE" || grep -q "^REMNAWAVE_WEBHOOK_SECRET=\"\"$" "$ENV_FILE"; then
    REMNAWAVE_WEBHOOK_SECRET=$(openssl rand -hex 32)
    sed -i "s|^REMNAWAVE_WEBHOOK_SECRET=.*|REMNAWAVE_WEBHOOK_SECRET=${REMNAWAVE_WEBHOOK_SECRET}|" "$ENV_FILE"
  fi
) &
show_spinner "Генерация секретов и паролей"

# 2. Проверка что мы в правильной директории
(
  if [ ! -f "$PROJECT_DIR/docker-compose.yml" ] && [ ! -f "$PROJECT_DIR/docker-compose.yaml" ]; then
      log_warning "docker-compose.yml не найден в $PROJECT_DIR"
      log_warning "Убедитесь что все файлы проекта скопированы в $PROJECT_DIR"
  fi
) &
show_spinner "Проверка файлов проекта"

# 3. Сборка Docker образа (если есть docker-compose.yml)
(
  if [ -f "$PROJECT_DIR/docker-compose.yml" ] || [ -f "$PROJECT_DIR/docker-compose.yaml" ]; then
      cd "$PROJECT_DIR"
      docker compose build >/dev/null 2>&1
  else
      log_warning "docker-compose.yml не найден, пропускаю сборку"
  fi
) &
show_spinner "Сборка Docker образа"

# 4. Запуск контейнеров
(
  if [ -f "$PROJECT_DIR/docker-compose.yml" ] || [ -f "$PROJECT_DIR/docker-compose.yaml" ]; then
      cd "$PROJECT_DIR"
      docker compose up -d >/dev/null 2>&1
  else
      log_warning "docker-compose.yml не найден, пропускаю запуск контейнеров"
  fi
) &
show_spinner "Запуск сервисов"

# 5. Настройка реверс-прокси если требуется
(
  if [ "$REVERSE_PROXY" != "none" ]; then
      configure_reverse_proxy "$APP_DOMAIN" "$REVERSE_PROXY"
  fi
) &
show_spinner "Настройка реверс-прокси"

# 6. Очистка ненужных файлов (опционально)
(
  # Удаляем только если файлы существуют
  [ -d "$PROJECT_DIR/src" ] && rm -rf "$PROJECT_DIR/src" 2>/dev/null || true
  [ -d "$PROJECT_DIR/scripts" ] && rm -rf "$PROJECT_DIR/scripts" 2>/dev/null || true
  [ -d "$PROJECT_DIR/docs" ] && rm -rf "$PROJECT_DIR/docs" 2>/dev/null || true
  [ -d "$PROJECT_DIR/.git" ] && rm -rf "$PROJECT_DIR/.git" 2>/dev/null || true
  [ -d "$PROJECT_DIR/.venv" ] && rm -rf "$PROJECT_DIR/.venv" 2>/dev/null || true
  [ -d "$PROJECT_DIR/__pycache__" ] && rm -rf "$PROJECT_DIR/__pycache__" 2>/dev/null || true
  
  # Удаляем файлы если они существуют
  [ -f "$PROJECT_DIR/.env.example" ] && rm -f "$PROJECT_DIR/.env.example" 2>/dev/null || true
  [ -f "$PROJECT_DIR/.gitignore" ] && rm -f "$PROJECT_DIR/.gitignore" 2>/dev/null || true
  [ -f "$PROJECT_DIR/.dockerignore" ] && rm -f "$PROJECT_DIR/.dockerignore" 2>/dev/null || true
  [ -f "$PROJECT_DIR/.python-version" ] && rm -f "$PROJECT_DIR/.python-version" 2>/dev/null || true
  [ -f "$PROJECT_DIR/.editorconfig" ] && rm -f "$PROJECT_DIR/.editorconfig" 2>/dev/null || true
  [ -f "$PROJECT_DIR/Makefile" ] && rm -f "$PROJECT_DIR/Makefile" 2>/dev/null || true
  [ -f "$PROJECT_DIR/pyproject.toml" ] && rm -f "$PROJECT_DIR/pyproject.toml" 2>/dev/null || true
  [ -f "$PROJECT_DIR/uv.lock" ] && rm -f "$PROJECT_DIR/uv.lock" 2>/dev/null || true
  [ -f "$PROJECT_DIR/README.md" ] && rm -f "$PROJECT_DIR/README.md" 2>/dev/null || true
  [ -f "$PROJECT_DIR/INSTALL_RU.md" ] && rm -f "$PROJECT_DIR/INSTALL_RU.md" 2>/dev/null || true
  [ -f "$PROJECT_DIR/BACKUP_RESTORE_GUIDE.md" ] && rm -f "$PROJECT_DIR/BACKUP_RESTORE_GUIDE.md" 2>/dev/null || true
  [ -f "$PROJECT_DIR/CHANGES_SUMMARY.md" ] && rm -f "$PROJECT_DIR/CHANGES_SUMMARY.md" 2>/dev/null || true
  [ -f "$PROJECT_DIR/DETAILED_EXPLANATION.md" ] && rm -f "$PROJECT_DIR/DETAILED_EXPLANATION.md" 2>/dev/null || true
  [ -f "$PROJECT_DIR/INVITE_FIX.md" ] && rm -f "$PROJECT_DIR/INVITE_FIX.md" 2>/dev/null || true
  
  # Не удаляем install.sh - он может понадобиться для обновления
) &
show_spinner "Очистка временных файлов"

# ============================================================
# ЗАВЕРШЕНИЕ УСТАНОВКИ
# ============================================================

echo
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}    🎉 УСТАНОВКА ЗАВЕРШЕНА УСПЕШНО!${NC}"
echo -e "${BLUE}========================================${NC}"
echo

echo -e "${WHITE}📋 ИНФОРМАЦИЯ О УСТАНОВКЕ:${NC}"
echo -e "${DARKGRAY}----------------------------------------${NC}"
echo -e "${GREEN}•${NC} Проект установлен в: ${YELLOW}$PROJECT_DIR${NC}"
echo -e "${GREEN}•${NC} Файл конфигурации: ${YELLOW}$ENV_FILE${NC}"
echo -e "${GREEN}•${NC} Домен приложения: ${YELLOW}$APP_DOMAIN${NC}"
echo -e "${GREEN}•${NC} Используемый прокси: ${YELLOW}$REVERSE_PROXY${NC}"

if [ -f "$PROJECT_DIR/docker-compose.yml" ] || [ -f "$PROJECT_DIR/docker-compose.yaml" ]; then
    echo
    echo -e "${WHITE}🚀 КОМАНДЫ ДЛЯ УПРАВЛЕНИЯ:${NC}"
    echo -e "${DARKGRAY}----------------------------------------${NC}"
    echo -e "${GREEN}•${NC} Проверить статус контейнеров:"
    echo -e "  ${YELLOW}cd $PROJECT_DIR && docker compose ps${NC}"
    echo -e "${GREEN}•${NC} Просмотреть логи бота:"
    echo -e "  ${YELLOW}cd $PROJECT_DIR && docker compose logs -f bot${NC}"
    echo -e "${GREEN}•${NC} Остановить сервисы:"
    echo -e "  ${YELLOW}cd $PROJECT_DIR && docker compose down${NC}"
    echo -e "${GREEN}•${NC} Перезапустить сервисы:"
    echo -e "  ${YELLOW}cd $PROJECT_DIR && docker compose restart${NC}"
fi

if [ "$REVERSE_PROXY" = "caddy" ]; then
    echo
    echo -e "${WHITE}⚠️  ДОПОЛНИТЕЛЬНЫЕ ДЕЙСТВИЯ:${NC}"
    echo -e "${DARKGRAY}----------------------------------------${NC}"
    echo -e "${GREEN}•${NC} Для применения конфигурации Caddy выполните:"
    echo -e "  ${YELLOW}docker compose -f /opt/remnawave/caddy/docker-compose.yml restart caddy${NC}"
fi

echo
echo -e "${WHITE}📁 СТРУКТУРА ПРОЕКТА:${NC}"
echo -e "${DARKGRAY}----------------------------------------${NC}"
ls -la "$PROJECT_DIR/" | grep -E "^d|^-" | head -20

echo
echo -e "${GREEN}✅ Установка завершена успешно!${NC}"
echo -e "${BLUE}========================================${NC}"
