import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

SITE_URL = os.getenv("SITE_URL", "https://finfit.kz")
MANAGER_USERNAME = os.getenv("MANAGER_USERNAME", "@finfit_manager")
COURSE_LINK = os.getenv("COURSE_LINK", "https://finfit.getcourse.ru")

CHANNEL_ID = os.getenv("CHANNEL_ID", "")
CHAT_ID = os.getenv("CHAT_ID", "")  # опционально: отдельный чат клуба

DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///finbot.db")

ROBOKASSA_LOGIN = os.getenv("ROBOKASSA_LOGIN", "")
ROBOKASSA_PASSWORD1 = os.getenv("ROBOKASSA_PASSWORD1", "")
ROBOKASSA_PASSWORD2 = os.getenv("ROBOKASSA_PASSWORD2", "")
ROBOKASSA_TEST_PASSWORD1 = os.getenv("ROBOKASSA_TEST_PASSWORD1", "")
ROBOKASSA_TEST_PASSWORD2 = os.getenv("ROBOKASSA_TEST_PASSWORD2", "")
ROBOKASSA_IS_TEST = os.getenv("ROBOKASSA_IS_TEST", "1")
ROBOKASSA_TAX = os.getenv("ROBOKASSA_TAX", "none")
# Включить после одобрения рекуррента в поддержке Robokassa (иначе ошибка 34)
ROBOKASSA_RECURRING_ENABLED = os.getenv("ROBOKASSA_RECURRING_ENABLED", "0") == "1"
# Чек (Receipt) — только если в Robokassa подключена онлайн-касса
ROBOKASSA_USE_RECEIPT = os.getenv("ROBOKASSA_USE_RECEIPT", "0") == "1"
ROBOKASSA_SUCCESS_URL = os.getenv("ROBOKASSA_SUCCESS_URL", "https://t.me/finfitclub_bot")
ROBOKASSA_FAIL_URL = os.getenv("ROBOKASSA_FAIL_URL", "https://t.me/finfitclub_bot")

GETCOURSE_ACCOUNT = os.getenv("GETCOURSE_ACCOUNT", "")
GETCOURSE_API_KEY = os.getenv("GETCOURSE_API_KEY", "")
GETCOURSE_GROUP_NAME = os.getenv("GETCOURSE_GROUP_NAME", "")

TARIFFS = {
    "1m": {"name": "1 месяц", "price": 8900, "days": 30},
    "6m": {"name": "6 месяцев", "price": 45000, "days": 180},
    "12m": {"name": "12 месяцев", "price": 72000, "days": 365},
}

TARIFF_PROGRESSION = {
    "1m": ["1m", "6m", "12m"],
    "6m": ["6m", "12m"],
    "12m": ["12m"],
}

WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8080"))
LOG_FILE = os.getenv("LOG_FILE", "finbot.log")
