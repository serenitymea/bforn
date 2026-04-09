from datetime import datetime, date as Date
from typing import Optional

import psycopg2

from db.pool import execute, get_raw_conn, release_conn

# Scheme initialization

def create_tables() -> None:
    """Створює таблиці якщо їх немає. Ідемпотентно."""
    conn = get_raw_conn()
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
                    value TEXT NOT NULL
                )
            """)
            cur.execute(
                "INSERT INTO settings(key, value) VALUES ('slot_interval', '90') ON CONFLICT DO NOTHING"
            )
            cur.execute(
                "INSERT INTO settings(key, value) VALUES ('admin_chat_id', '') ON CONFLICT DO NOTHING"
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_conn(conn)


# Users

def upsert_user(user_id: int, username: str, full_name: str) -> None:
    execute(
        """
        INSERT INTO users(id, username, full_name) VALUES (%s, %s, %s)
        ON CONFLICT (id) DO UPDATE
            SET username  = EXCLUDED.username,
                full_name = EXCLUDED.full_name
        """,
        (user_id, username, full_name),
        write=True,
    )


# Settings

def get_setting(key: str, default: str = "") -> str:
    row = execute("SELECT value FROM settings WHERE key = %s", (key,), fetch="one")
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    execute("UPDATE settings SET value = %s WHERE key = %s", (value, key), write=True)


# Working days

def upsert_working_day(date: str, start_time: str, end_time: str) -> None:
    execute(
        """
        INSERT INTO working_days(date, start_time, end_time) VALUES (%s, %s, %s)
        ON CONFLICT (date) DO UPDATE
            SET start_time = EXCLUDED.start_time,
                end_time   = EXCLUDED.end_time
        """,
        (date, start_time, end_time),
        write=True,
    )


def delete_working_day(date: str) -> None:
    """delete day and bookings"""
    conn = get_raw_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM bookings     WHERE date = %s", (date,))
            cur.execute("DELETE FROM working_days WHERE date = %s", (date,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        release_conn(conn)


def get_working_days(include_past: bool = False) -> list[str]:
    """return date list 'YYYY-MM-DD'."""
    today = datetime.now().strftime("%Y-%m-%d")
    if include_past:
        rows = execute("SELECT date::text FROM working_days ORDER BY date", fetch="all")
    else:
        rows = execute(
            "SELECT date::text FROM working_days WHERE date >= %s ORDER BY date",
            (today,), fetch="all",
        )
    return [r["date"] for r in (rows or [])]


def get_working_day(date: str) -> Optional[dict]:
    row = execute(
        """
        SELECT date::text,
               to_char(start_time, 'HH24:MI') AS start_time,
               to_char(end_time,   'HH24:MI') AS end_time
        FROM working_days WHERE date = %s
        """,
        (date,), fetch="one",
    )
    return dict(row) if row else None


# bookings

def get_booked_times(date: str) -> set[str]:
    rows = execute(
        "SELECT to_char(time, 'HH24:MI') AS time FROM bookings WHERE date = %s",
        (date,), fetch="all",
    )
    return {r["time"] for r in (rows or [])}


def create_booking(user_id: int, date: str, time: str) -> bool:
    """returns True if success"""
    conn = get_raw_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM bookings WHERE date = %s AND time = %s FOR UPDATE",
                (date, time),
            )
            if cur.fetchone():
                conn.rollback()
                return False
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
        release_conn(conn)


def cancel_booking(booking_id: int, user_id: int) -> None:
    execute(
        "DELETE FROM bookings WHERE id = %s AND user_id = %s",
        (booking_id, user_id), write=True,
    )


def admin_cancel_booking(booking_id: int) -> None:
    execute("DELETE FROM bookings WHERE id = %s", (booking_id,), write=True)


def get_user_bookings(user_id: int) -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    rows = execute(
        """
        SELECT id, date::text, to_char(time, 'HH24:MI') AS time
        FROM bookings
        WHERE user_id = %s AND date >= %s
        ORDER BY date, time
        """,
        (user_id, today), fetch="all",
    )
    return [dict(r) for r in (rows or [])]


def get_all_upcoming_bookings() -> list[dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    rows = execute(
        """
        SELECT b.id, b.date::text, to_char(b.time, 'HH24:MI') AS time,
               u.full_name, u.username
        FROM bookings b JOIN users u ON b.user_id = u.id
        WHERE b.date >= %s
        ORDER BY b.date, b.time
        """,
        (today,), fetch="all",
    )
    return [dict(r) for r in (rows or [])]


# Cleaning

def purge_past_data(before_date: str) -> tuple[int, int]:

    conn = get_raw_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM bookings     WHERE date < %s", (before_date,))
            deleted_bookings = cur.rowcount
            cur.execute("DELETE FROM working_days WHERE date < %s", (before_date,))
            deleted_days = cur.rowcount
        conn.commit()
        return deleted_bookings, deleted_days
    except Exception:
        conn.rollback()
        raise
    finally:
        release_conn(conn)