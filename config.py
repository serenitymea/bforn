from dotenv import load_dotenv
import os

load_dotenv()

# ── Налаштування ──────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Юзернейм вчителя (без @) — залишено для сумісності, але авторизація йде по ID
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "teacher_username")

# ID адміна в Telegram (надійніший спосіб авторизації, ніж username).
# Дізнатись свій ID можна у @userinfobot.
# Якщо не вказано — авторизація по ADMIN_USERNAME (менш надійно).
_admin_id_raw = os.getenv("ADMIN_USER_ID", "")
ADMIN_USER_ID: int | None = int(_admin_id_raw) if _admin_id_raw.strip().isdigit() else None

# Часовий пояс України
TIMEZONE = "Europe/Kyiv"

# Мінімальний інтервал між заняттями (хвилини). Можна змінити через адмін-панель
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