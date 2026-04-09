import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")

_admin_id_raw = os.getenv("ADMIN_USER_ID", "")
ADMIN_USER_ID: int | None = int(_admin_id_raw) if _admin_id_raw.strip().isdigit() else None

TIMEZONE = os.getenv("TIMEZONE", "Europe/Kyiv")

SLOT_DURATION_MINUTES = 90

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