# Layout
space = {" "}
empty = { "!empty!" }
btn-test = Кнопка
msg-test = Сообщение
development = Временно недоступно!
test-payment = Тестовый платеж
unlimited = ∞
unknown = —
expired = Закончилась

unit-unlimited = { $value ->
    [-1] { unlimited }
    [0] { unlimited }
    *[other] { $value }
}

# Other
payment-invoice-description = { purchase-type } подписки { $name } на { $duration }
payment-invoice-topup = Пополнение баланса на { $amount }
payment-invoice-extra-devices = Покупка дополнительных устройств ({ $device_count } шт.)
contact-support-help = Здравствуйте! Мне нужна помощь.
contact-support-paysupport = Здравствуйте! Я бы хотел запросить возврат средств.
contact-support-withdraw-points = Здравствуйте! Я бы хотел запросить обмен баллов.
cmd-start = Перезапустить бота
cmd-paysupport = Возврат средств
cmd-help = Помощь

referral-invite-message =
    {space}

    ✨ TEST Online - Ваш приватный интернет!

    ➡️ Подключиться: { $url }

# Headers
hdr-user = <b>👤 Пользователь:</b>
hdr-user-profile = <b>👤 Ваш профиль:</b>

hdr-subscription = <b>📋 Ваша подписка:</b>

hdr-plan = <b>📦 План:</b>
hdr-payment = <b>💰 Платеж:</b>
hdr-error = <b>⚠️ Ошибка:</b>
hdr-node = <b>🖥 Нода:</b>
hdr-hwid = <b>📱 Устройство:</b>

# Fragments
frg-user =
    <blockquote>
    • <b>ID</b>: <code>{ $user_id }</code>
    • <b>Имя</b>: { $user_name }
    • <b>Реферальный код</b>: <code>{ $referral_code }</code>
    • <b>Скидка</b>: { $discount_value }%{ $discount_value ->
    [0] {""}
    *[other] { $discount_is_permanent ->
        [1] {" "}(Постоянная)
        *[0] { $discount_remaining ->
            [0] {" "}(Одноразовая)
            *[other] {" "}(Осталось { $discount_remaining } { $discount_remaining ->
                [1] день
                [2] дня
                [3] дня
                [4] дня
                *[other] дней
            })
        }
    }
    }
    { $is_balance_enabled ->
        [1] • <b>Баланс</b>: { $balance } ₽
        *[0] {""}
    }
    { $is_balance_separate ->
        [1] • <b>Бонусы</b>: { $referral_balance } ₽
        *[0] {""}
    }
    </blockquote>

frg-user-info =
    <blockquote>
    • <b>ID</b>: <code>{ $user_id }</code>
    • <b>Имя</b>: { $user_name } { $username -> 
        [0] { empty }
        *[HAS] (<a href="tg://user?id={ $user_id }">@{ $username }</a>)
    }
    </blockquote>

frg-user-details =
    <blockquote>
    • <b>ID</b>: <code>{ $user_id }</code>
    • <b>Имя</b>: { $user_name } { $username -> 
        [0] { space }
        *[HAS] (<a href="tg://user?id={ $user_id }">@{ $username }</a>)
    }
    • <b>Роль</b>: { role }
    • <b>Язык</b>: { language }
    • <b>Реферальный код</b>: <code>{ $referral_code }</code>
    • <b>Баланс</b>: { $balance } ₽
    </blockquote>

frg-user-discounts-details =
    <blockquote>
    • <b>Персональная</b>: { $personal_discount }%
    • <b>На следующую покупку</b>: { $purchase_discount }%
    </blockquote>

frg-subscription =
    <blockquote>
    • <b>Тариф:</b> { $plan_name }
    • <b>Лимит трафика</b>: { $traffic_limit }
    • <b>Лимит устройств</b>: { $device_limit_number }{ $device_limit_bonus ->
        [0] { $extra_devices ->
            [0] {""}
            *[other] {" "}(+{ $extra_devices } доп.)
        }
        *[other] +{ $device_limit_bonus }{ $extra_devices ->
            [0] {""}
            *[other] {" "}(+{ $extra_devices } доп.)
        }
    }
    • <b>Осталось</b>: { $expire_time }
    </blockquote>

# Примечание: frg-subscription-devices убран как дубликат frg-subscription
# Используйте { frg-subscription } вместо { frg-subscription-devices }

frg-subscription-details =
    <blockquote>
    • <b>ID</b>: <code>{ $subscription_id }</code>
    • <b>Статус</b>: { subscription-status }
    • <b>Тариф:</b> { $plan_name }
    • <b>Трафик</b>: { $traffic_used } / { $traffic_limit }
    • <b>Лимит устройств</b>: { $device_limit_number }{ $device_limit_bonus ->
        [0] { $extra_devices ->
            [0] {""}
            *[other] {" "}(+{ $extra_devices } доп.)
        }
        *[other] +{ $device_limit_bonus }{ $extra_devices ->
            [0] {""}
            *[other] {" "}(+{ $extra_devices } доп.)
        }
    }
    • <b>Осталось</b>: { $expire_time }
    </blockquote>

frg-payment-info =
    <blockquote>
    • <b>ID</b>: <code>{ $payment_id }</code>
    • <b>Способ оплаты</b>: { gateway-type }
    • <b>Сумма</b>: { frg-payment-amount }
    </blockquote>

frg-payment-amount = { $final_amount } { $discount_percent -> 
    [0] { space }
    *[more] { space } <strike>{ $original_amount }</strike> (-{ $discount_percent }%)
    }

frg-plan-snapshot =
    <blockquote>
    • <b>План</b>: <code>{ $plan_name }</code>
    • <b>Тип</b>: { plan-type }
    • <b>Лимит трафика</b>: { $plan_traffic_limit }
    • <b>Лимит устройств</b>: { $plan_device_limit }
    • <b>Длительность</b>: { $plan_duration }
    </blockquote>

frg-plan-snapshot-comparison =
    <blockquote>
    • <b>План</b>: <code>{ $previous_plan_name }</code> -> <code>{ $plan_name }</code>
    • <b>Тип</b>: { $previous_plan_type } -> { plan-type }
    • <b>Лимит трафика</b>: { $previous_plan_traffic_limit } -> { $plan_traffic_limit }
    • <b>Лимит устройств</b>: { $previous_plan_device_limit } -> { $plan_device_limit }
    • <b>Длительность</b>: { $previous_plan_duration } -> { $plan_duration }
    </blockquote>

frg-node-info =
    <blockquote>
    • <b>Название</b>: { $country } { $name }
    • <b>Адрес</b>: <code>{ $address }:{ $port }</code>
    • <b>Трафик</b>: { $traffic_used } / { $traffic_limit }
    { $last_status_message -> 
    [0] { empty }
    *[HAS] • <b>Последний статус</b>: { $last_status_message }
    }
    { $last_status_change -> 
    [0] { empty }
    *[HAS] • <b>Статус изменен</b>: { $last_status_change }
    }
    </blockquote>

frg-user-hwid =
    <blockquote>
    • <b>HWID</b>: <code>{ $hwid }</code>

    • <b>Платформа</b>: { $platform }
    • <b>Модель</b>: { $device_model }
    • <b>Версия ОС</b>: { $os_version }
    • <b>Агент</b>: { $user_agent }
    </blockquote>

frg-build-info =
    { $has_build ->
    [0] { space }
    *[HAS]
    <b>🏗️ Информация о сборке:</b>
    <blockquote>
    Время сборки: { $time }
    Ветка: { $branch } ({ $tag })
    Коммит: <a href="{ $commit_url }">{ $commit }</a>
    </blockquote>
    }

# Roles
role-dev = Разработчик
role-admin = Администратор
role-user = Пользователь
role = 
    { $role ->
    [DEV] { role-dev }
    [ADMIN] { role-admin }
    *[USER] { role-user }
}


# Units
unit-device = { $value -> 
    [-1] { unlimited }
    *[other] { $value } 
} { $value ->
    [-1] { space }
    [one] устройство
    [few] устройства
    *[other] устройств
}

unit-byte = { $value } Б
unit-kilobyte = { $value } КБ
unit-megabyte = { $value } МБ
unit-gigabyte = { $value } ГБ
unit-terabyte = { $value } ТБ

unit-second = { $value } { $value ->
    [one] секунда
    [few] секунды
    *[other] секунд
}

unit-minute = { $value } { $value ->
    [one] минута
    [few] минуты
    *[other] минут
}

unit-hour = { $value } { $value ->
    [one] час
    [few] часа
    *[other] часов
}

unit-day = { $value } { $value ->
    [one] день
    [few] дня
    *[other] дней
}

unit-month = { $value } { $value ->
    [one] месяц
    [few] месяца
    *[other] месяцев
}

unit-year = { $value } { $value ->
    [one] год
    [few] года
    *[other] лет
}


# Types
plan-type = { $plan_type -> 
    [TRAFFIC] Трафик
    [DEVICES] Устройства
    [BOTH] Трафик + устройства
    [UNLIMITED] Безлимитный
    *[OTHER] { $plan_type }
}

promocode-type = { $promocode_type -> 
    [DURATION] Длительность
    [TRAFFIC] Трафик
    [DEVICES] Устройства
    [SUBSCRIPTION] Подписка
    [PERSONAL_DISCOUNT] Постоянная скидка
    [PURCHASE_DISCOUNT] Одноразовая скидка
    *[OTHER] { $promocode_type }
}

promocode-type-name = { $type -> 
    [DURATION] Дни к подписке
    [TRAFFIC] Трафик
    [DEVICES] Устройства
    [SUBSCRIPTION] Подписка
    [PERSONAL_DISCOUNT] Постоянная скидка
    [PURCHASE_DISCOUNT] Одноразовая скидка
    *[OTHER] { $type }
}

availability-type = { $availability_type -> 
    [ALL] Для всех
    [NEW] Для новых
    [EXISTING] Для существующих
    [INVITED] Для приглашенных
    [ALLOWED] Для разрешенных
    [TRIAL] Для пробника
    *[OTHER] { $availability_type }
}

gateway-type = { $gateway_type ->
    [TELEGRAM_STARS] ⭐ Telegram Stars
    [YOOKASSA] 💳 ЮKassa
    [YOOMONEY] 💳 ЮMoney
    [CRYPTOMUS] 🔐 Cryptomus
    [HELEKET] 💎 Heleket
    [URLPAY] UrlPay
    [BALANCE] 💰 С баланса
    *[OTHER] { $gateway_type }
}

access-mode = { $access_mode ->
    [PUBLIC] 🟢 Разрешен для всех
    [INVITED] 🟡 Разрешен для приглашенных
    [RESTRICTED] 🔴 Запрещен для всех
    *[OTHER] { $access_mode }
}

audience-type = { $audience_type ->
    [ALL] Всем
    [PLAN] По плану
    [SUBSCRIBED] С подпиской
    [UNSUBSCRIBED] Без подписки
    [EXPIRED] Просроченным
    [TRIAL] С пробником
    *[OTHER] { $audience_type }
}

broadcast-status = { $broadcast_status ->
    [PROCESSING] В процессе
    [COMPLETED] Завершена
    [CANCELED] Отменена
    [DELETED] Удалена
    [ERROR] Ошибка
    *[OTHER] { $broadcast_status }
}

transaction-status = { $transaction_status ->
    [PENDING] Ожидание
    [COMPLETED] Завершена
    [CANCELED] Отменена
    [REFUNDED] Возврат
    [FAILED] Ошибка
    *[OTHER] { $transaction_status }
}

subscription-status = { $subscription_status ->
    [ACTIVE] Активна
    [DISABLED] Отключена
    [LIMITED] Исчерпан трафик
    [EXPIRED] Истекла
    [DELETED] Удалена
    *[OTHER] { $subscription_status }
}

purchase-type = { $purchase_type ->
    [NEW] Покупка
    [RENEW] Продление
    [CHANGE] Изменение
    *[OTHER] { $purchase_type }
}

traffic-strategy = { $strategy_type -> 
    [NO_RESET] При оплате
    [DAY] Каждый день
    [WEEK] Каждую неделю
    [MONTH] Каждый месяц
    *[OTHER] { $strategy_type }
    }

reward-type = { $reward_type -> 
    [POINTS] Баллы
    [EXTRA_DAYS] Дни
    [MONEY] Деньги
    *[OTHER] { $reward_type }
    }

accrual-strategy = { $accrual_strategy_type -> 
    [ON_FIRST_PAYMENT] Первый платеж
    [ON_EACH_PAYMENT] Каждый платеж
    *[OTHER] { $accrual_strategy_type }
    }

reward-strategy = { $reward_strategy_type -> 
    [AMOUNT] Фиксированная
    [PERCENT] Процентная
    *[OTHER] { $reward_strategy_type }
    }

# Фрагмент: Текущая подписка с проверкой наличия
# Примечание: используйте plan_name вместо current_plan_name для согласованности
frg-subscription-conditional =
    { $has_subscription ->
    [true]
    { frg-subscription }
    *[false]
    <blockquote>
    • У вас нет оформленной подписки.
    </blockquote>
    }

# Фрагмент: Полный статус подписки (с пояснениями)
frg-subscription-status-full =
    { $status ->
    [ACTIVE] { frg-subscription }
    [EXPIRED]
    <blockquote>
    • Срок действия истек.
    
    <i>{ $is_trial ->
    [0] Ваша подписка истекла. Продлите ее, чтобы продолжить пользоваться сервисом!
    *[1] Ваш бесплатный пробный период закончился. Оформите подписку, чтобы продолжить пользоваться сервисом!
    }</i>
    </blockquote>
    [LIMITED]
    <blockquote>
    • Ваш трафик израсходован.

    <i>{ $is_trial ->
    [0] { $traffic_strategy ->
        [NO_RESET] Продлите подписку, чтобы сбросить трафик и продолжить пользоваться сервисом!
        *[RESET] Трафик будет восстановлен через { $reset_time }. Вы также можете продлить подписку, чтобы сбросить трафик.
        }
    *[1] { $traffic_strategy ->
        [NO_RESET] Оформите подписку, чтобы продолжить пользоваться сервисом!
        *[RESET] Трафик будет восстановлен через { $reset_time }. Вы также можете оформить подписку, чтобы пользоваться сервисом без ограничений.
        }
    }</i>
    </blockquote>
    [DISABLED]
    <blockquote>
    • Ваша подписка отключена.

    <i>Свяжитесь с поддержкой для выяснения причины!</i>
    </blockquote>
    *[NONE]
    <blockquote>
    • У вас нет оформленной подписки.
    </blockquote>

    <i>ℹ️ Для получения доступа перейдите в меню <b>«Подписка»</b>.</i>
    }

# Фрагмент: Короткий статус подписки (для админки)
frg-subscription-status-short =
    { $status ->
    [ACTIVE]
    { frg-subscription }
    [EXPIRED]
    <blockquote>
    • Срок действия истек.
    </blockquote>
    [LIMITED]
    <blockquote>
    • Превышен лимит трафика.
    </blockquote>
    [DISABLED]
    <blockquote>
    • Подписка отключена.
    </blockquote>
    *[NONE]
    <blockquote>
    • Нет текущей подписки.
    </blockquote>
    }

# Фрагмент: Предупреждение о типе покупки
frg-purchase-type-warning =
    { $purchase_type ->
    [RENEW] <i>⚠️ Текущая подписка будет <u>продлена</u>.</i>
    [CHANGE] <i>⚠️ Текущая подписка будет <u>заменена</u> без пересчета оставшегося срока.</i>
    *[OTHER] { empty }
    }

# Фрагмент: Заголовок подтверждения покупки
frg-purchase-confirm-header =
    { $purchase_type ->
    [RENEW] <b>🛒 Подтверждение продления подписки</b>
    [CHANGE] <b>🛒 Подтверждение изменения подписки</b>
    *[OTHER] <b>🛒 Подтверждение покупки подписки</b>
    }

language = { $language ->
    [ar] Арабский
    [az] Азербайджанский
    [be] Белорусский
    [cs] Чешский
    [de] Немецкий
    [en] Английский
    [es] Испанский
    [fa] Персидский
    [fr] Французский
    [he] Иврит
    [hi] Хинди
    [id] Индонезийский
    [it] Итальянский
    [ja] Японский
    [kk] Казахский
    [ko] Корейский
    [ms] Малайский
    [nl] Нидерландский
    [pl] Польский
    [pt] Португальский
    [ro] Румынский
    [ru] Русский
    [sr] Сербский
    [tr] Турецкий
    [uk] Украинский
    [uz] Узбекский
    [vi] Вьетнамский
    *[OTHER] { $language }
}