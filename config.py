import os

# На Railway змінні оточення вставляються напряму — dotenv не потрібен.
# Для локальної розробки можна встановити python-dotenv і розкоментувати рядки нижче:
# from dotenv import load_dotenv
# load_dotenv()

# ── Налаштування ──────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("Змінна BOT_TOKEN не встановлена! Додай її в Railway → Variables.")

# Юзернейм вчителя (без @) — запасний варіант авторизації
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")

# ID адміна в Telegram (надійніший спосіб авторизації, ніж username).
# Дізнатись свій ID можна у @userinfobot.
_admin_id_raw = os.getenv("ADMIN_USER_ID", "")
ADMIN_USER_ID: int | None = int(_admin_id_raw) if _admin_id_raw.strip().isdigit() else None

# Часовий пояс
TIMEZONE = os.getenv("TIMEZONE", "Europe/Kyiv")

# Мінімальний інтервал між заняттями (хвилини) — зберігається в БД,
# це значення використовується лише як fallback при першому запуску
SLOT_DURATION_MINUTES = 90

# ── Стани розмов ──────────────────────────────────────────────────────────────
BOOKING_STATES = {
    "CHOOSE_DATE":   10,
    "CHOOSE_TIME":   11,
    "CONFIRM":       12,
    "CANCEL_SELECT": 13,
}

ADMIN_STATES = {
    "MENU":         20,
    "ADD_DAY":      21,
    "DEL_DAY":      22,
    "SET_INTERVAL": 23,
}