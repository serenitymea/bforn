import sqlite3
import threading
import os
from datetime import datetime
from typing import List, Dict, Optional

_data_dir = os.environ.get("DATA_DIR", os.path.dirname(__file__))
os.makedirs(_data_dir, exist_ok=True)
DB_PATH = os.path.join(_data_dir, "bot_data.db")
DEFAULT_INTERVAL = 90  # хвилин


class Database:
    def __init__(self):
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # WAL-режим: читачі не блокують записувача і навпаки
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_tables()

    def _execute(self, sql: str, params: tuple = (), *, write: bool = False):
        """Виконати SQL. write=True — під локом для безпечної конкурентності."""
        if write:
            with self._lock:
                cur = self.conn.execute(sql, params)
                self.conn.commit()
                return cur
        return self.conn.execute(sql, params)

    def _init_tables(self):
        with self._lock:
            c = self.conn.cursor()

            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id        INTEGER PRIMARY KEY,
                    username  TEXT,
                    full_name TEXT
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS working_days (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    date       TEXT UNIQUE NOT NULL,
                    start_time TEXT NOT NULL,
                    end_time   TEXT NOT NULL
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id   INTEGER NOT NULL,
                    date      TEXT NOT NULL,
                    time      TEXT NOT NULL,
                    UNIQUE(date, time)
                )
            """)

            c.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # Defaults
            c.execute("INSERT OR IGNORE INTO settings VALUES ('slot_interval', ?)", (str(DEFAULT_INTERVAL),))
            c.execute("INSERT OR IGNORE INTO settings VALUES ('admin_chat_id', '')")
            self.conn.commit()

    # ── Users ──────────────────────────────────────────────────────────────────

    def ensure_user(self, user_id: int, username: str, full_name: str):
        self._execute(
            "INSERT OR REPLACE INTO users(id, username, full_name) VALUES (?,?,?)",
            (user_id, username, full_name),
            write=True,
        )

    # ── Settings ───────────────────────────────────────────────────────────────

    def get_slot_interval(self) -> int:
        row = self._execute("SELECT value FROM settings WHERE key='slot_interval'").fetchone()
        return int(row["value"]) if row else DEFAULT_INTERVAL

    def set_slot_interval(self, minutes: int):
        self._execute(
            "UPDATE settings SET value=? WHERE key='slot_interval'",
            (str(minutes),),
            write=True,
        )

    def get_admin_chat_id(self) -> Optional[int]:
        row = self._execute("SELECT value FROM settings WHERE key='admin_chat_id'").fetchone()
        v = row["value"] if row else ""
        return int(v) if v else None

    def set_admin_chat_id(self, chat_id: int):
        self._execute(
            "UPDATE settings SET value=? WHERE key='admin_chat_id'",
            (str(chat_id),),
            write=True,
        )

    # ── Working days ───────────────────────────────────────────────────────────

    def add_working_day(self, date: str, start_time: str, end_time: str):
        self._execute(
            "INSERT OR REPLACE INTO working_days(date, start_time, end_time) VALUES (?,?,?)",
            (date, start_time, end_time),
            write=True,
        )

    def delete_working_day(self, date: str):
        with self._lock:
            self.conn.execute("DELETE FROM working_days WHERE date=?", (date,))
            self.conn.execute("DELETE FROM bookings WHERE date=?", (date,))
            self.conn.commit()

    def get_available_days(self, include_past: bool = False) -> List[str]:
        today = datetime.now().strftime("%Y-%m-%d")
        if include_past:
            rows = self._execute(
                "SELECT date FROM working_days ORDER BY date"
            ).fetchall()
        else:
            rows = self._execute(
                "SELECT date FROM working_days WHERE date >= ? ORDER BY date",
                (today,),
            ).fetchall()
        return [r["date"] for r in rows]

    def get_working_day(self, date: str) -> Optional[Dict]:
        row = self._execute(
            "SELECT * FROM working_days WHERE date=?", (date,)
        ).fetchone()
        return dict(row) if row else None

    # ── Slots ──────────────────────────────────────────────────────────────────

    def get_free_slots(self, date: str, user_id: int) -> List[str]:
        """Return list of free time strings 'HH:MM' for a given date."""
        day = self.get_working_day(date)
        if not day:
            return []

        interval = self.get_slot_interval()

        start_h, start_m = map(int, day["start_time"].split(":"))
        end_h, end_m = map(int, day["end_time"].split(":"))
        start_minutes = start_h * 60 + start_m
        end_minutes = end_h * 60 + end_m

        all_slots = []
        cur = start_minutes
        while cur + interval <= end_minutes:
            slot_time = f"{cur // 60:02d}:{cur % 60:02d}"
            all_slots.append(slot_time)
            cur += interval

        booked_rows = self._execute(
            "SELECT time FROM bookings WHERE date=?", (date,)
        ).fetchall()
        booked = {r["time"] for r in booked_rows}

        today_str = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now()
        free = []
        for slot in all_slots:
            if slot in booked:
                continue
            if date == today_str:
                sh, sm = map(int, slot.split(":"))
                slot_dt = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
                if slot_dt <= now:
                    continue
            free.append(slot)

        return free

    # ── Bookings ───────────────────────────────────────────────────────────────

    def create_booking(self, user_id: int, date: str, time: str) -> bool:
        try:
            with self._lock:
                self.conn.execute(
                    "INSERT INTO bookings(user_id, date, time) VALUES (?,?,?)",
                    (user_id, date, time),
                )
                self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def cancel_booking(self, booking_id: int, user_id: int):
        self._execute(
            "DELETE FROM bookings WHERE id=? AND user_id=?",
            (booking_id, user_id),
            write=True,
        )

    def get_user_bookings(self, user_id: int) -> List[Dict]:
        today = datetime.now().strftime("%Y-%m-%d")
        rows = self._execute(
            "SELECT * FROM bookings WHERE user_id=? AND date >= ? ORDER BY date, time",
            (user_id, today),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_upcoming_bookings(self) -> List[Dict]:
        today = datetime.now().strftime("%Y-%m-%d")
        rows = self._execute(
            """SELECT b.id, b.date, b.time, u.full_name, u.username
               FROM bookings b
               JOIN users u ON b.user_id = u.id
               WHERE b.date >= ?
               ORDER BY b.date, b.time""",
            (today,),
        ).fetchall()
        return [dict(r) for r in rows]