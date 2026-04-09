# tg-booking-bot

Telegram bot for scheduling sessions. Admin manages working days, students pick time slots. Past bookings and days are purged automatically every night.

---

## Stack

Python 3.11, python-telegram-bot 21.5, PostgreSQL, APScheduler, psycopg2, pytz, python-dotenv.

---

## Project structure

```
tg-booking-bot/
├── bot.py               Entry point. Wires DB, scheduler, and all handlers.
├── config.py            All settings from env vars. One import = all constants.
│
├── db/
│   ├── pool.py          ThreadedConnectionPool + single execute() wrapper.
│   └── queries.py       Every SQL query lives here. No SQL anywhere else.
│
├── services/
│   ├── booking.py       Slot availability logic, create/cancel booking.
│   ├── schedule.py      Working day CRUD, slot interval, admin chat id.
│   └── cleanup.py       Deletes past bookings and working days atomically.
│
├── handlers/
│   ├── user.py          /start and "My bookings".
│   ├── booking.py       ConversationHandler: date → time → confirm.
│   ├── cancel.py        ConversationHandler: select booking → cancel.
│   └── admin.py         ConversationHandler: full admin panel.
│
└── utils/
    ├── auth.py          is_admin() check.
    ├── formatting.py    format_date_ua(), escape_mdv2(), escape_md().
    └── keyboards.py     Every InlineKeyboard and ReplyKeyboard.
```

### Layer rules

- `db/` — SQL and connection pool only. No business logic.
- `services/` — Business logic only. No SQL, no Telegram API.
- `handlers/` — Telegram I/O only. Calls services, never touches SQL.
- `utils/` — Pure stateless helpers. No side effects.

Each handler file exposes a single `build_handler()` function. `bot.py` just calls them all.

---

## Environment variables

| Variable       | Required | Default     | Description                       |
|----------------|----------|-------------|-----------------------------------|
| BOT_TOKEN      | yes      | —           | Token from @BotFather             |
| ADMIN_USER_ID  | yes      | —           | Telegram numeric ID of the admin  |
| ADMIN_USERNAME | no       | —           | Fallback if ADMIN_USER_ID not set |
| PGHOST         | yes      | —           | PostgreSQL host                   |
| PGPORT         | no       | 5432        | PostgreSQL port                   |
| PGDATABASE     | yes      | —           | Database name                     |
| PGUSER         | yes      | —           | Database user                     |
| PGPASSWORD     | yes      | —           | Database password                 |
| TIMEZONE       | no       | Europe/Kyiv | Timezone for slots and scheduler  |
| CLEANUP_HOUR   | no       | 3           | Hour of nightly cleanup (0–23)    |

---

## Quick start

Docker Compose (recommended):

```bash
cp .env.example .env      # fill in BOT_TOKEN, ADMIN_USER_ID, POSTGRES_PASSWORD
docker compose up -d
```

Local:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

---

## Nightly cleanup

Every day at `CLEANUP_HOUR:00` (in the configured TIMEZONE), `services/cleanup.py` runs a single atomic transaction that deletes all `bookings` and `working_days` with a date before today. If it fails, it logs the error and retries at the next scheduled run. Nothing else is affected.

---

## How to extend

Add a new user flow — create a file in `handlers/`, write `build_handler()`, register it in `bot.py`.

Add a new query — add a function to `db/queries.py`, call it from a service.

Add business logic — add a function to an existing service or create a new file in `services/`.

Add a setting — add a row to the `settings` table in `db/queries.py:create_tables()`, expose it via `services/schedule.py`.

---

## Database schema

```
users         id, username, full_name
working_days  id, date (unique), start_time, end_time
bookings      id, user_id → users, date, time (unique per date+time)
settings      key, value  (slot_interval, admin_chat_id)
```

Tables are created automatically on first run via `create_tables()`. Schema changes should be applied as manual migrations.