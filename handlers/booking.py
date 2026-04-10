from datetime import datetime

import pytz

from config import TIMEZONE
from db import queries

_tz = pytz.timezone(TIMEZONE)


def get_free_slots(date: str, _user_id: int) -> list[str]:
    """
    all free time slots
    """
    day = queries.get_working_day(date)
    if not day:
        return []

    interval = int(queries.get_setting("slot_interval", "90"))
    start_h, start_m = map(int, day["start_time"].split(":"))
    end_h,   end_m   = map(int, day["end_time"].split(":"))
    start_min = start_h * 60 + start_m
    end_min   = end_h   * 60 + end_m

    all_slots: list[str] = []
    cur = start_min
    while cur + interval <= end_min:
        all_slots.append(f"{cur // 60:02d}:{cur % 60:02d}")
        cur += interval

    booked = queries.get_booked_times(date)
    now = datetime.now(_tz)
    today_str = now.strftime("%Y-%m-%d")

    free: list[str] = []
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


def book(user_id: int, date: str, time: str) -> bool:
    """returns True"""
    return queries.create_booking(user_id, date, time)


def cancel(booking_id: int, user_id: int) -> None:
    queries.cancel_booking(booking_id, user_id)