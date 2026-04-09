import os
import threading
from datetime import datetime
from typing import List, Dict, Optional

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

DEFAULT_INTERVAL = 90  # хвилин

# ── DSN ───────────────────────────────────────────────────────────────────────
# Підтримує або DATABASE_URL, або окремі змінні оточення.
_DATABASE_URL = os.environ.get("DATABASE_URL")

if not _DATABASE_URL:
    _host = os.environ.get("POSTGRES_HOST", "db")
    _port = os.environ.get("POSTGRES_PORT", "5432")
    _db   = os.environ.get("POSTGRES_DB",   "botdb")
    _user = os.environ.get("POSTGRES_USER", "botuser")
    _pwd  = os.environ.get("POSTGRES_PASSWORD", "")
    _DATABASE_URL = f"postgresql://{_user}:{_pwd}@{_host}:{_port}/{_db}"

if _DATABASE_URL.startswith("postgresql://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgresql://", "postgres://", 1)

class Database:
    def __init__(self):
        self._lock = threading.Lock()
        # Пул: мін. 1, макс. 10 з'єднань
        self._pool = ThreadedConnectionPool(1, 10, dsn=_DATABASE_URL)
        self._init_tables()

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _conn(self):
        """Взяти з'єднання з пулу."""
        return self._pool.getconn()

    def _put(self, conn):
        """Повернути з'єднання до пулу."""
        self._pool.putconn(conn)

    def _execute(self, sql: str, params: tuple = (), *, fetch: str = "none",
                 write: bool = False):
        """
        Виконати SQL і (опційно) повернути результат.

        fetch:
          "none"  — нічого не повертати
          "one"   — fetchone() → dict | None
          "all"   — fetchall() → list[dict]
        """
        conn = self._conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                if write:
                    conn.commit()
                if fetch == "one":
                    return cur.fetchone()
                if fetch == "all":
                    return cur.fetchall()
                return None
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put(conn)

    def _init_tables(self):
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id        BIGINT PRIMARY KEY,
                        username  TEXT,
                        full_name TEXT
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS working_days (
                        id         SERIAL PRIMARY KEY,
                        date       DATE UNIQUE NOT NULL,
                        start_time TIME NOT NULL,
                        end_time   TIME NOT NULL
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS bookings (
                        id        SERIAL PRIMARY KEY,
                        user_id   BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        date      DATE NOT NULL,
                        time      TIME NOT NULL,
                        UNIQUE(date, time)
                    )
                """)

                cur.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        key   TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)

                # Defaults
                cur.execute(
                    "INSERT INTO settings(key, value) VALUES ('slot_interval', %s) "
                    "ON CONFLICT (key) DO NOTHING",
                    (str(DEFAULT_INTERVAL),),
                )
                cur.execute(
                    "INSERT INTO settings(key, value) VALUES ('admin_chat_id', '') "
                    "ON CONFLICT (key) DO NOTHING"
                )
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put(conn)

    # ── Users ──────────────────────────────────────────────────────────────────

    def ensure_user(self, user_id: int, username: str, full_name: str):
        """
        Upsert користувача.
        Використовуємо ON CONFLICT … DO UPDATE, щоб не видаляти рядок і не
        порушувати зовнішні ключі (замість INSERT OR REPLACE у SQLite).
        """
        self._execute(
            """
            INSERT INTO users(id, username, full_name) VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE
                SET username  = EXCLUDED.username,
                    full_name = EXCLUDED.full_name
            """,
            (user_id, username, full_name),
            write=True,
        )

    # ── Settings ───────────────────────────────────────────────────────────────

    def get_slot_interval(self) -> int:
        row = self._execute(
            "SELECT value FROM settings WHERE key = 'slot_interval'",
            fetch="one",
        )
        return int(row["value"]) if row else DEFAULT_INTERVAL

    def set_slot_interval(self, minutes: int):
        self._execute(
            "UPDATE settings SET value = %s WHERE key = 'slot_interval'",
            (str(minutes),),
            write=True,
        )

    def get_admin_chat_id(self) -> Optional[int]:
        row = self._execute(
            "SELECT value FROM settings WHERE key = 'admin_chat_id'",
            fetch="one",
        )
        v = row["value"] if row else ""
        return int(v) if v else None

    def set_admin_chat_id(self, chat_id: int):
        self._execute(
            "UPDATE settings SET value = %s WHERE key = 'admin_chat_id'",
            (str(chat_id),),
            write=True,
        )

    # ── Working days ───────────────────────────────────────────────────────────

    def add_working_day(self, date: str, start_time: str, end_time: str):
        self._execute(
            """
            INSERT INTO working_days(date, start_time, end_time)
            VALUES (%s, %s, %s)
            ON CONFLICT (date) DO UPDATE
                SET start_time = EXCLUDED.start_time,
                    end_time   = EXCLUDED.end_time
            """,
            (date, start_time, end_time),
            write=True,
        )

    def delete_working_day(self, date: str):
        """Видалити день і всі записи на нього (каскадно через дату)."""
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                # bookings не має FK на working_days → видаляємо вручну
                cur.execute("DELETE FROM bookings WHERE date = %s", (date,))
                cur.execute("DELETE FROM working_days WHERE date = %s", (date,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put(conn)

    def get_available_days(self, include_past: bool = False) -> List[str]:
        today = datetime.now().strftime("%Y-%m-%d")
        if include_past:
            rows = self._execute(
                "SELECT date::text FROM working_days ORDER BY date",
                fetch="all",
            )
        else:
            rows = self._execute(
                "SELECT date::text FROM working_days WHERE date >= %s ORDER BY date",
                (today,),
                fetch="all",
            )
        return [r["date"] for r in (rows or [])]

    def get_working_day(self, date: str) -> Optional[Dict]:
        row = self._execute(
            """
            SELECT date::text,
                   to_char(start_time, 'HH24:MI') AS start_time,
                   to_char(end_time,   'HH24:MI') AS end_time
            FROM working_days
            WHERE date = %s
            """,
            (date,),
            fetch="one",
        )
        return dict(row) if row else None

    # ── Slots ──────────────────────────────────────────────────────────────────

    def get_free_slots(self, date: str, user_id: int) -> List[str]:
        """
        Повертає список вільних слотів 'HH:MM' для дати.

        Виправлення відносно оригіналу:
        - Слоти, заброньовані тим самим користувачем, теж вважаються зайнятими
          (користувач не може записатися двічі на один час).
        - Минулі слоти поточного дня фільтруються коректно.
        """
        day = self.get_working_day(date)
        if not day:
            return []

        interval = self.get_slot_interval()

        start_h, start_m = map(int, day["start_time"].split(":"))
        end_h,   end_m   = map(int, day["end_time"].split(":"))
        start_minutes = start_h * 60 + start_m
        end_minutes   = end_h   * 60 + end_m

        all_slots: List[str] = []
        cur = start_minutes
        while cur + interval <= end_minutes:
            all_slots.append(f"{cur // 60:02d}:{cur % 60:02d}")
            cur += interval

        # Всі заброньовані слоти на цю дату (будь-яким користувачем)
        rows = self._execute(
            "SELECT to_char(time, 'HH24:MI') AS time FROM bookings WHERE date = %s",
            (date,),
            fetch="all",
        )
        booked = {r["time"] for r in (rows or [])}

        today_str = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now()
        free = []
        for slot in all_slots:
            if slot in booked:
                continue
            # Фільтруємо вже минулі слоти сьогоднішнього дня
            if date == today_str:
                sh, sm = map(int, slot.split(":"))
                slot_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
                if slot_dt <= now:
                    continue
            free.append(slot)

        return free

    # ── Bookings ───────────────────────────────────────────────────────────────

    def create_booking(self, user_id: int, date: str, time: str) -> bool:
        """
        Створити запис. Повертає True при успіху, False якщо слот вже зайнятий.

        Виправлення: перевірка унікальності відбувається всередині однієї
        транзакції з блокуванням рядка (SELECT … FOR UPDATE), що усуває
        race-condition при одночасному запису.
        """
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                # Блокуємо потенційний конфліктний рядок, щоб два потоки не
                # вставили однаковий слот одночасно
                cur.execute(
                    "SELECT id FROM bookings WHERE date = %s AND time = %s FOR UPDATE",
                    (date, time),
                )
                if cur.fetchone():
                    conn.rollback()
                    return False  # слот вже зайнятий

                cur.execute(
                    "INSERT INTO bookings(user_id, date, time) VALUES (%s, %s, %s)",
                    (user_id, date, time),
                )
            conn.commit()
            return True
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            return False
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put(conn)

    def cancel_booking(self, booking_id: int, user_id: int):
        self._execute(
            "DELETE FROM bookings WHERE id = %s AND user_id = %s",
            (booking_id, user_id),
            write=True,
        )

    def get_user_bookings(self, user_id: int) -> List[Dict]:
        today = datetime.now().strftime("%Y-%m-%d")
        rows = self._execute(
            """
            SELECT id,
                   date::text,
                   to_char(time, 'HH24:MI') AS time
            FROM bookings
            WHERE user_id = %s AND date >= %s
            ORDER BY date, time
            """,
            (user_id, today),
            fetch="all",
        )
        return [dict(r) for r in (rows or [])]

    def get_all_upcoming_bookings(self) -> List[Dict]:
        today = datetime.now().strftime("%Y-%m-%d")
        rows = self._execute(
            """
            SELECT b.id,
                   b.date::text,
                   to_char(b.time, 'HH24:MI') AS time,
                   u.full_name,
                   u.username
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            WHERE b.date >= %s
            ORDER BY b.date, b.time
            """,
            (today,),
            fetch="all",
        )
        return [dict(r) for r in (rows or [])]