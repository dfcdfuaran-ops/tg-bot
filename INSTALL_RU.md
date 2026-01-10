# QUICK START для Remnashop Bot
# 
# ✨ Одна команда для полной установки:
# ./install.sh
#
# Скрипт install.sh автоматически:
# 1. Создаст .env файл
# 2. Попросит ввести обязательные параметры
# 3. Сгенерирует все ключи и пароли
# 4. Запустит Docker Compose
#
# Что необходимо иметь перед установкой:
# - Docker и Docker Compose
# - OpenSSL
#
# Обязательные параметры:
# - APP_DOMAIN: Домен вашего бота (например: bot.example.com)
# - BOT_TOKEN: Получить у @BotFather в Telegram
# - BOT_DEV_ID: Ваш Telegram ID (найти можно у @userinfobot)
# - BOT_SUPPORT_USERNAME: Никнейм бота поддержки (без @)
# - REMNAWAVE_TOKEN: API токен из панели Remnawave
# - REMNAWAVE_WEBHOOK_SECRET: Секрет webhook из панели Remnawave
#
# После установки:
# - docker compose logs -f remnashop  # Просмотр логов
# - docker compose down               # Остановка сервиса
# - docker compose restart            # Перезапуск сервиса
