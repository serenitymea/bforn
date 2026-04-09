from calendar import monthrange
from datetime import datetime

import pytz
from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup,
)

from config import TIMEZONE

_tz = pytz.timezone(TIMEZONE)

_MONTHS_UA = ["Січень","Лютий","Березень","Квітень","Травень","Червень",
               "Липень","Серпень","Вересень","Жовтень","Листопад","Грудень"]


# Reply keyboards

def main_keyboard(admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton("📅 Записатися на заняття")],
        [KeyboardButton("📋 Мої записи"), KeyboardButton("❌ Скасувати запис")],
    ]
    if admin:
        rows.append([KeyboardButton("⚙️ Адмін панель")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


# Inline keyboards

def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Додати робочий день", callback_data="admin_add_day")],
        [InlineKeyboardButton("🗑 Видалити день",        callback_data="admin_del_day")],
        [InlineKeyboardButton("📋 Всі записи",           callback_data="admin_bookings")],
        [InlineKeyboardButton("⏱ Змінити інтервал",     callback_data="admin_interval")],
    ])


def dates_keyboard(available_days: list[str], from_formatting) -> InlineKeyboardMarkup:
    rows = []
    for day in available_days:
        dt = datetime.strptime(day, "%Y-%m-%d")
        rows.append([InlineKeyboardButton(f"📅 {from_formatting(dt)}", callback_data=f"date_{day}")])
    rows.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)


def slots_keyboard(slots: list[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(f"🕐 {s}", callback_data=f"slot|{s}")] for s in slots]
    rows.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_dates")])
    return InlineKeyboardMarkup(rows)


def confirm_booking_keyboard(date_str: str, time_str: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Підтвердити", callback_data=f"confirm|{date_str}|{time_str}")],
        [InlineKeyboardButton("❌ Скасувати",   callback_data="cancel")],
    ])


def cancel_bookings_keyboard(bookings: list[dict], from_formatting) -> InlineKeyboardMarkup:
    rows = []
    for b in bookings:
        dt = datetime.strptime(b["date"], "%Y-%m-%d")
        label = f"{from_formatting(dt)} о {b['time']}"
        rows.append([InlineKeyboardButton(f"❌ {label}", callback_data=f"cancel_book_{b['id']}")])
    rows.append([InlineKeyboardButton("↩️ Назад", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)


def calendar_keyboard(year: int, month: int, existing_days: set[str]) -> InlineKeyboardMarkup:
    today = datetime.now(_tz).date()
    _, days_in_month = monthrange(year, month)
    first_weekday = datetime(year, month, 1).weekday()

    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year  = year if month < 12 else year + 1

    rows = [
        [
            InlineKeyboardButton("◀️", callback_data=f"cal_prev_{prev_year}_{prev_month:02d}"),
            InlineKeyboardButton(f"📅 {_MONTHS_UA[month - 1]} {year}", callback_data="cal_ignore"),
            InlineKeyboardButton("▶️", callback_data=f"cal_next_{next_year}_{next_month:02d}"),
        ],
        [InlineKeyboardButton(d, callback_data="cal_ignore") for d in ["Пн","Вт","Ср","Чт","Пт","Сб","Нд"]],
    ]

    week = [InlineKeyboardButton(" ", callback_data="cal_ignore")] * first_weekday
    for day in range(1, days_in_month + 1):
        from datetime import date as _Date
        date_obj = _Date(year, month, day)
        date_str = date_obj.strftime("%Y-%m-%d")
        if date_obj < today:
            label, cb = "·", "cal_ignore"
        elif date_str in existing_days:
            label, cb = f"✅{day}", f"cal_day_{date_str}"
        else:
            label, cb = str(day), f"cal_day_{date_str}"
        week.append(InlineKeyboardButton(label, callback_data=cb))
        if len(week) == 7:
            rows.append(week)
            week = []
    if week:
        while len(week) < 7:
            week.append(InlineKeyboardButton(" ", callback_data="cal_ignore"))
        rows.append(week)

    rows.append([InlineKeyboardButton("↩️ Назад до меню", callback_data="admin_back")])
    return InlineKeyboardMarkup(rows)


def time_picker_keyboard(step: str, selected_h: int | None = None) -> InlineKeyboardMarkup:
    rows, pair = [], []
    for h in range(7, 23):
        if step == "end" and selected_h is not None and h <= selected_h:
            btn = InlineKeyboardButton("·", callback_data="cal_ignore")
        else:
            btn = InlineKeyboardButton(f"{h:02d}:00", callback_data=f"time_{step}_{h:02d}")
        pair.append(btn)
        if len(pair) == 4:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("↩️ Назад", callback_data="admin_add_day")])
    return InlineKeyboardMarkup(rows)


def interval_keyboard(current: int) -> InlineKeyboardMarkup:
    presets = [45, 60, 90, 120]
    return InlineKeyboardMarkup([
        [[InlineKeyboardButton(
            f"{'✅ ' if current == m else ''}{m} хв",
            callback_data=f"set_interval_{m}",
        ) for m in presets]],
        [InlineKeyboardButton("✏️ Ввести вручну", callback_data="interval_manual")],
        [InlineKeyboardButton("↩️ Назад",         callback_data="admin_back")],
    ])