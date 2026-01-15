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
REPO_BRANCH="main"

# Статус обновлений
UPDATE_AVAILABLE=0
CHECK_UPDATE_PID=""
UPDATE_STATUS_FILE=""

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

# Спинер с таймером (отсчёт секунд)
show_spinner_timer() {
  local seconds=$1
  local msg="$2"
  local spin=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
  local i=0
  local delay=0.08
  local elapsed=0
  tput civis 2>/dev/null || true
  
  while [ $elapsed -lt $seconds ]; do
    local remaining=$((seconds - elapsed))
    printf "\r${GREEN}%s${NC}  %s (%d сек)" "${spin[$i]}" "$msg" "$remaining"
    
    # Крутим спинер несколько раз перед следующим обновлением секунды
    for ((j=0; j<12; j++)); do
      sleep $delay
      i=$(( (i+1) % 10 ))
    done
    
    ((elapsed++))
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

# Функция для подтверждения действия (Enter/Esc)
confirm_action() {
    local message="${1:-Продолжить?}"
    echo -e "${DARKGRAY}Нажмите Enter для подтверждения или Esc для отмены${NC}"
    
    # Ожидаем нажатия Enter или Esc
    local original_stty=$(stty -g)
    stty -icanon -echo min 1 time 0
    local key=""
    read -rsn1 key 2>/dev/null || key=""
    stty "$original_stty"
    
    # Проверяем нажал ли пользователь Enter (ASCII 13 или 10) или Esc (ASCII 27)
    if [ "$key" = $'\033' ] || [ "$key" = $'\x1b' ]; then
        # Esc - отмена
        echo -e "${YELLOW}ℹ️  Отменено${NC}"
        sleep 1
        return 1
    elif [ -z "$key" ] || [ "$(printf '%d' "'$key")" -eq 13 ] || [ "$(printf '%d' "'$key")" -eq 10 ]; then
        # Enter - подтверждение
        return 0
    fi
    return 1
}

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
    
    # Сохраняем ВСЕ переменные окружения из .env файла
    # Исключаем только комментарии и пустые строки
    if [ -f "$env_file" ]; then
        grep -v "^#" "$env_file" | grep -v "^$" > "$temp_storage" 2>/dev/null || true
    fi
    echo "$temp_storage"
}

# Функция для восстановления переменных в .env после обновления
restore_env_vars() {
    local env_file="$1"
    local temp_storage="$2"
    
    # Переменные которые НЕ следует перезаписывать (пароли, криптографические ключи)
    # Переменные которые БУДУТ восстановлены: APP_DOMAIN, BOT_TOKEN, BOT_DEV_ID, и другие пользовательские данные
    local protected_vars=(
        "APP_CRYPT_KEY"
        "DB_PASSWORD"
        "POSTGRES_PASSWORD"
        "REDIS_PASSWORD"
        "SECRET_KEY"
        "JWT_SECRET"
        "API_KEY"
    )
    
    if [ -f "$temp_storage" ]; then
        # Читаем сохранённые переменные и обновляем их в .env
        while IFS='=' read -r var_name var_value; do
            if [ -n "$var_name" ] && [ -n "$var_value" ]; then
                # Пропускаем пустые строки
                var_name=$(echo "$var_name" | xargs)
                if [ -n "$var_name" ]; then
                    # Проверяем не входит ли переменная в защищённый список
                    is_protected=0
                    for protected in "${protected_vars[@]}"; do
                        if [ "$var_name" = "$protected" ]; then
                            is_protected=1
                            break
                        fi
                    done
                    
                    # Обновляем только незащищённые переменные (включая домен, токен и ID)
                    if [ $is_protected -eq 0 ]; then
                        update_env_var "$env_file" "$var_name" "$var_value"
                    fi
                fi
            fi
        done < "$temp_storage"
        
        # Удаляем временный файл
        rm -f "$temp_storage" 2>/dev/null || true
    fi
}

# Функция для получения версии из __version__.py
get_version_from_file() {
    local version_file="$1"
    if [ -f "$version_file" ]; then
        grep -oP '__version__ = "\K[^"]+' "$version_file" 2>/dev/null || echo ""
    else
        echo ""
    fi
}

# Функция для получения локальной версии (из assets/update/.version или src/__version__.py)
get_local_version() {
    # Сначала пробуем assets/update/.version файл
    if [ -f "$PROJECT_DIR/assets/update/.version" ]; then
        cat "$PROJECT_DIR/assets/update/.version" 2>/dev/null | tr -d '\n' || echo ""
    # Fallback на старый путь assets/setup/.version (для совместимости)
    elif [ -f "$PROJECT_DIR/assets/setup/.version" ]; then
        cat "$PROJECT_DIR/assets/setup/.version" 2>/dev/null | tr -d '\n' || echo ""
    # Fallback на старый путь .version
    elif [ -f "$PROJECT_DIR/.version" ]; then
        cat "$PROJECT_DIR/.version" 2>/dev/null | tr -d '\n' || echo ""
    # Fallback на src/__version__.py
    elif [ -f "$PROJECT_DIR/src/__version__.py" ]; then
        get_version_from_file "$PROJECT_DIR/src/__version__.py"
    else
        echo ""
    fi
}

# Функция для проверки доступности обновлений
check_updates_available() {
    # Создаем временный файл для хранения статуса и версии
    UPDATE_STATUS_FILE=$(mktemp)
    echo "0" > "$UPDATE_STATUS_FILE"
    
    # Проверка обновлений в фоне
    {
        # Получаем локальную версию из PROJECT_DIR (production)
        LOCAL_VERSION=$(get_local_version)
        
        # Получаем удаленную версию через GitHub raw URL
        # Формат: https://raw.githubusercontent.com/owner/repo/branch/path/to/file
        GITHUB_RAW_URL=$(echo "$REPO_URL" | sed 's|github.com|raw.githubusercontent.com|; s|\.git$||')
        REMOTE_VERSION_URL="${GITHUB_RAW_URL}/${REPO_BRANCH}/src/__version__.py"
        
        # Скачиваем файл версии с GitHub
        REMOTE_VERSION=$(curl -s "$REMOTE_VERSION_URL" 2>/dev/null | grep -oP '__version__ = "\K[^"]+' || echo "")
        
        # Сравниваем версии
        if [ -n "$REMOTE_VERSION" ] && [ -n "$LOCAL_VERSION" ]; then
            if [ "$LOCAL_VERSION" != "$REMOTE_VERSION" ]; then
                echo "1|$REMOTE_VERSION" > "$UPDATE_STATUS_FILE"
            else
                echo "0|$REMOTE_VERSION" > "$UPDATE_STATUS_FILE"
            fi
        else
            echo "0|unknown" > "$UPDATE_STATUS_FILE"
        fi
    } &
    CHECK_UPDATE_PID=$!
}

wait_for_update_check() {
    if [ -n "$CHECK_UPDATE_PID" ]; then
        wait $CHECK_UPDATE_PID 2>/dev/null || true
    fi
    
    # Читаем результат из файла (формат: status|version)
    if [ -n "$UPDATE_STATUS_FILE" ] && [ -f "$UPDATE_STATUS_FILE" ]; then
        local update_info=$(cat "$UPDATE_STATUS_FILE" 2>/dev/null || echo "0|unknown")
        UPDATE_AVAILABLE=$(echo "$update_info" | cut -d'|' -f1)
        AVAILABLE_VERSION=$(echo "$update_info" | cut -d'|' -f2)
        rm -f "$UPDATE_STATUS_FILE" 2>/dev/null || true
    fi
}

# Функция для проверки режима (установка или меню)
check_mode() {
    # Если передан аргумент --install, пропускаем меню
    if [ "$1" = "--install" ]; then
        return 0
    fi
    
    # Проверяем обновления в фоне перед показом меню
    check_updates_available
    
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
    
    # Ждём завершения проверки обновлений
    wait_for_update_check
    
    # Формируем опции меню
    local options=("🔄  Обновить" "ℹ️   Просмотр логов" "📊  Логи в реальном времени" "🔃  Перезагрузить бота" "🔃  Перезагрузить с логами" "⬆️   Включить бота" "⬇️   Выключить бота" "🔄  Переустановить" "⚙️   Изменить настройки" "🧹  Очистить данные" "🗑️   Удалить бота" "❌  Выход")
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
                # Для пункта "Обновить" добавляем статус если доступно обновление
                if [ $i -eq 0 ] && [ $UPDATE_AVAILABLE -eq 1 ]; then
                    if [ -n "$AVAILABLE_VERSION" ] && [ "$AVAILABLE_VERSION" != "unknown" ]; then
                        echo -e "${BLUE}▶${NC} ${GREEN}${options[$i]} ${YELLOW}( Доступно обновление - версия $AVAILABLE_VERSION ! )${NC}"
                    else
                        echo -e "${BLUE}▶${NC} ${GREEN}${options[$i]} ${YELLOW}( Доступно обновление! )${NC}"
                    fi
                else
                    echo -e "${BLUE}▶${NC} ${GREEN}${options[$i]}${NC}"
                fi
            else
                # Для пункта "Обновить" добавляем статус если доступно обновление
                if [ $i -eq 0 ] && [ $UPDATE_AVAILABLE -eq 1 ]; then
                    if [ -n "$AVAILABLE_VERSION" ] && [ "$AVAILABLE_VERSION" != "unknown" ]; then
                        echo -e "  ${options[$i]} ${YELLOW}( Доступно обновление - версия $AVAILABLE_VERSION ! )${NC}"
                    else
                        echo -e "  ${options[$i]} ${YELLOW}( Доступно обновление! )${NC}"
                    fi
                else
                    echo "  ${options[$i]}"
                fi
            fi
            
            # Разделители после пунктов 2, 6 и 10
            if [ $i -eq 2 ] || [ $i -eq 6 ] || [ $i -eq 10 ]; then
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
                    0)  # Обновить
                        manage_update_bot
                        stty -icanon -echo min 1 time 0 2>/dev/null || true
                        tput civis 2>/dev/null || true
                        ;;
                    1)  # Просмотр логов
                        manage_view_logs
                        # Возвращаемся в raw mode
                        stty -icanon -echo min 1 time 0 2>/dev/null || true
                        tput civis 2>/dev/null || true
                        ;;
                    2)  # Логи в реальном времени
                        manage_view_logs_live
                        stty -icanon -echo min 1 time 0 2>/dev/null || true
                        tput civis 2>/dev/null || true
                        ;;
                    3)  # Перезагрузить бота
                        manage_restart_bot
                        stty -icanon -echo min 1 time 0 2>/dev/null || true
                        tput civis 2>/dev/null || true
                        ;;
                    4)  # Перезагрузить с логами
                        manage_restart_bot_with_logs
                        ;;
                    5)  # Включить бота
                        manage_start_bot
                        stty -icanon -echo min 1 time 0 2>/dev/null || true
                        tput civis 2>/dev/null || true
                        ;;
                    6)  # Выключить бота
                        manage_stop_bot
                        stty -icanon -echo min 1 time 0 2>/dev/null || true
                        tput civis 2>/dev/null || true
                        ;;
                    7)  # Переустановить
                        manage_reinstall_bot
                        stty -icanon -echo min 1 time 0 2>/dev/null || true
                        tput civis 2>/dev/null || true
                        ;;
                    8)  # Изменить настройки
                        manage_change_settings
                        stty -icanon -echo min 1 time 0 2>/dev/null || true
                        tput civis 2>/dev/null || true
                        ;;
                    9)  # Очистить данные
                        manage_reset_data
                        stty -icanon -echo min 1 time 0 2>/dev/null || true
                        tput civis 2>/dev/null || true
                        ;;
                    10)  # Удалить бота
                        manage_uninstall_bot
                        ;;
                    11)  # Выход
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
    clear
    echo -e "${BLUE}========================================${NC}"
    echo -e "${GREEN}       🔄 ОБНОВЛЕНИЕ TG-SELL-BOT${NC}"
    echo -e "${BLUE}========================================${NC}"
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
    
    # Получаем версии
    REMOTE_VERSION=$(get_version_from_file "$TEMP_REPO/src/__version__.py")
    LOCAL_VERSION=$(get_local_version)
    
    UPDATE_NEEDED=1
    
    # Проверяем версии
    if [ -n "$REMOTE_VERSION" ] && [ -n "$LOCAL_VERSION" ]; then
        if [ "$LOCAL_VERSION" = "$REMOTE_VERSION" ]; then
            UPDATE_NEEDED=0
        fi
    else
        # Fallback на старый метод с хешами если версии не доступны
        REMOTE_HASH=$(cd "$TEMP_REPO" && git rev-parse HEAD 2>/dev/null)
        LOCAL_HASH=""
        
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
    fi
    
    # Выводим результат проверки
    if [ $UPDATE_NEEDED -eq 0 ]; then
        clear
        echo -e "${BLUE}========================================${NC}"
        echo -e "${GREEN}       🔄 ОБНОВЛЕНИЕ TG-SELL-BOT${NC}"
        echo -e "${BLUE}========================================${NC}"
        echo
        if [ -n "$LOCAL_VERSION" ] && [ "$LOCAL_VERSION" != "unknown" ]; then
            echo -e "${GREEN}✅ Обновление не требуется${NC}"
            echo -e "${GRAY}Текущая версия: $LOCAL_VERSION${NC}"
        else
            echo -e "${GREEN}✅ Обновление не требуется${NC}"
        fi
    else
        # Автоматическое начало обновления без диалога
        clear
        
        # Сохраняем критические переменные перед обновлением
        ENV_BACKUP_FILE=$(preserve_env_vars "$ENV_FILE")
            
            # Копируем только необходимые файлы конфигурации в PROJECT_DIR
            {
                cd "$TEMP_REPO" || return
                
                # Список файлов для копирования в PROJECT_DIR (только конфигурация)
                INCLUDE_FILES=(
                    "docker-compose.yml"
                    "assets"
                )
                
                for item in "${INCLUDE_FILES[@]}"; do
                    if [ -e "$item" ]; then
                        if [ -d "$item" ]; then
                            mkdir -p "$PROJECT_DIR/$item" 2>/dev/null || true
                            # Копируем всё содержимое
                            if [ "$item" = "assets" ]; then
                                # Для папки assets копируем всё содержимое
                                for subitem in "$item"/*; do
                                    subname=$(basename "$subitem")
                                    if [ -d "$subitem" ]; then
                                        # Для папки banners - копируем только если папка не существует
                                        if [ "$subname" = "banners" ]; then
                                            if [ ! -d "$PROJECT_DIR/$item/banners" ]; then
                                                cp -r "$subitem" "$PROJECT_DIR/$item/" 2>/dev/null || true
                                            else
                                                # Папка существует, копируем всё кроме default.jpg (пользовательский баннер)
                                                for banner_file in "$subitem"/*; do
                                                    banner_name=$(basename "$banner_file")
                                                    if [ "$banner_name" != "default.jpg" ]; then
                                                        if [ -f "$banner_file" ]; then
                                                            cp -f "$banner_file" "$PROJECT_DIR/$item/banners/" 2>/dev/null || true
                                                        fi
                                                    fi
                                                done
                                            fi
                                        else
                                            cp -r "$subitem" "$PROJECT_DIR/$item/" 2>/dev/null || true
                                        fi
                                    else
                                        cp -f "$subitem" "$PROJECT_DIR/$item/" 2>/dev/null || true
                                    fi
                                done
                            else
                                cp -r "$item"/* "$PROJECT_DIR/$item/" 2>/dev/null || true
                            fi
                        else
                            cp -f "$item" "$PROJECT_DIR/" 2>/dev/null || true
                        fi
                    fi
                done
                
                # Сохраняем версию в assets/update/.version файл для корректной проверки версий
                mkdir -p "$PROJECT_DIR/assets/update" 2>/dev/null || true
                local new_version=$(grep -oP '__version__ = "\K[^"]+' "src/__version__.py" 2>/dev/null || echo "")
                if [ -n "$new_version" ]; then
                    echo "$new_version" > "$PROJECT_DIR/assets/update/.version"
                fi
                
                # Копируем install.sh в папку assets/update
                cp -f "install.sh" "$PROJECT_DIR/assets/update/install.sh" 2>/dev/null || true
                chmod +x "$PROJECT_DIR/assets/update/install.sh" 2>/dev/null || true
            } &
            show_spinner "Обновление конфигурации"
            
            {
                cd "$PROJECT_DIR" || return
                docker compose down >/dev/null 2>&1
            } &
            show_spinner "Остановка сервисов"
            
            {
                # Собираем образ из временной папки с исходниками
                cd "$TEMP_REPO" || return
                docker build --no-cache -t remnashop:local . >/dev/null 2>&1
                
                # Запускаем контейнеры из PROJECT_DIR
                cd "$PROJECT_DIR" || return
                docker compose up -d >/dev/null 2>&1
            } &
            show_spinner "Пересборка и запуск сервисов"
            
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
            
            # Ожидание запуска бота
            (sleep 5) &
            
            echo
            echo -e "${YELLOW}Запуск бота. Пожалуйста ожидайте.${NC}"
            echo
            
            # Ждем появления логотипа DFC в логах
            local max_attempts=90
            local attempt=0
            local dfc_found=false
            local error_found=false
            
            while [ $attempt -lt $max_attempts ]; do
                local logs=$(docker compose -f "$PROJECT_DIR/docker-compose.yml" logs remnashop 2>&1)
                
                # Проверяем наличие логотипа DFC
                if echo "$logs" | grep -q "Digital.*Freedom.*Core"; then
                    dfc_found=true
                    break
                fi
                
                # Проверяем наличие критических ошибок (строки начинающиеся с ERROR, CRITICAL, или содержащие Traceback)
                if echo "$logs" | grep -E "^\s*(ERROR|CRITICAL|Traceback)" >/dev/null 2>&1; then
                    error_found=true
                    break
                fi
                
                ((attempt++))
                sleep 1
            done
            
            echo
            
            if [ "$dfc_found" = true ]; then
                echo -e "${GREEN}✅ Бот успешно обновлен${NC}"
                
                # Сохраняем хеш обновления в .env
                update_env_var "$ENV_FILE" "LAST_UPDATE_HASH" "$REMOTE_HASH"
                
                echo
                echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
                read -p ""
                
                # Перезапускаем скрипт чтобы вернуться в главное меню
                # При перезапуске check_updates_available автоматически пересчитает флаг обновления
                exec "$0"
            elif [ "$error_found" = true ]; then
                echo -e "${RED}❌ Ошибка при обновлении бота!${NC}"
                echo
                echo -ne "${YELLOW}Показать лог ошибки? [Y/n]: ${NC}"
                read -n 1 -r show_logs
                echo
                
                if [[ -z "$show_logs" || "$show_logs" =~ ^[Yy]$ ]]; then
                    echo
                    echo -e "${BLUE}========================================${NC}"
                    echo -e "${RED}ЛОГИ ОШИБОК:${NC}"
                    echo -e "${BLUE}========================================${NC}"
                    docker compose -f "$PROJECT_DIR/docker-compose.yml" logs --tail 50 remnashop
                    echo -e "${BLUE}========================================${NC}"
                fi
                
                echo
                echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
                read -p ""
                return
            else
                echo -e "${YELLOW}⚠️  Превышено время ожидания (${max_attempts}сек)${NC}"
                echo -e "${YELLOW}Бот может всё ещё запускаться...${NC}"
                
                # Сохраняем хеш обновления даже при таймауте
                update_env_var "$ENV_FILE" "LAST_UPDATE_HASH" "$REMOTE_HASH"
                
                echo
                echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
                read -p ""
                
                # Перезапускаем скрипт
                exec "$0"
            fi
    fi
}

# Функция перезагрузки бота с ожиданием логотипа DFC
manage_restart_bot() {
    clear
    echo -e "${BLUE}========================================${NC}"
    echo -e "${GREEN}      🔃 ПЕРЕЗАГРУЗКА TG-SELL-BOT${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
    echo -e "${YELLOW}Бот будет перезагружен...${NC}"
    echo
    
    {
        cd "$PROJECT_DIR" || return
        docker compose down >/dev/null 2>&1
        docker compose up -d >/dev/null 2>&1
    } &
    show_spinner "Перезагрузка бота"
    
    echo
    echo -e "${YELLOW}Запуск бота. Пожалуйста ожидайте.${NC}"
    echo
    
    # Ждем появления логотипа DFC в логах (строка с "Digital  Freedom   Core")
    local max_attempts=90
    local attempt=0
    local dfc_found=false
    local error_found=false
    
    while [ $attempt -lt $max_attempts ]; do
        local logs=$(docker logs remnashop 2>&1 | tail -100)
        
        # Проверяем наличие логотипа DFC
        if echo "$logs" | grep -q "Digital.*Freedom.*Core"; then
            dfc_found=true
            break
        fi
        
        # Проверяем наличие критических ошибок
        if echo "$logs" | grep -E "^\s*(ERROR|CRITICAL|Traceback)" >/dev/null 2>&1; then
            error_found=true
            break
        fi
        
        # Показываем прогресс каждые 5 секунд
        if [ $((attempt % 5)) -eq 0 ] && [ $attempt -gt 0 ]; then
            echo -e "${DARKGRAY}  Ожидание запуска... (${attempt}/${max_attempts}сек)${NC}"
        fi
        
        ((attempt++))
        sleep 1
    done
    
    echo
    if [ "$dfc_found" = true ]; then
        echo -e "${GREEN}✅ Бот успешно перезагружен${NC}"
    elif [ "$error_found" = true ]; then
        echo -e "${RED}❌ Обнаружена ошибка при запуске. Проверьте логи.${NC}"
    else
        echo -e "${YELLOW}⚠️  Превышено время ожидания (${max_attempts}сек), но бот может быть готов${NC}"
    fi
    
    echo
    echo -e "${BLUE}========================================${NC}"
    tput civis 2>/dev/null || true
    echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
    read -p ""
}

# Функция перезагрузки бота с отображением логов
manage_restart_bot_with_logs() {
    clear
    echo -e "${BLUE}========================================${NC}"
    echo -e "${GREEN}    🔃📊 ПЕРЕЗАГРУЗКА С ЛОГАМИ TG-SELL-BOT${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
    echo -e "${YELLOW}Бот будет перезагружен с отображением логов...${NC}"
    echo -e "${DARKGRAY}(Нажмите Ctrl+C для выхода из логов)${NC}"
    echo
    
    # Восстанавливаем нормальные настройки терминала
    stty sane 2>/dev/null || true
    tput cnorm 2>/dev/null || true
    
    cd "$PROJECT_DIR" || return
    
    # Перезагружаем и одновременно смотрим логи
    docker compose down >/dev/null 2>&1
    docker compose up -d >/dev/null 2>&1
    sleep 2
    
    # Выводим логи с автоматическим обновлением
    docker compose logs -f remnashop
    
    # После выхода из логов возвращаемся в меню
    echo
    tput civis 2>/dev/null || true
    echo -e "${DARKGRAY}Нажмите Enter для возврата в меню${NC}"
    read -p ""
}

# Функция переустановки бота с удалением всех данных
manage_reinstall_bot() {
    clear
    echo -e "${BLUE}========================================${NC}"
    echo -e "${GREEN}      🔄 ПЕРЕУСТАНОВКА TG-SELL-BOT${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
    echo -e "${RED}⚠️  ВНИМАНИЕ!${NC}"
    echo -e "${RED}Это действие удалит весь бот и ВСЕ данные:${NC}"
    echo -e "  - База данных PostgreSQL"
    echo -e "  - Redis/Valkey"
    echo -e "  - Все конфигурационные файлы"
    echo -e "  - Логи и кэш"
    echo
    echo -e "${YELLOW}После этого будет произведена чистая переустановка бота.${NC}"
    echo
    
    if ! confirm_action; then
        return
    fi
    
    echo
    
    # Удаляем контейнеры и данные
    {
        cd "$PROJECT_DIR" || return
        docker compose down -v >/dev/null 2>&1 || true
        
        # Удаляем все локальные данные
        rm -rf "$PROJECT_DIR/db_data" 2>/dev/null || true
        rm -rf "$PROJECT_DIR/redis_data" 2>/dev/null || true
        rm -rf "$PROJECT_DIR/.env" 2>/dev/null || true
    } &
    show_spinner "Удаление данных и контейнеров"
    
    echo
    
    # Запускаем переустановку
    if confirm_action "Начать переустановку?"; then
        # Восстанавливаем нормальные настройки терминала
        stty sane 2>/dev/null || true
        tput cnorm 2>/dev/null || true
        
        # Запускаем скрипт установки
        exec "$0" --install
    else
        echo -e "${YELLOW}Переустановка отменена${NC}"
        echo
        echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
        read -p ""
        tput civis 2>/dev/null || true
    fi
}

# Функция выключения бота
manage_stop_bot() {
    clear
    echo -e "${BLUE}========================================${NC}"
    echo -e "${GREEN}      ⬇️  ВЫКЛЮЧЕНИЕ TG-SELL-BOT${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
    echo -e "${YELLOW}Бот будет выключен...${NC}"
    echo
    
    {
        cd "$PROJECT_DIR" || return
        docker compose down >/dev/null 2>&1
    } &
    show_spinner "Выключение бота"
    
    echo
    echo -e "${GREEN}✅ Бот успешно выключен${NC}"
    echo
    echo -e "${BLUE}========================================${NC}"
    tput civis 2>/dev/null || true
    echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
    read -p ""
}

# Функция включения бота
manage_start_bot() {
    clear
    echo -e "${BLUE}========================================${NC}"
    echo -e "${GREEN}      ⬆️  ВКЛЮЧЕНИЕ TG-SELL-BOT${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
    echo -e "${YELLOW}Бот будет включен...${NC}"
    echo
    
    {
        cd "$PROJECT_DIR" || return
        docker compose up -d >/dev/null 2>&1
    } &
    show_spinner "Включение бота"
    
    echo
    echo -e "${GREEN}✅ Бот успешно включен${NC}"
    echo
    echo -e "${BLUE}========================================${NC}"
    tput civis 2>/dev/null || true
    echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
    read -p ""
}

# Функция просмотра логов
manage_view_logs() {
    clear
    echo -e "${BLUE}========================================${NC}"
    echo -e "${GREEN}       📋 ПРОСМОТР ЛОГОВ TG-SELL-BOT${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
    echo -e "${DARKGRAY}Последние 50 строк логов...${NC}"
    echo -e "${DARKGRAY}(Нажмите Enter для продолжения)${NC}"
    echo
    
    cd "$PROJECT_DIR" || return
    docker compose logs remnashop 2>&1 | tail -50
    
    echo
    tput civis 2>/dev/null || true
    echo -e "${DARKGRAY}Нажмите Enter для возврата в меню${NC}"
    read -p ""
}

# Функция просмотра логов в реальном времени
manage_view_logs_live() {
    clear
    echo -e "${BLUE}========================================${NC}"
    echo -e "${GREEN}     📊 ЛОГИ В РЕАЛЬНОМ ВРЕМЕНИ TG-SELL-BOT${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
    echo -e "${DARKGRAY}Запуск просмотра логов...${NC}"
    echo -e "${DARKGRAY}(Для выхода нажмите Ctrl+C)${NC}"
    echo
    
    # Восстанавливаем нормальные настройки терминала
    stty sane 2>/dev/null || true
    tput cnorm 2>/dev/null || true
    
    cd "$PROJECT_DIR" || return
    docker compose logs -f remnashop
    
    # После выхода возвращаемся в raw mode
    tput civis 2>/dev/null || true
    echo
    echo -e "${DARKGRAY}Нажмите Enter для возврата в меню${NC}"
    read -p ""
}

# Функция изменения настроек
manage_change_settings() {
    local settings=(
        "🌐 Изменить домен"
        "🤖 Изменить Токен телеграм бота"
        "👤 Изменить Телеграм ID разработчика"
    )
    
    while true; do
        local selected_setting=0
        while true; do
            # Полностью очищаем экран и скрываем курсор
            clear
            tput civis 2>/dev/null || true
            
            echo -e "${BLUE}========================================${NC}"
            echo -e "${GREEN}       ⚙️  ИЗМЕНЕНИЕ НАСТРОЕК${NC}"
            echo -e "${BLUE}========================================${NC}"
            echo
            
            # Отображаем элементы меню
            for i in "${!settings[@]}"; do
                if [ $i -eq $selected_setting ]; then
                    echo -e "${BLUE}▶${NC} ${GREEN}${settings[$i]}${NC}"
                else
                    echo -e "  ${settings[$i]}"
                fi
            done
            
            # Разделитель и кнопка "Назад"
            echo -e "${BLUE}----------------------------------${NC}"
            if [ $selected_setting -eq ${#settings[@]} ]; then
                echo -e "${BLUE}▶${NC} ${GREEN}⬅️  Назад${NC}"
            else
                echo -e "  ⬅️  Назад"
            fi
            echo
            echo -e "${BLUE}========================================${NC}"
            echo -e "${DARKGRAY}Используйте ↑↓ для навигации, Enter для выбора${NC}"
            
            # Ожидаем нажатия клавиши
            local original_stty=$(stty -g)
            stty -icanon -echo min 1 time 0
            local key=""
            read -rsn1 key 2>/dev/null || key=""
            stty "$original_stty"
            
            # Обработка навигации
            case "$key" in
                $'\033')  # Esc
                    read -rsn1 -t 0.1 && read -rsn1 arrow 2>/dev/null || arrow=""
                    case "$arrow" in
                        'A')  # Стрелка вверх
                            selected_setting=$(( (selected_setting - 1 + ${#settings[@]} + 1) % (${#settings[@]} + 1) ))
                            ;;
                        'B')  # Стрелка вниз
                            selected_setting=$(( (selected_setting + 1) % (${#settings[@]} + 1) ))
                            ;;
                        *)  # Просто Esc - выход
                            tput cnorm 2>/dev/null || true
                            echo -e "${YELLOW}ℹ️  Отменено${NC}"
                            sleep 1
                            return
                            ;;
                    esac
                    ;;
                '')  # Enter
                    break
                    ;;
            esac
        done
        
        # Показываем курсор для ввода
        tput cnorm 2>/dev/null || true
        
        # Обработка выбранного пункта
        if [ $selected_setting -eq ${#settings[@]} ]; then
            # Нажата кнопка "Назад"
            return
        fi
        
        case $selected_setting in
            0)  # Изменить домен
                while true; do
                    clear
                    tput civis 2>/dev/null || true
                    
                    echo -e "${BLUE}========================================${NC}"
                    echo -e "${GREEN}       🌐 ИЗМЕНИТЬ ДОМЕН${NC}"
                    echo -e "${BLUE}========================================${NC}"
                    echo -e "${DARKGRAY}Введите новые данные или нажмите Esc для отмены${NC}"
                    echo -e "${DARKGRAY}--------------------------------------------------------------------${NC}"
                    echo
                    echo "Текущее значение: $(grep "^APP_DOMAIN=" "$ENV_FILE" | cut -d'=' -f2)"
                    
                    # Используем простой read для ввода без редактирования промпта
                    echo -n -e "${YELLOW}Введите новый домен:${NC} "
                    tput cnorm 2>/dev/null || true
                    read new_domain
                    
                    tput civis 2>/dev/null || true
                    echo
                    
                    if [ -z "$new_domain" ]; then
                        echo -e "${YELLOW}ℹ️  Отменено${NC}"
                        echo
                        echo -e "${BLUE}========================================${NC}"
                        echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
                        read -p ""
                        break
                    else
                        echo -e "${DARKGRAY}--------------------------------------------------------------------${NC}"
                        echo
                        {
                            old_domain=$(grep "^APP_DOMAIN=" "$ENV_FILE" | cut -d'=' -f2)
                            update_env_var "$ENV_FILE" "APP_DOMAIN" "$new_domain" >/dev/null 2>&1
                            # Обновляем Caddyfile в /opt/remnawave/caddy/
                            if [ -f "/opt/remnawave/caddy/Caddyfile" ]; then
                                # Экранируем точки для sed
                                old_domain_escaped=$(printf '%s\n' "$old_domain" | sed -e 's/[\.]/\\&/g')
                                new_domain_escaped=$(printf '%s\n' "$new_domain" | sed -e 's/[\/&]/\\&/g')
                                sed -i "s/https:\/\/$old_domain_escaped/https:\/\/$new_domain_escaped/g" /opt/remnawave/caddy/Caddyfile 2>/dev/null || true
                            fi
                        } &
                        show_spinner "Обновление домена"
                        echo -e "${GREEN}✅ Домен обновлён${NC}"
                        echo
                        echo -e "${BLUE}========================================${NC}"
                        echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
                        read -p ""
                        break
                    fi
                done
                ;;
            1)  # Изменить Токен телеграм бота
                while true; do
                    clear
                    tput civis 2>/dev/null || true
                    
                    echo -e "${BLUE}========================================${NC}"
                    echo -e "${GREEN}       🤖 ИЗМЕНИТЬ ТОКЕН ТЕЛЕГРАМ БОТА${NC}"
                    echo -e "${BLUE}========================================${NC}"
                    echo -e "${DARKGRAY}Введите новые данные или нажмите Esc для отмены${NC}"
                    echo -e "${DARKGRAY}--------------------------------------------------------------------${NC}"
                    echo
                    echo "Текущее значение: (скрыто)"
                    
                    # Используем простой read для ввода без редактирования промпта
                    echo -n -e "${YELLOW}Введите новый токен:${NC} "
                    tput cnorm 2>/dev/null || true
                    read new_token
                    
                    tput civis 2>/dev/null || true
                    echo
                    
                    if [ -z "$new_token" ]; then
                        echo -e "${YELLOW}ℹ️  Отменено${NC}"
                        echo
                        echo -e "${BLUE}========================================${NC}"
                        echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
                        read -p ""
                        break
                    else
                        echo -e "${DARKGRAY}--------------------------------------------------------------------${NC}"
                        echo
                        {
                            update_env_var "$ENV_FILE" "BOT_TOKEN" "$new_token" >/dev/null 2>&1
                        } &
                        show_spinner "Обновление токена"
                        
                        {
                            cd "$PROJECT_DIR" || return
                            docker compose down >/dev/null 2>&1
                            docker compose up -d >/dev/null 2>&1
                        } &
                        show_spinner "Перезагрузка сервисов"
                        echo -e "${GREEN}✅ Токен обновлён и сервисы перезагружены${NC}"
                        echo
                        echo -e "${BLUE}========================================${NC}"
                        echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
                        read -p ""
                        break
                    fi
                done
                ;;
            2)  # Изменить Телеграм ID разработчика
                while true; do
                    clear
                    tput civis 2>/dev/null || true
                    
                    echo -e "${BLUE}========================================${NC}"
                    echo -e "${GREEN}       👤 ИЗМЕНИТЬ ТЕЛЕГРАМ ID РАЗРАБОТЧИКА${NC}"
                    echo -e "${BLUE}========================================${NC}"
                    echo -e "${DARKGRAY}Введите новые данные или нажмите Esc для отмены${NC}"
                    echo -e "${DARKGRAY}--------------------------------------------------------------------${NC}"
                    echo
                    echo "Текущее значение: $(grep "^BOT_DEV_ID=" "$ENV_FILE" | cut -d'=' -f2)"
                    
                    # Используем простой read для ввода без редактирования промпта
                    echo -n -e "${YELLOW}Введите новый ID:${NC} "
                    tput cnorm 2>/dev/null || true
                    read new_dev_id
                    
                    tput civis 2>/dev/null || true
                    echo
                    
                    if [ -z "$new_dev_id" ]; then
                        echo -e "${YELLOW}ℹ️  Отменено${NC}"
                        echo
                        echo -e "${BLUE}========================================${NC}"
                        echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
                        read -p ""
                        break
                    else
                        echo -e "${DARKGRAY}--------------------------------------------------------------------${NC}"
                        echo
                        {
                            update_env_var "$ENV_FILE" "BOT_DEV_ID" "$new_dev_id" >/dev/null 2>&1
                        } &
                        show_spinner "Обновление ID разработчика"
                        echo -e "${GREEN}✅ ID обновлён${NC}"
                        echo
                        echo -e "${BLUE}========================================${NC}"
                        echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
                        read -p ""
                        break
                    fi
                done
                ;;
        esac
    done
}

# Функция очистки базы данных
manage_cleanup_database() {
    clear
    echo -e "${BLUE}========================================${NC}"
    echo -e "${GREEN}       🧹 ОЧИСТКА БАЗЫ ДАННЫХ${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
    echo -e "${RED}⚠️  Внимание!${NC} Это удалит всех пользователей и данные!"
    echo
    
    if ! confirm_action; then
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
    echo
    echo -e "${BLUE}========================================${NC}"
    echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
    read -p ""
}

# Функция удаления бота
manage_uninstall_bot() {
    clear
    echo -e "${BLUE}========================================${NC}"
    echo -e "${GREEN}       🗑️  УДАЛЕНИЕ TG-SELL-BOT${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo
    echo -e "${RED}⚠️  Внимание!${NC} Это удалит весь бот и все данные!"
    echo
    
    if ! confirm_action; then
        return
    fi
    
    echo
    
    # Подготовка к удалению
    {
        remove_from_caddy >/dev/null 2>&1 || true
    } &
    show_spinner "Подготовка к удалению"
    
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
    echo -e "${GREEN}✅ Бот успешно удален!${NC}"
    echo
    echo -e "${DARKGRAY}Нажмите Enter для продолжения.${NC}"
    read -p ""
    clear
    exit 0
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

remove_from_caddy() {
    local caddy_dir="/opt/remnawave/caddy"
    local caddy_file="${caddy_dir}/Caddyfile"

    # Если Caddy нет — выходим
    [ -d "$caddy_dir" ] || return 0
    [ -f "$caddy_file" ] || return 0

    # Получаем домен из .env
    local app_domain=""
    if [ -f "$ENV_FILE" ]; then
        app_domain=$(grep "^APP_DOMAIN=" "$ENV_FILE" | cut -d'=' -f2 | tr -d '"' | tr -d "'")
    fi

    # Если домен не найден, выходим
    [ -z "$app_domain" ] && return 0

    # Удаляем блок с доменом из Caddyfile используя sed
    # Ищем блок начинающийся с https://$app_domain { и заканчивающийся }
    sed -i "/^https:\/\/${app_domain}\s*{/,/^}/d" "$caddy_file" 2>/dev/null || true

    # Также удаляем пустые строки вокруг удаленного блока
    sed -i '/^$/N;/^\n$/d' "$caddy_file" 2>/dev/null || true

    # Перезапускаем Caddy
    cd "$caddy_dir"
    docker compose down >/dev/null 2>&1
    docker compose up -d >/dev/null 2>&1
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
        "Makefile"
        "pyproject.toml"
        "uv.lock"
        ".deployignore"
        "README.md"
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
      
      # Копируем директории (src, scripts и assets)
      for dir in "src" "scripts" "assets"; do
          if [ -d "$SOURCE_DIR/$dir" ]; then
              rm -rf "$PROJECT_DIR/$dir" 2>/dev/null || true
              cp -r "$SOURCE_DIR/$dir" "$PROJECT_DIR/"
          fi
      done
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
echo -e "${GREEN}       🚀 ПРОЦЕСС УСТАНОВКИ${NC}"
echo -e "${BLUE}========================================${NC}"
echo

# 1. СНАЧАЛА - Создание конфигурации (в фоне со спинером)
(
  # Автогенерация ключей безопасности
  if grep -q "^APP_CRYPT_KEY=$" "$ENV_FILE"; then
    APP_CRYPT_KEY=$(openssl rand -base64 32 | tr -d '\n')
    update_env_var "$ENV_FILE" "APP_CRYPT_KEY" "$APP_CRYPT_KEY"
  fi

  if grep -q "^BOT_SECRET_TOKEN=$" "$ENV_FILE"; then
    BOT_SECRET_TOKEN=$(openssl rand -hex 64 | tr -d '\n')
    update_env_var "$ENV_FILE" "BOT_SECRET_TOKEN" "$BOT_SECRET_TOKEN"
  fi

  # Генерация пароля БД
  if grep -q "^DATABASE_PASSWORD=" "$ENV_FILE"; then
    CURRENT_DB_PASS=$(grep "^DATABASE_PASSWORD=" "$ENV_FILE" | cut -d'=' -f2 | tr -d ' ')
    if [ -z "$CURRENT_DB_PASS" ]; then
      DATABASE_PASSWORD=$(openssl rand -hex 32 | tr -d '\n')
      update_env_var "$ENV_FILE" "DATABASE_PASSWORD" "$DATABASE_PASSWORD"
    else
      DATABASE_PASSWORD="$CURRENT_DB_PASS"
    fi
  else
    DATABASE_PASSWORD=$(openssl rand -hex 32 | tr -d '\n')
    echo "DATABASE_PASSWORD=$DATABASE_PASSWORD" >> "$ENV_FILE"
  fi

  # Синхронизируем DATABASE_USER с POSTGRES_USER
  DATABASE_USER=$(grep "^DATABASE_USER=" "$ENV_FILE" | cut -d'=' -f2 | tr -d ' ')
  if [ -n "$DATABASE_USER" ]; then
    if grep -q "^POSTGRES_USER=" "$ENV_FILE"; then
      update_env_var "$ENV_FILE" "POSTGRES_USER" "$DATABASE_USER"
    else
      echo "POSTGRES_USER=$DATABASE_USER" >> "$ENV_FILE"
    fi
  fi

  # Синхронизируем DATABASE_PASSWORD с POSTGRES_PASSWORD
  if grep -q "^POSTGRES_PASSWORD=" "$ENV_FILE"; then
    update_env_var "$ENV_FILE" "POSTGRES_PASSWORD" "$DATABASE_PASSWORD"
  else
    echo "POSTGRES_PASSWORD=$DATABASE_PASSWORD" >> "$ENV_FILE"
  fi

  # Синхронизируем DATABASE_NAME с POSTGRES_DB
  DATABASE_NAME=$(grep "^DATABASE_NAME=" "$ENV_FILE" | cut -d'=' -f2 | tr -d ' ')
  if [ -n "$DATABASE_NAME" ]; then
    if grep -q "^POSTGRES_DB=" "$ENV_FILE"; then
      update_env_var "$ENV_FILE" "POSTGRES_DB" "$DATABASE_NAME"
    else
      echo "POSTGRES_DB=$DATABASE_NAME" >> "$ENV_FILE"
    fi
  fi

  # Генерация пароля Redis
  if grep -q "^REDIS_PASSWORD=$" "$ENV_FILE"; then
    CURRENT_REDIS_PASS=$(grep "^REDIS_PASSWORD=" "$ENV_FILE" | cut -d'=' -f2 | tr -d ' ')
    if [ -z "$CURRENT_REDIS_PASS" ]; then
      REDIS_PASSWORD=$(openssl rand -hex 32 | tr -d '\n')
      update_env_var "$ENV_FILE" "REDIS_PASSWORD" "$REDIS_PASSWORD"
    fi
  fi

  if grep -q "^REMNAWAVE_WEBHOOK_SECRET=" "$ENV_FILE"; then
    CURRENT_WEBHOOK_SECRET=$(grep "^REMNAWAVE_WEBHOOK_SECRET=" "$ENV_FILE" | cut -d'=' -f2 | tr -d ' ')
    if [ -z "$CURRENT_WEBHOOK_SECRET" ]; then
      REMNAWAVE_WEBHOOK_SECRET=$(openssl rand -hex 32 | tr -d '\n')
      update_env_var "$ENV_FILE" "REMNAWAVE_WEBHOOK_SECRET" "$REMNAWAVE_WEBHOOK_SECRET"
    fi
  fi
) &
show_spinner "Создание конфигурации"

# 2. Синхронизация webhook (в фоне со спинером)
(
  REMNAWAVE_ENV="/opt/remnawave/.env"

  if [ -f "$REMNAWAVE_ENV" ]; then
    # Включаем webhook
    if grep -q "^WEBHOOK_ENABLED=" "$REMNAWAVE_ENV"; then
      sed -i "s|^WEBHOOK_ENABLED=.*|WEBHOOK_ENABLED=true|" "$REMNAWAVE_ENV"
    else
      echo "WEBHOOK_ENABLED=true" >> "$REMNAWAVE_ENV"
    fi

    # Копируем WEBHOOK_SECRET_HEADER
    REMNAWAVE_SECRET=$(grep "^WEBHOOK_SECRET_HEADER=" "$REMNAWAVE_ENV" | cut -d'=' -f2)
    if [ -n "$REMNAWAVE_SECRET" ]; then
      update_env_var "$ENV_FILE" "REMNAWAVE_WEBHOOK_SECRET" "$REMNAWAVE_SECRET"
    fi

    # Подставляем домен
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

# 3. Создание структуры папок (в фоне со спинером)
(
  mkdir -p "$PROJECT_DIR"/{assets,backups,logs}
) &
show_spinner "Создание структуры папок"

# 4. Удаление старых томов БД для свежей установки (в фоне со спинером)
(
  cd "$PROJECT_DIR"
  # Останавливаем контейнеры если они есть
  docker compose down >/dev/null 2>&1 || true
  # Удаляем том БД чтобы PostgreSQL переинициализировалась с правильными паролями
  docker volume rm remnashop-db-data >/dev/null 2>&1 || true
) &
show_spinner "Очистка старых данных БД"

# 5. Сборка Docker образа (в фоне со спинером)
(
  cd "$PROJECT_DIR"
  docker compose build >/dev/null 2>&1
) &
show_spinner "Сборка Docker образа"

# 6. Запуск контейнеров (в фоне со спинером)
(
  cd "$PROJECT_DIR"
  docker compose up -d >/dev/null 2>&1
) &
show_spinner "Запуск сервисов"

# 7. Инициализация БД (в фоне со спинером)
(
  sleep 20
) &
show_spinner "Инициализация базы данных"

# 8. Настройка и перезапуск Caddy (в фоне со спинером)
if [ -d "/opt/remnawave/caddy" ]; then
  (
    configure_caddy "$APP_DOMAIN"
  ) &
  show_spinner "Настройка и перезапуск Caddy"
fi

# 9. Очистка ненужных файлов в целевой директории
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
# Запускаем install.sh из папки assets/update
if [ -f "/opt/tg-bot/assets/update/install.sh" ]; then
    exec /opt/tg-bot/assets/update/install.sh
else
    # Fallback на основной install.sh для обратной совместимости
    exec /opt/tg-bot/install.sh
fi
EOF
    sudo chmod +x /usr/local/bin/tg-sell-bot
) >/dev/null 2>&1

# Ожидание ввода перед возвратом в главное меню
echo -e "${DARKGRAY}Нажмите Enter для продолжения${NC}"
read -p ""
clear

cd /opt

# Удаляем временную папку клонирования если она была создана
if [ -n "$CLONE_DIR" ] && [ -d "$CLONE_DIR" ]; then
    rm -rf "$CLONE_DIR" 2>/dev/null || true
fi

# Возвращаемся в главное меню
show_full_menu

# Возвращаемся в главное меню
show_full_menu
