import os

# Telegram

BOT_TOKEN: str = os.environ["BOT_TOKEN"]  # KeyError = crash

ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "")

_admin_id_raw = os.getenv("ADMIN_USER_ID", "")
ADMIN_USER_ID: int | None = int(_admin_id_raw) if _admin_id_raw.strip().isdigit() else None

# time zone

TIMEZONE: str = os.getenv("TIMEZONE", "Europe/Kyiv")

# biznes rules

DEFAULT_SLOT_MINUTES: int = 90

# plan cleanup time

CLEANUP_HOUR: int = int(os.getenv("CLEANUP_HOUR", "3"))

# states ConversationHandler

class BookingState:
    CHOOSE_DATE   = 10
    CHOOSE_TIME   = 11
    CONFIRM       = 12
    CANCEL_SELECT = 13

class AdminState:
    MENU         = 20
    ADD_DAY      = 21
    DEL_DAY      = 22
    SET_INTERVAL = 23