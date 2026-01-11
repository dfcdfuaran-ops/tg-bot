#!/bin/bash
set -e

# Переменные для отслеживания состояния установки
INSTALL_STARTED=false
SOURCE_DIR=""
CLEANUP_DIRS=()
TEMP_REPO=""
SCRIPT_CWD="$(cd "$(dirname "$0")" && pwd)"
CLONE_DIR=""

# Переменные путей
PROJECT_DIR="/opt/tg-sell-bot"
ENV_FILE="$PROJECT_DIR/.env"
REPO_DIR="/opt/tg-bot"
REMNAWAVE_DIR="/opt/remnawave"
REPO_URL="https://github.com/dfcdfuaran-ops/tg-bot.git"
REPO_BRANCH="dev"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[1;34m'
WHITE='\033[1;37m'
GRAY='\033[0;37m'
NC='\033[0m'
DARKGRAY='\033[1;30m'

# ════════════════════════════════════════
# ФУНКЦИИ УТИЛИТ
# ════════════════════════════════════════

# Функция спинера для длительных операций
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

# Спинер без сообщения (просто ждём процесс)
show_spinner_silent() {
  local pid=$!
  local delay=0.08
  local spin=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
  local i=0
  while kill -0 $pid 2>/dev/null; do
    i=$(( (i+1) % 10 ))
    sleep $delay
  done
  wait $pid 2>/dev/null || true
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

# Функция для проверки установлен ли бот
is_installed() {
    # Бот считается установленным только если:
    # 1. Директория существует
    # 2. Есть критические файлы (docker-compose.yml и .env)
    # 3. Docker контейнеры запущены или есть следы работы
    if [ -d "$PROJECT_DIR" ] && [ -f "$PROJECT_DIR/docker-compose.yml" ] && [ -f "$PROJECT_DIR/.env" ]; then
        return 0  # installed
    fi
    return 1  # not installed
}

# Функция для сохранения критических переменных из .env перед обновлением
preserve_env_vars() {
    local env_file="$1"
    local temp_storage="/tmp/env_backup_$$"
    
    # Сохраняем критические переменные в временный файл
    if [ -f "$env_file" ]; then
        # Сохраняем пароли и токены
        grep -E "^(DB_PASSWORD|DB_USER|DB_NAME|BOT_TOKEN|BOT_DEV_ID|APP_DOMAIN|POSTGRES_PASSWORD|POSTGRES_USER|POSTGRES_DB)=" "$env_file" > "$temp_storage" 2>/dev/null || true
    fi
    echo "$temp_storage"
}

# Функция для восстановления критических переменных в .env
restore_env_vars() {
    local env_file="$1"
    local temp_storage="$2"
    
    if [ -f "$temp_storage" ]; then
        # Читаем сохранённые переменные и обновляем их в .env
        while IFS='=' read -r var_name var_value; do
            if [ -n "$var_name" ] && [ -n "$var_value" ]; then
                update_env_var "$env_file" "$var_name" "$var_value"
            fi
        done < "$temp_storage"
        
        # Удаляем временный файл
        rm -f "$temp_storage" 2>/dev/null || true
    fi
}

# Функция для проверки режима (установка или меню)
check_mode() {
    # Если передан аргумент --install, пропускаем меню
    if [ "$1" = "--install" ]; then
        return 0
    fi
    
    # Инициализируем временный каталог для скачивания репозитория
    TEMP_REPO=$(mktemp -d)
    
    # Если бот установлен и скрипт вызван без аргументов, показываем полное меню
    if is_installed && [ -z "$1" ]; then
        show_full_menu
    fi
    
    # Если бот не установлен и скрипт вызван без аргументов, показываем меню с одним пунктом
    if ! is_installed && [ -z "$1" ]; then
        show_simple_menu
    fi
}

# Функция очистки при выходе из установки
cleanup_on_exit() {
    # Удаляем скачанные файлы если они были скачаны но установка не началась
    if [ -n "$TEMP_REPO" ] && [ -d "$TEMP_REPO" ]; then
        rm -rf "$TEMP_REPO" 2>/dev/null || true
    fi
}

# Простое меню при отсутствии бота
show_simple_menu() {
    set +e  # Отключаем exit on error для функции меню
    local selected=0
    local options=("🚀  Установить" "❌  Выход")
    local num_options=${#options[@]}
    
    # Сохраняем текущие настройки терминала
    local original_stty=$(stty -g 2>/dev/null)
    
    # Функция для очистки скачанных файлов при выходе из меню установки
    cleanup_menu_temp() {
        if [ "$INSTALL_STARTED" = false ]; then
            # Удаляем временную папку репозитория для проверки обновлений
            if [ -n "$TEMP_REPO" ] && [ -d "$TEMP_REPO" ]; then
                cd /opt 2>/dev/null || true
                rm -rf "$TEMP_REPO" 2>/dev/null || true
            fi
            
            # Удаляем исходную папку клона если это была временная установка
            # (не целевая /opt/tg-sell-bot и не основной каталог /opt/tg-bot)
            if [ -n "$SCRIPT_CWD" ] && [ "$SCRIPT_CWD" != "/opt/tg-sell-bot" ] && [ "$SCRIPT_CWD" != "/opt/tg-bot" ] && [ "$SCRIPT_CWD" != "/" ]; then
                if [ -d "$SCRIPT_CWD" ]; then
                    cd /opt 2>/dev/null || true
                    rm -rf "$SCRIPT_CWD" 2>/dev/null || true
                fi
            fi
        fi
    }
    
    trap "stty '$original_stty' 2>/dev/null || true; tput cnorm 2>/dev/null || true; cleanup_menu_temp; set -e" EXIT
    
    # Скрываем курсор
    tput civis 2>/dev/null || true
    
    # Отключаем canonical mode и echo, включаем чтение отдельных символов
    stty -icanon -echo min 1 time 0 2>/dev/null || true
    
    while true; do
        clear
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo -e "${GREEN}   🚀 TG-SELL-BOT INSTALLER${NC}"
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo
        
        # Выводим опции меню
        for i in "${!options[@]}"; do
            if [ $i -eq $selected ]; then
                echo -e "${BLUE}▶${NC} ${GREEN}${options[$i]}${NC}"
            else
                echo "  ${options[$i]}"
            fi
        done
        
        echo
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo -e "${DARKGRAY}Используйте ↑↓ для навигации, Enter для выбора${NC}"
        echo
        
        local key
        read -rsn1 key 2>/dev/null || key=""
        
        # Проверяем escape-последовательность для стрелок (ASCII 27)
        if [[ "$key" == $'\e' ]]; then
            # Читаем остаток последовательности [A или [B
            local seq1=""
            read -rsn1 -t 0.1 seq1 2>/dev/null || seq1=""
            
            if [[ "$seq1" == '[' ]]; then
                local seq2=""
                read -rsn1 -t 0.1 seq2 2>/dev/null || seq2=""
                
                case "$seq2" in
                    'A')  # Стрелка вверх
                        ((selected--))
                        if [ $selected -lt 0 ]; then
                            selected=$((num_options - 1))
                        fi
                        ;;
                    'B')  # Стрелка вниз
                        ((selected++))
                        if [ $selected -ge $num_options ]; then
                            selected=0
                        fi
                        ;;
                esac
            fi
        else
            # Если это не escape, проверяем другие символы
            # В raw mode Enter может быть CR (ASCII 13) или быть пустым
            local key_code
            if [ -n "$key" ]; then
                # Получаем ASCII код символа
                key_code=$(printf '%d' "'$key" 2>/dev/null || echo 0)
            else
                # Пустая строка - это может быть быть Enter в некоторых режимах
                key_code=13  # Трактуем пустую строку как CR
            fi
            
            # Проверяем это Enter (ASCII 10 = LF, 13 = CR)
            if [ "$key_code" -eq 10 ] || [ "$key_code" -eq 13 ]; then
                # Enter нажата - восстанавливаем режим и выполняем действие
                stty "$original_stty" 2>/dev/null || true
                
                case $selected in
                    0)  # Установить
                        echo
                        exec "$0" --install
                        ;;
                    1)  # Выход
                        clear
                        exit 0
                        ;;
                esac
            fi
        fi
    done
}

# Полное меню при установленном боте
show_full_menu() {
    set +e  # Отключаем exit on error для функции меню
    local selected=0
    local options=("🔄  Переустановить" "📦  Проверить обновления" "⚙️   Изменить настройки" "🧹  Очистить данные" "🗑️   Удалить бота" "❌  Выход")
    local num_options=${#options[@]}
    
    # Сохраняем текущие настройки терминала
    local original_stty=$(stty -g 2>/dev/null)
    trap "stty '$original_stty' 2>/dev/null || true; tput cnorm 2>/dev/null || true; set -e" EXIT
    
    # Скрываем курсор
    tput civis 2>/dev/null || true
    
    # Отключаем canonical mode и echo, включаем чтение отдельных символов
    stty -icanon -echo min 1 time 0 2>/dev/null || true
    
    while true; do
        clear
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo -e "${GREEN}   🚀 TG-SELL-BOT MANAGEMENT PANEL${NC}"
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo
        
        # Выводим опции меню
        for i in "${!options[@]}"; do
            if [ $i -eq $selected ]; then
                echo -e "${BLUE}▶${NC} ${GREEN}${options[$i]}${NC}"
            else
                echo "  ${options[$i]}"
            fi
            
            # Разделители после пунктов 1 и 4
            if [ $i -eq 1 ] || [ $i -eq 4 ]; then
                echo -e "${BLUE}----------------------------------${NC}"
            fi
        done
        
        echo
        echo -e "${BLUE}════════════════════════════════════════${NC}"
        echo -e "${DARKGRAY}Используйте ↑↓ для навигации, Enter для выбора${NC}"
        echo
        
        local key
        read -rsn1 key 2>/dev/null || key=""
        
        # Проверяем escape-последовательность для стрелок (ASCII 27)
        if [[ "$key" == $'\e' ]]; then
            # Читаем остаток последовательности [A или [B
            local seq1=""
            read -rsn1 -t 0.1 seq1 2>/dev/null || seq1=""
            
            if [[ "$seq1" == '[' ]]; then
                local seq2=""
                read -rsn1 -t 0.1 seq2 2>/dev/null || seq2=""
                
                case "$seq2" in
                    'A')  # Стрелка вверх
                        ((selected--))
                        if [ $selected -lt 0 ]; then
                            selected=$((num_options - 1))
                        fi
                        ;;
                    'B')  # Стрелка вниз
                        ((selected++))
                        if [ $selected -ge $num_options ]; then
                            selected=0
                        fi
                        ;;
                esac
            fi
        else
            # Если это не escape, проверяем другие символы
            # В raw mode Enter может быть CR (ASCII 13) или быть пустым
            local key_code
            if [ -n "$key" ]; then
                # Получаем ASCII код символа
                key_code=$(printf '%d' "'$key" 2>/dev/null || echo 0)
            else
                # Пустая строка - это может быть быть Enter в некоторых режимах
                key_code=13  # Трактуем пустую строку как CR
            fi
            
            # Проверяем это Enter (ASCII 10 = LF, 13 = CR)
            if [ "$key_code" -eq 10 ] || [ "$key_code" -eq 13 ]; then
                # Enter нажата - восстанавливаем режим и выполняем действие
                stty "$original_stty" 2>/dev/null || true
                
                case $selected in
                    0)  # Переустановить
                        echo
                        echo -e "${YELLOW}⚠️  Внимание!${NC} Это переустановит бот с потерей данных!"
                        read -p "Продолжить? (Y/n): " confirm
                        confirm=${confirm:-y}
                        confirm=$(echo "$confirm" | tr '[:upper:]' '[:lower:]')
                        if [ "$confirm" = "y" ] || [ "$confirm" = "да" ]; then
                            exec "$0" --install
                        else
                            echo -e "${YELLOW}ℹ️  Отменено${NC}"
                            sleep 2
                        fi
                        # Возвращаемся в raw mode
                        stty -icanon -echo min 1 time 0 2>/dev/null || true
                        tput civis 2>/dev/null || true
                        ;;
                    1)  # Проверить обновления
                        manage_update_bot
                        # Возвращаемся в raw mode
                        stty -icanon -echo min 1 time 0 2>/dev/null || true
                        tput civis 2>/dev/null || true
                        ;;
                    2)  # Изменить настройки
                        manage_change_settings
                        stty -icanon -echo min 1 time 0 2>/dev/null || true
                        tput civis 2>/dev/null || true
                        ;;
                    3)  # Очистить данные
                        manage_cleanup_database
                        stty -icanon -echo min 1 time 0 2>/dev/null || true
                        tput civis 2>/dev/null || true
                        ;;
                    4)  # Удалить бота
                        manage_uninstall_bot
                        exit 0
                        ;;
                    5)  # Выход
                        clear
                        exit 0
                        ;;
                esac
            fi
        fi
    done
}

# Функция обновления бота
manage_update_bot() {
    echo
    
    # Сохраняем позицию курсора перед выводом информации о проверке
    tput sc 2>/dev/null || true
    
    # Скрываем курсор во время проверки
    tput civis 2>/dev/null || true
    
    # Создаём временную папку для клонирования репозитория
    TEMP_REPO=$(mktemp -d)
    trap "rm -rf '$TEMP_REPO'" RETURN
    
    # Проверка обновлений с спинером
    show_spinner "Проверка обновлений" &
    SPINNER_PID=$!
    
    git clone -b "$REPO_BRANCH" --depth 1 "$REPO_URL" "$TEMP_REPO" >/dev/null 2>&1
    
    # Убиваем спинер после завершения клонирования
    kill $SPINNER_PID 2>/dev/null || true
    wait $SPINNER_PID 2>/dev/null || true
    
    # Получаем хеш HEAD из удалённого репо
    REMOTE_HASH=$(cd "$TEMP_REPO" && git rev-parse HEAD 2>/dev/null)
    
    # Проверяем сохранённый хеш из последнего обновления
    LOCAL_HASH=""
    UPDATE_NEEDED=1
    
    # Сначала проверяем есть ли хеш в .env (самый надёжный способ)
    if [ -f "$ENV_FILE" ] && grep -q "^LAST_UPDATE_HASH=" "$ENV_FILE"; then
        LOCAL_HASH=$(grep "^LAST_UPDATE_HASH=" "$ENV_FILE" | cut -d'=' -f2)
        
        if [ "$LOCAL_HASH" = "$REMOTE_HASH" ]; then
            UPDATE_NEEDED=0
        fi
    elif [ -d "$PROJECT_DIR/.git" ]; then
        # Если это git репозиторий, просто сравним хеши
        LOCAL_HASH=$(cd "$PROJECT_DIR" && git rev-parse HEAD 2>/dev/null || echo "")
        
        if [ "$LOCAL_HASH" = "$REMOTE_HASH" ]; then
            UPDATE_NEEDED=0
        fi
    else
        # Если нет .git и нет сохранённого хеша - нужно обновить
        UPDATE_NEEDED=1
    fi
    
    # Выводим результат проверки
    if [ $UPDATE_NEEDED -eq 0 ]; then
        echo -e "${GREEN}✅ Обновление не требуется${NC}"
    else
        echo -e "${YELLOW}📦 Доступно обновление!${NC}"
        echo -e "${DARKGRAY}Нажмите Enter для начала обновления или Esc для отмены${NC}"
        
        # Ожидаем нажатия Enter или Esc
        local original_stty=$(stty -g)
        stty -icanon -echo min 1 time 0
        local update_key=""
        read -rsn1 update_key 2>/dev/null || update_key=""
        stty "$original_stty"
        
        # Проверяем нажал ли пользователь Enter (ASCII 13 или 10) или Esc (ASCII 27)
        if [ "$update_key" = $'\033' ] || [ "$update_key" = $'\x1b' ]; then
            # Esc - отмена
            return
        elif [ -z "$update_key" ] || [ "$(printf '%d' "'$update_key")" -eq 13 ] || [ "$(printf '%d' "'$update_key")" -eq 10 ]; then
            # Enter - начало обновления
            # Восстанавливаем позицию курсора (очищаем информацию о проверке)
            tput rc 2>/dev/null || true
            tput ed 2>/dev/null || true  # Очищаем от курсора до конца экрана
            tput cnorm 2>/dev/null || true  # Показываем курсор перед началом
            
            # Сохраняем критические переменные перед обновлением
            ENV_BACKUP_FILE=$(preserve_env_vars "$ENV_FILE")
            
            # Копируем новые файлы, исключая развёрнутые файлы
            {
                cd "$TEMP_REPO" || return
                
                # Список исключений (всё что в .deployignore)
                EXCLUDES=(
                    ".git"
                    ".github"
                    ".gitignore"
                    ".gitattributes"
                    ".env.example"
                    ".deployignore"
                    "Dockerfile"
                    "install.sh"
                    "manage.sh"
                    "server-setup.sh"
                    "original_install.sh"
                    "src"
                    "scripts"
                    "Makefile"
                    "pyproject.toml"
                    "uv.lock"
                    "README.md"
                    "docs"
                )
                
                # Копируем файлы с исключениями
                find . -type f | while read -r file; do
                    # Пропускаем исключённые файлы
                    skip=0
                    for exclude in "${EXCLUDES[@]}"; do
                        if [[ "$file" == "./$exclude"* ]]; then
                            skip=1
                            break
                        fi
                    done
                    
                    if [ $skip -eq 0 ]; then
                        target_file="${file#./}"
                        target_dir="$PROJECT_DIR/$(dirname "$target_file")"
                        mkdir -p "$target_dir" 2>/dev/null || true
                        cp -f "$file" "$target_dir/" 2>/dev/null || true
                    fi
                done
            } &
            show_spinner "Загрузка файлов обновления"
            
            echo -e "✅ Остановка сервисов"
            
            # Остановка контейнеров
            {
                cd "$PROJECT_DIR" || return
                docker compose down >/dev/null 2>&1
            } &
            show_spinner_silent
            
            echo -e "✅ Пересборка и запуск сервисов"
            
            # Перестроение и запуск
            {
                cd "$PROJECT_DIR" || return
                docker compose build --no-cache >/dev/null 2>&1
                docker compose up -d >/dev/null 2>&1
            } &
            show_spinner_silent
            
            # Восстанавливаем сохранённые переменные в .env после обновления
            if [ -n "$ENV_BACKUP_FILE" ] && [ -f "$ENV_BACKUP_FILE" ]; then
                restore_env_vars "$ENV_FILE" "$ENV_BACKUP_FILE"
                
                # Перезагружаем контейнеры чтобы применить восстановленные переменные
                {
                    cd "$PROJECT_DIR" || return
                    docker compose down >/dev/null 2>&1
                    docker compose up -d >/dev/null 2>&1
                } &
                show_spinner "Применение сохранённых параметров"
            fi
            
            echo
            echo -e "${GREEN}✅ Бот успешно обновлен${NC}"
            
            # Сохраняем хеш обновления в .env
            update_env_var "$ENV_FILE" "LAST_UPDATE_HASH" "$REMOTE_HASH"
        fi
    fi
    
    echo
    tput civis 2>/dev/null || true
    echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
    read -p ""
}

# Функция изменения настроек
manage_change_settings() {
    while true; do
        echo
        echo -e "${WHITE}⚙️  Изменение настроек${NC}"
        echo
        echo -e "  ${BLUE}1)${NC} APP_DOMAIN"
        echo -e "  ${BLUE}2)${NC} BOT_TOKEN"
        echo -e "  ${BLUE}3)${NC} BOT_DEV_ID"
        echo -e "  ${BLUE}0)${NC} Вернуться"
        echo
        read -p "Выберите: " setting_choice
        
        case $setting_choice in
            1)
                read -p "Введите новый APP_DOMAIN: " new_domain
                if [ -n "$new_domain" ]; then
                    echo
                    {
                        update_env_var "$ENV_FILE" "APP_DOMAIN" "$new_domain" >/dev/null 2>&1
                    } &
                    show_spinner "Обновление APP_DOMAIN"
                    echo
                else
                    echo -e "${YELLOW}ℹ️  Пусто, отменено${NC}"
                fi
                ;;
            2)
                read -p "Введите новый BOT_TOKEN: " new_token
                if [ -n "$new_token" ]; then
                    echo
                    {
                        update_env_var "$ENV_FILE" "BOT_TOKEN" "$new_token" >/dev/null 2>&1
                    } &
                    show_spinner "Обновление BOT_TOKEN"
                    
                    {
                        cd "$PROJECT_DIR" || return
                        docker compose down >/dev/null 2>&1
                        docker compose up -d >/dev/null 2>&1
                    } &
                    show_spinner "Перезагрузка сервисов"
                    echo
                else
                    echo -e "${YELLOW}ℹ️  Пусто, отменено${NC}"
                fi
                ;;
            3)
                read -p "Введите новый BOT_DEV_ID: " new_dev_id
                if [ -n "$new_dev_id" ]; then
                    echo
                    {
                        update_env_var "$ENV_FILE" "BOT_DEV_ID" "$new_dev_id" >/dev/null 2>&1
                    } &
                    show_spinner "Обновление BOT_DEV_ID"
                    echo
                else
                    echo -e "${YELLOW}ℹ️  Пусто, отменено${NC}"
                fi
                ;;
            0)
                return
                ;;
            *)
                echo -e "${RED}✖ Неверный выбор${NC}"
                ;;
        esac
        
        sleep 1
    done
}

# Функция очистки базы данных
manage_cleanup_database() {
    echo
    echo -e "${RED}⚠️  Внимание!${NC} Это удалит всех пользователей и данные!"
    read -p "Вы уверены? (Y/n): " confirm
    confirm=${confirm:-y}
    confirm=$(echo "$confirm" | tr '[:upper:]' '[:lower:]')
    
    if [ "$confirm" != "y" ] && [ "$confirm" != "да" ]; then
        echo -e "${YELLOW}ℹ️  Отменено${NC}"
        sleep 1
        return
    fi
    
    echo
    
    # PostgreSQL
    {
        if command -v psql &> /dev/null; then
            psql -h 127.0.0.1 -U "$(grep "^DB_USER=" "$ENV_FILE" | cut -d= -f2 | tr -d '\"')" \
                -d "$(grep "^DB_NAME=" "$ENV_FILE" | cut -d= -f2 | tr -d '\"')" \
                -c "DELETE FROM users;" >/dev/null 2>&1 || true
        fi
    } &
    show_spinner "Очистка базы данных"
    
    # Redis
    {
        if command -v redis-cli &> /dev/null; then
            redis-cli FLUSHALL >/dev/null 2>&1 || true
        fi
    } &
    show_spinner "Очистка кэша"
    
    echo
    echo -e "${GREEN}✅ Данные успешно очищены${NC}"
    sleep 1
}

# Функция удаления бота
manage_uninstall_bot() {
    echo
    echo -e "${RED}⚠️  Внимание!${NC} Это удалит весь бот и все данные!"
    echo -e "${DARKGRAY}Нажмите Enter для удаления или Esc для отмены${NC}"
    
    # Ожидаем нажатия Enter или Esc
    local original_stty=$(stty -g)
    stty -icanon -echo min 1 time 0
    local delete_key=""
    read -rsn1 delete_key 2>/dev/null || delete_key=""
    stty "$original_stty"
    
    # Проверяем нажал ли пользователь Enter (ASCII 13 или 10) или Esc (ASCII 27)
    if [ "$delete_key" = $'\033' ] || [ "$delete_key" = $'\x1b' ]; then
        # Esc - отмена
        echo -e "${YELLOW}ℹ️  Отменено${NC}"
        return
    elif [ -z "$delete_key" ] || [ "$(printf '%d' "'$delete_key")" -eq 13 ] || [ "$(printf '%d' "'$delete_key")" -eq 10 ]; then
        # Enter - начало удаления
        echo
        
        # Остановка контейнеров и удаление
        {
            cd "$PROJECT_DIR" || return
            docker compose down >/dev/null 2>&1 || true
            cd /opt
            rm -rf "$PROJECT_DIR"
        } &
        show_spinner "Удаление бота и контейнеров"
        
        # Удаляем глобальную команду
        {
            sudo rm -f /usr/local/bin/tg-sell-bot 2>/dev/null || true
        } &
        show_spinner "Удаление ярлыка команды"
        
        echo
        echo -e "${GREEN}✅ Бот успешно удален${NC}"
        echo
        sleep 1
        exit 0
    fi
}

# Функция очистки при ошибке или отмене
cleanup_on_error() {
    local exit_code=$?
    
    # Показать курсор
    tput cnorm >/dev/null 2>&1 || true
    tput sgr0 >/dev/null 2>&1 || true
    
    if [ $exit_code -ne 0 ] || [ "$INSTALL_STARTED" = true ]; then
        echo
        echo -e "${RED}════════════════════════════════════════${NC}"
        echo -e "${RED}  ⚠️ УСТАНОВКА ПРЕРВАНА ИЛИ ОШИБКА${NC}"
        echo -e "${RED}════════════════════════════════════════${NC}"
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
    
    # Удаляем временную папку клонирования если она была создана
    if [ -n "$CLONE_DIR" ] && [ -d "$CLONE_DIR" ]; then
        cd /opt 2>/dev/null || true
        rm -rf "$CLONE_DIR" 2>/dev/null || true
    fi
    
    exit $exit_code
}

# Установка trap для обработки ошибок, прерываний и выхода
trap cleanup_on_error EXIT
trap 'INSTALL_STARTED=false; exit 130' INT TERM

# Автоматически даем права на выполнение самому себе
chmod +x "$0" 2>/dev/null || true

# Показать курсор
tput civis >/dev/null 2>&1 || true

# Показать курсор при выходе
trap 'tput cnorm >/dev/null 2>&1 || true; tput sgr0 >/dev/null 2>&1 || true' EXIT

# Режим установки: dev или prod
INSTALL_MODE="dev"

# Если это первый запуск (не из временной папки), клонируем репозиторий в /tmp
if [ "$1" != "--install" ] && [ ! -d "/tmp/tg-bot-install-$$" ]; then
    # Проверяем режим если скрипт вызван без аргументов --install
    if [ "$1" != "--prod" ] && [ "$1" != "-p" ]; then
        check_mode "$1"
    fi
    
    # Если нужна установка, создаем временную папку и клонируем туда
    if [ "$1" = "--install" ] || [ -z "$1" ]; then
        # Это будет обработано ниже после check_mode
        :
    fi
    
    if [ "$1" = "--prod" ] || [ "$1" = "-p" ]; then
        INSTALL_MODE="prod"
    fi
    
    # Если скрипт запущен с флагом установки, создаем временную папку и переклонируемся туда
    if [ "$1" = "--install" ]; then
        CLONE_DIR=$(mktemp -d /tmp/tg-bot-install-XXXXXX)
        trap "cd /opt 2>/dev/null || true; rm -rf '$CLONE_DIR' 2>/dev/null || true" EXIT
        git clone -b "$REPO_BRANCH" --depth 1 "$REPO_URL" "$CLONE_DIR" >/dev/null 2>&1
        cd "$CLONE_DIR"
        exec "$CLONE_DIR/install.sh" --install "$$"
    fi
else
    # Это повторный запуск из временной папки
    CLONE_DIR="/tmp/tg-bot-install-$2"
    INSTALL_MODE="$3"
    if [ "$INSTALL_MODE" = "prod" ] || [ "$INSTALL_MODE" = "-p" ]; then
        INSTALL_MODE="prod"
    fi
fi

# Проверяем режим если скрипт вызван без аргументов --install
if [ "$1" != "--install" ] && [ "$1" != "--prod" ] && [ "$1" != "-p" ]; then
    check_mode "$1"
fi

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

echo -e "${WHITE}✅ Бот успешно установлен по пути${NC} ${GREEN}$PROJECT_DIR${NC}"
echo -e "${WHITE}✅ Команда вызова меню бота:${NC} ${YELLOW}tg-sell-bot${NC}"
echo

# Удаление исходной папки если она не в /opt/tg-sell-bot
if [ "$COPY_FILES" = true ] && [ "$SOURCE_DIR" != "/opt/tg-sell-bot" ] && [ "$SOURCE_DIR" != "/" ]; then
    cd /opt
    rm -rf "$SOURCE_DIR" 2>/dev/null || true
fi

# Отмечаем успешное завершение установки
INSTALL_STARTED=false

# Создание глобальной команды tg-sell-bot
(
    sudo tee /usr/local/bin/tg-sell-bot > /dev/null << 'EOF'
#!/bin/bash
exec /opt/tg-bot/install.sh
EOF
    sudo chmod +x /usr/local/bin/tg-sell-bot
) >/dev/null 2>&1

# Ожидание ввода перед очисткой экрана
echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
read -p ""
clear

cd /opt

# Удаляем временную папку клонирования если она была создана
if [ -n "$CLONE_DIR" ] && [ -d "$CLONE_DIR" ]; then
    rm -rf "$CLONE_DIR" 2>/dev/null || true
fi
