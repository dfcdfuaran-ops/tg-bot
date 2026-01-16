from typing import Optional

from aiogram.fsm.state import State, StatesGroup


class MainMenu(StatesGroup):
    MAIN = State()
    CONNECT = State()
    DEVICES = State()
    INVITE = State()
    INVITE_ABOUT = State()
    INVITE_QR = State()
    BALANCE = State()
    BALANCE_TOPUP = State()
    BALANCE_AMOUNTS = State()
    BALANCE_AMOUNT = State()
    BALANCE_CONFIRM = State()
    BALANCE_TRANSFER = State()  # Меню перевода баланса
    BALANCE_TRANSFER_RECIPIENT = State()  # Ввод получателя
    BALANCE_TRANSFER_RECIPIENT_HISTORY = State()  # История получателей переводов
    BALANCE_TRANSFER_AMOUNT_VALUE = State()  # Выбор суммы из preset
    BALANCE_TRANSFER_AMOUNT_MANUAL = State()  # Ручной ввод суммы
    BALANCE_TRANSFER_MESSAGE = State()  # Ввод сообщения для перевода
    BALANCE_SUCCESS = State()  # Успешное пополнение баланса
    BONUS_ACTIVATE = State()
    BONUS_ACTIVATE_CUSTOM = State()


class Notification(StatesGroup):
    CLOSE = State()


class Subscription(StatesGroup):
    MAIN = State()
    DEVICES = State()
    ADD_DEVICE = State()
    ADD_DEVICE_SELECT_COUNT = State()
    ADD_DEVICE_DURATION = State()  # Выбор типа покупки (до конца подписки / до конца месяца)
    ADD_DEVICE_PAYMENT = State()
    ADD_DEVICE_CONFIRM = State()
    ADD_DEVICE_SUCCESS = State()
    ADD_DEVICE_PAYMENT_LINK = State()  # Экран ссылки платежа
    EXTRA_DEVICES_LIST = State()  # Список купленных дополнительных устройств
    EXTRA_DEVICE_MANAGE = State()  # Управление конкретной покупкой
    PROMOCODE = State()
    REFERRAL_CODE = State()
    REFERRAL_SUCCESS = State()
    PLANS = State()
    DURATION = State()
    PAYMENT_METHOD = State()
    CONFIRM = State()
    CONFIRM_BALANCE = State()
    CONFIRM_YOOMONEY = State()
    CONFIRM_YOOKASSA = State()
    SUCCESS = State()
    FAILED = State()
    TRIAL = State()



class Dashboard(StatesGroup):
    MAIN = State()


# Состояния для меню управления БД
class DashboardDB(StatesGroup):
    MAIN = State()
    LOAD = State()
    IMPORTER = State()
    SYNC = State()  # Меню синхронизации
    SYNC_PROGRESS = State()  # Процесс синхронизации
    CLEAR_ALL_CONFIRM = State()  # Подтверждение полной очистки
    CLEAR_USERS_CONFIRM = State()  # Подтверждение очистки пользователей


class DashboardStatistics(StatesGroup):
    MAIN = State()


class DashboardBroadcast(StatesGroup):
    MAIN = State()
    LIST = State()
    VIEW = State()
    PLAN = State()
    SEND = State()
    CONTENT = State()
    BUTTONS = State()


class DashboardPromocodes(StatesGroup):
    MAIN = State()
    LIST = State()
    SEARCH = State()
    CONFIGURATOR = State()
    VIEW = State()
    NAME = State()
    CODE = State()
    TYPE = State()
    AVAILABILITY = State()
    REWARD = State()
    LIFETIME = State()
    LIFETIME_INPUT = State()
    QUANTITY = State()
    QUANTITY_INPUT = State()
    ALLOWED = State()


class DashboardAccess(StatesGroup):
    MAIN = State()
    CONDITIONS = State()
    RULES = State()
    CHANNEL = State()


class DashboardFeatures(StatesGroup):
    MAIN = State()


class DashboardSettings(StatesGroup):
    MAIN = State()
    
    # Баланс
    BALANCE = State()
    BALANCE_MIN_AMOUNT = State()
    BALANCE_MIN_AMOUNT_MANUAL = State()
    BALANCE_MAX_AMOUNT = State()
    BALANCE_MAX_AMOUNT_MANUAL = State()
    
    # Переводы
    TRANSFERS = State()
    TRANSFERS_COMMISSION_TYPE = State()
    TRANSFERS_COMMISSION_VALUE = State()
    TRANSFERS_COMMISSION_MANUAL = State()
    TRANSFERS_MIN_AMOUNT = State()
    TRANSFERS_MIN_AMOUNT_MANUAL = State()
    TRANSFERS_MAX_AMOUNT = State()
    TRANSFERS_MAX_AMOUNT_MANUAL = State()
    
    # Доп. устройства
    EXTRA_DEVICES = State()
    EXTRA_DEVICES_PRICE = State()
    EXTRA_DEVICES_PRICE_MANUAL = State()
    
    # Глобальная скидка
    GLOBAL_DISCOUNT = State()
    GLOBAL_DISCOUNT_VALUE = State()
    GLOBAL_DISCOUNT_MANUAL = State()
    GLOBAL_DISCOUNT_APPLY_TO = State()  # Меню "Влияние"
    GLOBAL_DISCOUNT_MODE = State()  # Меню "Режим"
    
    # Соглашение (ToS)
    TOS = State()
    TOS_URL_MANUAL = State()
    
    # Сообщество
    COMMUNITY = State()
    COMMUNITY_URL_MANUAL = State()
    
    # Финансы
    FINANCES = State()
    
    # Курсы валют
    CURRENCY_RATES = State()
    CURRENCY_RATE_USD = State()
    CURRENCY_RATE_EUR = State()
    CURRENCY_RATE_STARS = State()


class DashboardUsers(StatesGroup):
    MAIN = State()
    SEARCH = State()
    SEARCH_RESULTS = State()
    RECENT_REGISTERED = State()
    RECENT_ACTIVITY = State()
    ALL_USERS = State()  # Все пользователи
    BLACKLIST = State()


class DashboardUser(StatesGroup):
    MAIN = State()
    SUBSCRIPTION = State()
    TRAFFIC_LIMIT = State()
    DEVICE_LIMIT = State()
    EXPIRE_TIME = State()
    SQUADS = State()
    INTERNAL_SQUADS = State()
    EXTERNAL_SQUADS = State()
    DEVICES_LIST = State()
    DISCOUNT = State()
    POINTS = State()  # Balance menu with two options
    MAIN_BALANCE = State()  # Main user balance
    REFERRAL_BALANCE = State()  # Referral balance
    STATISTICS = State()
    ROLE = State()
    TRANSACTIONS_LIST = State()
    TRANSACTION = State()
    GIVE_ACCESS = State()
    MESSAGE = State()
    SYNC = State()
    SYNC_WAITING = State()
    GIVE_SUBSCRIPTION = State()
    SUBSCRIPTION_DURATION = State()


class DashboardRemnashop(StatesGroup):
    MAIN = State()
    ADMINS = State()
    ADVERTISING = State()
    EXTRA_DEVICES = State()
    EXTRA_DEVICES_PRICE = State()
    EXTRA_DEVICES_PRICE_MANUAL = State()


class RemnashopReferral(StatesGroup):
    MAIN = State()
    LEVEL = State()
    REWARD = State()
    REWARD_MANUAL_INPUT = State()
    REWARD_TYPE = State()
    ACCRUAL_STRATEGY = State()
    REWARD_STRATEGY = State()
    INVITE_MESSAGE = State()
    INVITE_MESSAGE_EDIT = State()
    INVITE_MESSAGE_PREVIEW = State()


class RemnashopGateways(StatesGroup):
    MAIN = State()
    SETTINGS = State()
    FIELD = State()
    CURRENCY = State()
    PLACEMENT = State()


class RemnashopNotifications(StatesGroup):
    MAIN = State()
    USER = State()
    SYSTEM = State()


class RemnashopPlans(StatesGroup):
    MAIN = State()
    CONFIGURATOR = State()
    NAME = State()
    DESCRIPTION = State()
    TAG = State()
    TYPE = State()
    AVAILABILITY = State()
    TRAFFIC = State()
    DEVICES = State()
    DURATIONS = State()
    DURATION_ADD = State()
    PRICES = State()
    PRICE = State()
    ALLOWED = State()
    SQUADS = State()
    INTERNAL_SQUADS = State()
    EXTERNAL_SQUADS = State()


class DashboardRemnawave(StatesGroup):
    MAIN = State()
    USERS = State()
    HOSTS = State()
    NODES = State()
    INBOUNDS = State()


class DashboardImporter(StatesGroup):
    MAIN = State()
    FROM_XUI = State()
    SYNC = State()
    SQUADS = State()
    IMPORT_COMPLETED = State()
    SYNC_COMPLETED = State()


def state_from_string(state_str: str, sep: Optional[str] = ":") -> Optional[State]:
    try:
        group_name, state_name = state_str.split(":")[:2]
        group_cls = globals().get(group_name)
        if group_cls is None:
            return None
        state_obj = getattr(group_cls, state_name, None)
        if not isinstance(state_obj, State):
            return None
        return state_obj
    except (ValueError, AttributeError):
        return None
