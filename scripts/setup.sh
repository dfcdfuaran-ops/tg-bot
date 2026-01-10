#!/bin/bash
set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Путь к .env файлу
ENV_FILE="/opt/remnashop/.env"
REMNAWAVE_ENV="/opt/remnawave/.env"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║      Установка и настройка RemnashopBot                   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================
# 0. Установка прав доступа и очистка
# ============================================================
echo -e "${BLUE}[0/4] Подготовка окружения...${NC}"

# Дать права на выполнение всем скриптам
chmod +x /opt/remnashop/scripts/*.sh 2>/dev/null || true

# Создать необходимые папки если их нет
mkdir -p /opt/remnashop/logs
mkdir -p /opt/remnashop/backups
mkdir -p /opt/remnashop/assets

# Установить права на папки
chmod 755 /opt/remnashop/logs
chmod 755 /opt/remnashop/backups
chmod 755 /opt/remnashop/assets

# Проверить наличие Docker network
echo -e "${YELLOW}  Проверяем Docker network...${NC}"
if ! docker network ls | grep -q "remnawave-network"; then
    echo -e "${YELLOW}  Создаем сеть remnawave-network...${NC}"
    docker network create remnawave-network 2>/dev/null || true
fi
echo -e "${GREEN}✓${NC} Docker network готова"

# Остановить контейнеры и удалить volumes
echo -e "${YELLOW}  Останавливаем контейнеры...${NC}"
docker compose down -v 2>/dev/null || true

# Удалить старый образ если он существует
echo -e "${YELLOW}  Удаляем старый образ remnashop:local...${NC}"
docker rmi remnashop:local -f 2>/dev/null || true

# Очистить BuildKit кэш
echo -e "${YELLOW}  Очищаем BuildKit кэш...${NC}"
docker buildx prune -af 2>/dev/null || true

echo -e "${GREEN}✓${NC} Окружение подготовлено"
echo ""

# Проверка наличия .env файла
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}✗ Файл .env не найден!${NC}"
    echo -e "${YELLOW}Создайте файл .env на основе .env.example${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Файл .env найден"
echo ""

# ============================================================
# 1. Генерация ключей безопасности
# ============================================================
echo -e "${BLUE}[1/4] Генерация ключей безопасности...${NC}"

APP_CRYPT_KEY=$(openssl rand -base64 32 | tr -d '\n')
BOT_SECRET_TOKEN=$(openssl rand -hex 64 | tr -d '\n')

sed -i "s|^APP_CRYPT_KEY=.*|APP_CRYPT_KEY=${APP_CRYPT_KEY}|" "$ENV_FILE"
sed -i "s|^BOT_SECRET_TOKEN=.*|BOT_SECRET_TOKEN=${BOT_SECRET_TOKEN}|" "$ENV_FILE"

echo -e "${GREEN}✓${NC} APP_CRYPT_KEY сгенерирован"
echo -e "${GREEN}✓${NC} BOT_SECRET_TOKEN сгенерирован"
echo ""

# ============================================================
# 2. Генерация паролей для БД и Redis
# ============================================================
echo -e "${BLUE}[2/4] Генерация паролей...${NC}"

# Используем hex (без спецсимволов) для совместимости с PostgresDsn.build()
DATABASE_PASSWORD=$(openssl rand -hex 32 | tr -d '\n')
REDIS_PASSWORD=$(openssl rand -hex 32 | tr -d '\n')

sed -i "s|^DATABASE_PASSWORD=.*|DATABASE_PASSWORD=${DATABASE_PASSWORD}|" "$ENV_FILE"
sed -i "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=${REDIS_PASSWORD}|" "$ENV_FILE"

echo -e "${GREEN}✓${NC} DATABASE_PASSWORD сгенерирован"
echo -e "${GREEN}✓${NC} REDIS_PASSWORD сгенерирован"
echo ""

# ============================================================
# 3. Запрос обязательных переменных
# ============================================================
echo -e "${BLUE}[3/4] Настройка обязательных переменных${NC}"
echo -e "${YELLOW}Введите следующие параметры:${NC}"
echo ""

# APP_DOMAIN
while true; do
    echo -e "${BLUE}→${NC} APP_DOMAIN (домен для доступа к боту, например: bot.example.com):"
    read -r APP_DOMAIN
    if [ -n "$APP_DOMAIN" ]; then
        sed -i "s|^APP_DOMAIN=.*|APP_DOMAIN=${APP_DOMAIN}|" "$ENV_FILE"
        echo -e "${GREEN}✓${NC} APP_DOMAIN установлен: ${APP_DOMAIN}"
        echo ""
        break
    else
        echo -e "${RED}✗ Домен не может быть пустым!${NC}"
    fi
done

# BOT_TOKEN
while true; do
    echo -e "${BLUE}→${NC} BOT_TOKEN (токен от @BotFather):"
    read -r BOT_TOKEN
    if [ -n "$BOT_TOKEN" ]; then
        sed -i "s|^BOT_TOKEN=.*|BOT_TOKEN=${BOT_TOKEN}|" "$ENV_FILE"
        echo -e "${GREEN}✓${NC} BOT_TOKEN установлен"
        echo ""
        break
    else
        echo -e "${RED}✗ BOT_TOKEN не может быть пустым!${NC}"
    fi
done

# BOT_DEV_ID
while true; do
    echo -e "${BLUE}→${NC} BOT_DEV_ID (ваш Telegram ID, узнать можно у @userinfobot):"
    read -r BOT_DEV_ID
    if [[ "$BOT_DEV_ID" =~ ^[0-9]+$ ]]; then
        sed -i "s|^BOT_DEV_ID=.*|BOT_DEV_ID=${BOT_DEV_ID}|" "$ENV_FILE"
        echo -e "${GREEN}✓${NC} BOT_DEV_ID установлен: ${BOT_DEV_ID}"
        echo ""
        break
    else
        echo -e "${RED}✗ BOT_DEV_ID должен быть числом!${NC}"
    fi
done

# BOT_SUPPORT_USERNAME
while true; do
    echo -e "${BLUE}→${NC} BOT_SUPPORT_USERNAME (имя пользователя поддержки без @):"
    read -r BOT_SUPPORT_USERNAME
    if [ -n "$BOT_SUPPORT_USERNAME" ]; then
        # Удаляем @ если пользователь ввел его
        BOT_SUPPORT_USERNAME="${BOT_SUPPORT_USERNAME#@}"
        sed -i "s|^BOT_SUPPORT_USERNAME=.*|BOT_SUPPORT_USERNAME=${BOT_SUPPORT_USERNAME}|" "$ENV_FILE"
        echo -e "${GREEN}✓${NC} BOT_SUPPORT_USERNAME установлен: @${BOT_SUPPORT_USERNAME}"
        echo ""
        break
    else
        echo -e "${RED}✗ Username не может быть пустым!${NC}"
    fi
done

# REMNAWAVE_TOKEN
while true; do
    echo -e "${BLUE}→${NC} REMNAWAVE_TOKEN (API токен из панели Remnawave):"
    read -r REMNAWAVE_TOKEN
    if [ -n "$REMNAWAVE_TOKEN" ]; then
        sed -i "s|^REMNAWAVE_TOKEN=.*|REMNAWAVE_TOKEN=${REMNAWAVE_TOKEN}|" "$ENV_FILE"
        echo -e "${GREEN}✓${NC} REMNAWAVE_TOKEN установлен"
        echo ""
        break
    else
        echo -e "${RED}✗ REMNAWAVE_TOKEN не может быть пустым!${NC}"
    fi
done

# REMNAWAVE_WEBHOOK_SECRET - автоматическое извлечение из Remnawave .env
if [ -f "$REMNAWAVE_ENV" ]; then
    # Извлекаем WEBHOOK_SECRET_HEADER из файла Remnawave
    EXTRACTED_SECRET=$(grep "^WEBHOOK_SECRET_HEADER=" "$REMNAWAVE_ENV" 2>/dev/null | cut -d '=' -f 2)
    
    if [ -n "$EXTRACTED_SECRET" ]; then
        sed -i "s|^REMNAWAVE_WEBHOOK_SECRET=.*|REMNAWAVE_WEBHOOK_SECRET=${EXTRACTED_SECRET}|" "$ENV_FILE"
        echo -e "${GREEN}✓${NC} REMNAWAVE_WEBHOOK_SECRET автоматически извлечен из Remnawave .env"
        echo ""
    else
        echo -e "${YELLOW}⚠ WEBHOOK_SECRET_HEADER не найден в ${REMNAWAVE_ENV}${NC}"
        # Ручной ввод если не нашли
        while true; do
            echo -e "${BLUE}→${NC} REMNAWAVE_WEBHOOK_SECRET (должен совпадать с WEBHOOK_SECRET_HEADER в панели):"
            read -r REMNAWAVE_WEBHOOK_SECRET
            if [ -n "$REMNAWAVE_WEBHOOK_SECRET" ]; then
                sed -i "s|^REMNAWAVE_WEBHOOK_SECRET=.*|REMNAWAVE_WEBHOOK_SECRET=${REMNAWAVE_WEBHOOK_SECRET}|" "$ENV_FILE"
                echo -e "${GREEN}✓${NC} REMNAWAVE_WEBHOOK_SECRET установлен"
                echo ""
                break
            else
                echo -e "${RED}✗ REMNAWAVE_WEBHOOK_SECRET не может быть пустым!${NC}"
            fi
        done
    fi
else
    echo -e "${YELLOW}⚠ Файл ${REMNAWAVE_ENV} не найден${NC}"
    # Ручной ввод если файл не существует
    while true; do
        echo -e "${BLUE}→${NC} REMNAWAVE_WEBHOOK_SECRET (должен совпадать с WEBHOOK_SECRET_HEADER в панели):"
        read -r REMNAWAVE_WEBHOOK_SECRET
        if [ -n "$REMNAWAVE_WEBHOOK_SECRET" ]; then
            sed -i "s|^REMNAWAVE_WEBHOOK_SECRET=.*|REMNAWAVE_WEBHOOK_SECRET=${REMNAWAVE_WEBHOOK_SECRET}|" "$ENV_FILE"
            echo -e "${GREEN}✓${NC} REMNAWAVE_WEBHOOK_SECRET установлен"
            echo ""
            break
        else
            echo -e "${RED}✗ REMNAWAVE_WEBHOOK_SECRET не может быть пустым!${NC}"
        fi
    done
fi

# ============================================================
# 4. Настройка Remnawave webhook
# ============================================================
echo -e "${BLUE}Настройка Remnawave webhook...${NC}"

if [ -f "$REMNAWAVE_ENV" ]; then
    WEBHOOK_URL="https://${APP_DOMAIN}/api/v1/remnawave"
    
    # Обновляем WEBHOOK_ENABLED
    if grep -q "^WEBHOOK_ENABLED=" "$REMNAWAVE_ENV"; then
        sed -i "s|^WEBHOOK_ENABLED=.*|WEBHOOK_ENABLED=true|" "$REMNAWAVE_ENV"
    else
        echo "WEBHOOK_ENABLED=true" >> "$REMNAWAVE_ENV"
    fi
    
    # Обновляем WEBHOOK_URL
    if grep -q "^WEBHOOK_URL=" "$REMNAWAVE_ENV"; then
        sed -i "s|^WEBHOOK_URL=.*|WEBHOOK_URL=${WEBHOOK_URL}|" "$REMNAWAVE_ENV"
    else
        echo "WEBHOOK_URL=${WEBHOOK_URL}" >> "$REMNAWAVE_ENV"
    fi
    
    echo -e "${GREEN}✓${NC} Remnawave .env обновлен:"
    echo -e "  WEBHOOK_ENABLED=true"
    echo -e "  WEBHOOK_URL=${WEBHOOK_URL}"
    echo ""
else
    echo -e "${YELLOW}⚠ Файл ${REMNAWAVE_ENV} не найден${NC}"
    echo -e "${YELLOW}  Пожалуйста, настройте webhook вручную:${NC}"
    echo -e "  WEBHOOK_ENABLED=true"
    echo -e "  WEBHOOK_URL=https://${APP_DOMAIN}/api/v1/remnawave"
    echo ""
fi

# ============================================================
# 4. Выбор реверс-прокси
# ============================================================
echo -e "${BLUE}Настройка реверс-прокси${NC}"
echo -e "Выберите используемый реверс-прокси:"
echo -e "  ${GREEN}1${NC}) Caddy"
echo -e "  ${YELLOW}2${NC}) Nginx (в разработке)"
echo ""

while true; do
    echo -e "${BLUE}→${NC} Ваш выбор [1-2]:"
    read -r PROXY_CHOICE
    
    case $PROXY_CHOICE in
        1)
            # Caddy
            CADDY_FILE="/opt/remnawave/caddy/Caddyfile"
            
            if [ -f "$CADDY_FILE" ]; then
                # Проверяем, нет ли уже такой конфигурации
                if grep -q "https://${APP_DOMAIN}" "$CADDY_FILE"; then
                    echo -e "${YELLOW}⚠ Конфигурация для ${APP_DOMAIN} уже существует в Caddyfile${NC}"
                else
                    # Добавляем конфигурацию
                    echo "" >> "$CADDY_FILE"
                    echo "https://${APP_DOMAIN} {" >> "$CADDY_FILE"
                    echo "        reverse_proxy * http://remnashop:5000" >> "$CADDY_FILE"
                    echo "}" >> "$CADDY_FILE"
                    
                    echo -e "${GREEN}✓${NC} Конфигурация Caddy добавлена"
                    echo -e "${YELLOW}⚠ Перезагрузите Caddy:${NC} docker restart caddy"
                fi
            else
                echo -e "${RED}✗ Файл ${CADDY_FILE} не найден${NC}"
                echo -e "${YELLOW}Добавьте в Caddyfile вручную:${NC}"
                echo ""
                echo "https://${APP_DOMAIN} {"
                echo "        reverse_proxy * http://remnashop:5000"
                echo "}"
            fi
            break
            ;;
        2)
            # Nginx
            echo -e "${YELLOW}⚠ Функция Nginx в разработке${NC}"
            echo -e "${YELLOW}Добавьте в nginx.conf вручную:${NC}"
            echo ""
            echo "server {"
            echo "    listen 443 ssl http2;"
            echo "    server_name ${APP_DOMAIN};"
            echo ""
            echo "    location / {"
            echo "        proxy_pass http://remnashop:5000;"
            echo "        proxy_set_header Host \$host;"
            echo "        proxy_set_header X-Real-IP \$remote_addr;"
            echo "    }"
            echo "}"
            break
            ;;
        *)
            echo -e "${RED}✗ Неверный выбор. Введите 1 или 2${NC}"
            ;;
    esac
done

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              Настройка завершена успешно! ✓               ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BLUE}Запуск бота...${NC}"
echo ""

# Запускаем контейнеры с пересборкой
cd /opt/remnashop && docker compose up -d --build

# Функция проверки здоровья контейнера
wait_for_healthy() {
    local container=$1
    local max_wait=$2
    local counter=0
    
    while [ $counter -lt $max_wait ]; do
        status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "starting")
        if [ "$status" = "healthy" ]; then
            return 0
        fi
        counter=$((counter + 1))
        sleep 1
    done
    return 1
}

echo -e "${YELLOW}Ожидание запуска контейнеров...${NC}"

# Ждем БД
echo -ne "  База данных: "
if wait_for_healthy "remnashop-db" 30; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}запускается...${NC}"
fi

# Ждем Redis
echo -ne "  Redis: "
if wait_for_healthy "remnashop-redis" 30; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${YELLOW}запускается...${NC}"
fi

# Ждем бота (проверяем что контейнер запущен)
echo -ne "  Бот: "
sleep 10
if docker ps --format '{{.Names}}' | grep -q "^remnashop$"; then
    # Проверяем логи на успешный запуск
    if docker compose logs remnashop 2>&1 | grep -q "Uvicorn running"; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${YELLOW}запускается...${NC}"
        sleep 10
    fi
else
    echo -e "${RED}не запущен!${NC}"
fi

# Проверяем статус
echo ""
echo -e "${BLUE}Статус контейнеров:${NC}"
docker compose ps

# Проверяем наличие ошибок
echo ""
if docker compose logs remnashop 2>&1 | grep -qi "error\|exception\|failed" | head -1; then
    echo -e "${YELLOW}⚠ Обнаружены предупреждения в логах. Проверьте: docker compose logs remnashop${NC}"
fi

# Проверяем создание DEV пользователя
if docker compose logs remnashop 2>&1 | grep -q "DEV user.*created automatically"; then
    echo -e "${GREEN}✓ DEV пользователь создан автоматически!${NC}"
    echo -e "${GREEN}✓ Уведомление о запуске отправлено в Telegram${NC}"
fi

echo ""
echo -e "${GREEN}✓ Установка завершена!${NC}"
echo ""
echo -e "${BLUE}Полезные команды:${NC}"
echo -e "  ${YELLOW}docker compose ps${NC}              - статус контейнеров"
echo -e "  ${YELLOW}docker compose logs -f remnashop${NC} - логи бота (Ctrl+C для выхода)"
echo -e "  ${YELLOW}docker compose restart${NC}          - перезапуск"
echo -e "  ${YELLOW}docker compose down${NC}             - остановка"
echo ""
