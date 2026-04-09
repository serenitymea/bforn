import logging
import os
from datetime import datetime
import pytz

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

from database import Database
from config import (
    BOT_TOKEN, ADMIN_USERNAME, ADMIN_USER_ID, TIMEZONE, SLOT_DURATION_MINUTES,
    ADMIN_STATES, BOOKING_STATES
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

tz = pytz.timezone(TIMEZONE)

db: Database


def escape_md(text: str) -> str:
    for ch in r"\_*`[":
        text = text.replace(ch, f"\\{ch}")
    return text


def escape_mdv2(text: str) -> str:
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def is_admin(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    if ADMIN_USER_ID is not None:
        return user.id == ADMIN_USER_ID
    return bool(user.username) and user.username.lower() == ADMIN_USERNAME.lower().lstrip("@")


def make_main_keyboard(admin: bool = False) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton("📅 Записатися на заняття")],
        [KeyboardButton("📋 Мої записи"), KeyboardButton("❌ Скасувати запис")],
    ]
    if admin:
        buttons.append([KeyboardButton("⚙️ Адмін панель")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def format_date_ua(dt: datetime) -> str:
    months = [
        "січня", "лютого", "березня", "квітня", "травня", "червня",
        "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
    ]
    weekdays = ["понеділок", "вівторок", "середа", "четвер", "п'ятниця", "субота", "неділя"]
    return f"{dt.day} {months[dt.month - 1]} ({weekdays[dt.weekday()]})"


def make_admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Додати робочий день", callback_data="admin_add_day")],
        [InlineKeyboardButton("🗑 Видалити день",        callback_data="admin_del_day")],
        [InlineKeyboardButton("📋 Всі записи",           callback_data="admin_bookings")],
        [InlineKeyboardButton("⏱ Змінити інтервал",     callback_data="admin_interval")],
    ])


def build_calendar(year: int, month: int, existing_days: set) -> InlineKeyboardMarkup:
    from calendar import monthrange

    today = datetime.now(tz).date()
    _, days_in_month = monthrange(year, month)
    first_weekday = datetime(year, month, 1).weekday()

    months_ua = [
        "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
        "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень",
    ]
    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year  = year if month < 12 else year + 1

    rows = []
    rows.append([
        InlineKeyboardButton("◀️", callback_data=f"cal_prev_{prev_year}_{prev_month:02d}"),
        InlineKeyboardButton(f"📅 {months_ua[month - 1]} {year}", callback_data="cal_ignore"),
        InlineKeyboardButton("▶️", callback_data=f"cal_next_{next_year}_{next_month:02d}"),
    ])
    rows.append([
        InlineKeyboardButton(d, callback_data="cal_ignore")
        for d in ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
    ])

    week = [InlineKeyboardButton(" ", callback_data="cal_ignore")] * first_weekday
    for day in range(1, days_in_month + 1):
        date_obj = datetime(year, month, day).date()
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


def build_time_keyboard(step: str, selected_h: int | None = None) -> InlineKeyboardMarkup:
    rows = []
    pair = []
    for h in range(7, 23):
        if step == "end" and selected_h is not None and h <= selected_h:
            btn = InlineKeyboardButton("·", callback_data="cal_ignore")
        else:
            label = f"{h:02d}:00"
            btn = InlineKeyboardButton(label, callback_data=f"time_{step}_{h:02d}")
        pair.append(btn)
        if len(pair) == 4:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("↩️ Назад", callback_data="admin_add_day")])
    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.ensure_user(user.id, user.username or "", user.full_name)
    admin = is_admin(update)
    name = escape_md(user.first_name or "учню")
    text = (
        f"👋 Вітаю, {name}!\n\n"
        "Це бот для запису на заняття. Тут ти можеш:\n"
        "• Обрати зручний час і записатися\n"
        "• Переглянути свої записи\n"
        "• Скасувати запис\n\n"
        "Обери дію нижче 👇"
    )
    if admin:
        text += "\n\n🔑 Ти маєш доступ до адмін\\-панелі."
    await update.message.reply_text(text, reply_markup=make_main_keyboard(admin))


async def _show_dates(query) -> int:
    available_days = db.get_available_days()
    if not available_days:
        await query.edit_message_text(
            "😔 На жаль, зараз немає доступних дат для запису.\n"
            "Спробуй пізніше або зв'яжись з учителем."
        )
        return ConversationHandler.END

    buttons = []
    for day in available_days:
        dt = datetime.strptime(day, "%Y-%m-%d")
        buttons.append([InlineKeyboardButton(f"📅 {format_date_ua(dt)}", callback_data=f"date_{day}")])
    buttons.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel")])
    await query.edit_message_text(
        "📅 *Обери дату заняття:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return BOOKING_STATES["CHOOSE_DATE"]


async def book_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.ensure_user(user.id, user.username or "", user.full_name)

    available_days = db.get_available_days()
    if not available_days:
        await update.message.reply_text(
            "😔 На жаль, зараз немає доступних дат для запису.\n"
            "Спробуй пізніше або зв'яжись з учителем."
        )
        return ConversationHandler.END

    buttons = []
    for day in available_days:
        dt = datetime.strptime(day, "%Y-%m-%d")
        buttons.append([InlineKeyboardButton(f"📅 {format_date_ua(dt)}", callback_data=f"date_{day}")])
    buttons.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel")])

    await update.message.reply_text(
        "📅 *Обери дату заняття:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return BOOKING_STATES["CHOOSE_DATE"]


async def book_choose_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("❌ Запис скасовано.")
        return ConversationHandler.END

    date_str = query.data.replace("date_", "", 1)
    context.user_data["booking_date"] = date_str

    slots = db.get_free_slots(date_str, update.effective_user.id)
    if not slots:
        await query.edit_message_text("😔 На цю дату вільних місць немає. Обери іншу дату.")
        return await _show_dates(query)

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    buttons = []
    for slot in slots:
        buttons.append([InlineKeyboardButton(f"🕐 {slot}", callback_data=f"slot|{slot}")])
    buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_dates")])

    await query.edit_message_text(
        f"📅 *{format_date_ua(dt)}*\n\nОбери зручний час:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return BOOKING_STATES["CHOOSE_TIME"]


async def book_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_dates":
        return await _show_dates(query)

    time_str = query.data.split("|", 1)[1]
    date_str = context.user_data.get("booking_date")
    user = update.effective_user

    slots = db.get_free_slots(date_str, user.id)
    if time_str not in slots:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        buttons = []
        for slot in slots:
            buttons.append([InlineKeyboardButton(f"🕐 {slot}", callback_data=f"slot|{slot}")])
        buttons.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_dates")])
        await query.edit_message_text(
            f"⚠️ Цей час вже зайнятий.\n\n📅 *{format_date_ua(dt)}*\n\nОбери зручний час:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return BOOKING_STATES["CHOOSE_TIME"]

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    buttons = [
        [InlineKeyboardButton("✅ Підтвердити", callback_data=f"confirm|{date_str}|{time_str}")],
        [InlineKeyboardButton("❌ Скасувати",   callback_data="cancel")],
    ]
    await query.edit_message_text(
        f"📋 *Підтвердження запису*\n\n"
        f"📅 Дата: {format_date_ua(dt)}\n"
        f"🕐 Час: {time_str}\n\n"
        f"Підтверджуєш запис?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return BOOKING_STATES["CONFIRM"]


async def book_finalize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("❌ Запис скасовано.")
        return ConversationHandler.END

    _, date_str, time_str = query.data.split("|", 2)
    user = update.effective_user

    success = db.create_booking(user.id, date_str, time_str)
    if success:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        await query.edit_message_text(
            f"✅ *Запис підтверджено!*\n\n"
            f"📅 {format_date_ua(dt)}\n"
            f"🕐 {time_str}\n\n"
            f"Чекаємо тебе! Якщо плани зміняться — скасуй запис заздалегідь.",
            parse_mode="Markdown",
        )
        await notify_admin_new_booking(context, user, date_str, time_str)
    else:
        await query.edit_message_text("⚠️ Не вдалося записатися. Можливо, місце вже зайняте. Спробуй ще раз.")

    return ConversationHandler.END


async def notify_admin_new_booking(context, user, date_str: str, time_str: str):
    try:
        admin_id = db.get_admin_chat_id() or ADMIN_USER_ID
        if not admin_id:
            return
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        name = escape_md(user.full_name or user.first_name or "Невідомий")
        username = f"@{escape_md(user.username)}" if user.username else "без юзернейму"
        await context.bot.send_message(
            admin_id,
            f"📬 *Новий запис!*\n\n"
            f"👤 {name} ({username})\n"
            f"📅 {format_date_ua(dt)}\n"
            f"🕐 {time_str}",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")


async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update):
        bookings = db.get_all_upcoming_bookings()
        if not bookings:
            await update.message.reply_text("📋 Немає активних записів учнів.")
            return
        text = "📋 *Всі записи учнів:*\n\n"
        for b in bookings:
            dt = datetime.strptime(b["date"], "%Y-%m-%d")
            name = escape_md(b.get("full_name") or b.get("username") or "Невідомий")
            text += f"• {format_date_ua(dt)} о {b['time']} — {name}\n"
    else:
        user_id = update.effective_user.id
        bookings = db.get_user_bookings(user_id)
        if not bookings:
            await update.message.reply_text(
                "📋 У тебе немає активних записів.\n"
                "Натисни «📅 Записатися на заняття», щоб обрати час."
            )
            return
        text = "📋 *Твої записи:*\n\n"
        for b in bookings:
            dt = datetime.strptime(b["date"], "%Y-%m-%d")
            text += f"• {format_date_ua(dt)} о {b['time']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def cancel_booking_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bookings = db.get_user_bookings(user_id)
    if not bookings:
        await update.message.reply_text("📋 У тебе немає активних записів для скасування.")
        return ConversationHandler.END

    buttons = []
    for b in bookings:
        dt = datetime.strptime(b["date"], "%Y-%m-%d")
        label = f"{format_date_ua(dt)} о {b['time']}"
        buttons.append([InlineKeyboardButton(f"❌ {label}", callback_data=f"cancel_book_{b['id']}")])
    buttons.append([InlineKeyboardButton("↩️ Назад", callback_data="cancel")])

    await update.message.reply_text(
        "Який запис скасувати?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return BOOKING_STATES["CANCEL_SELECT"]


async def cancel_booking_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("↩️ Скасування відмінено.")
        return ConversationHandler.END

    booking_id = int(query.data.replace("cancel_book_", "", 1))
    db.cancel_booking(booking_id, update.effective_user.id)
    await query.edit_message_text("✅ Запис успішно скасовано.")
    return ConversationHandler.END


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("⛔ У тебе немає доступу до цього розділу.")
        return ConversationHandler.END

    db.set_admin_chat_id(update.effective_user.id)

    await update.message.reply_text(
        "⚙️ *Адмін\\-панель*\n\nОбери дію:",
        parse_mode="Markdown",
        reply_markup=make_admin_menu_keyboard(),
    )
    return ADMIN_STATES["MENU"]


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(update):
        await query.answer("⛔ Доступ заборонено", show_alert=True)
        return ADMIN_STATES["MENU"]

    data = query.data

    if data == "cal_ignore":
        return ADMIN_STATES["ADD_DAY"]

    if data == "admin_add_day":
        now = datetime.now(tz)
        existing = set(db.get_available_days(include_past=False))
        context.user_data["cal_year"] = now.year
        context.user_data["cal_month"] = now.month
        await query.edit_message_text(
            "➕ *Додати робочий день*\n\nОбери дату на календарі.\n✅ — день вже додано.",
            parse_mode="Markdown",
            reply_markup=build_calendar(now.year, now.month, existing),
        )
        return ADMIN_STATES["ADD_DAY"]

    if data.startswith("cal_prev_") or data.startswith("cal_next_"):
        parts = data.split("_")
        year, month = int(parts[-2]), int(parts[-1])
        context.user_data["cal_year"] = year
        context.user_data["cal_month"] = month
        existing = set(db.get_available_days(include_past=False))
        await query.edit_message_text(
            "➕ *Додати робочий день*\n\nОбери дату на календарі.\n✅ — день вже додано.",
            parse_mode="Markdown",
            reply_markup=build_calendar(year, month, existing),
        )
        return ADMIN_STATES["ADD_DAY"]

    if data.startswith("cal_day_"):
        date_str = data[len("cal_day_"):]
        context.user_data["new_day_date"] = date_str
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        await query.edit_message_text(
            f"📅 *{format_date_ua(dt)}*\n\n🕐 Обери час *початку* робочого дня:",
            parse_mode="Markdown",
            reply_markup=build_time_keyboard("start"),
        )
        return ADMIN_STATES["ADD_DAY"]

    if data.startswith("time_start_"):
        start_h = int(data[len("time_start_"):])
        context.user_data["new_day_start"] = f"{start_h:02d}:00"
        date_str = context.user_data.get("new_day_date", "")
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        await query.edit_message_text(
            f"📅 *{format_date_ua(dt)}*\n🕐 Початок: *{start_h:02d}:00*\n\n🕕 Обери час *кінця* робочого дня:",
            parse_mode="Markdown",
            reply_markup=build_time_keyboard("end", selected_h=start_h),
        )
        return ADMIN_STATES["ADD_DAY"]

    if data.startswith("time_end_"):
        end_h = int(data[len("time_end_"):])
        end_s = f"{end_h:02d}:00"
        start_s = context.user_data.get("new_day_start", "09:00")
        date_str = context.user_data.get("new_day_date", "")
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        interval = db.get_slot_interval()
        sh = int(start_s.split(":")[0])
        slots_count = (end_h - sh) * 60 // interval

        await query.edit_message_text(
            f"✅ *Підтвердження*\n\n"
            f"📅 {format_date_ua(dt)}\n"
            f"🕐 Початок: *{start_s}*\n"
            f"🕕 Кінець:  *{end_s}*\n"
            f"⏱ Слотів по {interval} хв: *{slots_count}*\n\n"
            f"Зберегти цей день?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Так, зберегти",  callback_data=f"confirm_day|{date_str}|{start_s}|{end_s}")],
                [InlineKeyboardButton("✏️ Змінити час",    callback_data=f"cal_day_{date_str}")],
                [InlineKeyboardButton("↩️ До календаря",  callback_data="admin_add_day")],
            ]),
        )
        return ADMIN_STATES["ADD_DAY"]

    if data.startswith("confirm_day|"):
        _, date_str, start_s, end_s = data.split("|", 3)
        db.add_working_day(date_str, start_s, end_s)
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        interval = db.get_slot_interval()
        sh = int(start_s.split(":")[0])
        eh = int(end_s.split(":")[0])
        slots_count = (eh - sh) * 60 // interval
        await query.edit_message_text(
            f"✅ *Робочий день додано!*\n\n"
            f"📅 {format_date_ua(dt)}\n"
            f"🕐 {start_s} – {end_s}\n"
            f"⏱ Інтервал між заняттями: {interval} хв\n\n"
            f"Обери наступну дію:",
            parse_mode="Markdown",
            reply_markup=make_admin_menu_keyboard(),
        )
        return ADMIN_STATES["MENU"]

    if data == "admin_del_day":
        days = db.get_available_days(include_past=False)
        if not days:
            await query.edit_message_text(
                "😔 Немає доданих днів.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Назад", callback_data="admin_back")]]),
            )
            return ADMIN_STATES["MENU"]
        buttons = []
        for day in days:
            dt = datetime.strptime(day, "%Y-%m-%d")
            buttons.append([InlineKeyboardButton(f"🗑 {format_date_ua(dt)}", callback_data=f"delday_{day}")])
        buttons.append([InlineKeyboardButton("↩️ Назад", callback_data="admin_back")])
        await query.edit_message_text(
            "🗑 *Який день видалити?*\n\n⚠️ Всі записи на цей день також будуть видалені.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return ADMIN_STATES["DEL_DAY"]

    if data.startswith("delday_"):
        day = data[len("delday_"):]
        db.delete_working_day(day)
        dt = datetime.strptime(day, "%Y-%m-%d")
        await query.edit_message_text(
            f"✅ День *{format_date_ua(dt)}* видалено разом із записами.",
            parse_mode="Markdown",
            reply_markup=make_admin_menu_keyboard(),
        )
        return ADMIN_STATES["MENU"]

    if data == "admin_bookings":
        bookings = db.get_all_upcoming_bookings()
        if not bookings:
            await query.edit_message_text(
                "📋 Немає активних записів\\.",
                parse_mode="MarkdownV2",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Назад", callback_data="admin_back")]]),
            )
            return ADMIN_STATES["MENU"]

        text = "📋 *Всі записи:*\\n\\n"
        buttons = []

        for i, b in enumerate(bookings, 1):
            dt = datetime.strptime(b["date"], "%Y-%m-%d")

            name = b.get("full_name") or b.get("username") or "Невідомий"
            username = f" (@{b['username']})" if b.get("username") else ""

            line = f"{i}. {format_date_ua(dt)} о {b['time']} — {name}{username}"
            text += escape_mdv2(line) + "\\n"

            buttons.append([
                InlineKeyboardButton(
                    f"🗑 Видалити запис №{i}",
                    callback_data=f"admin_del_booking_{b['id']}"
                )
            ])

        buttons.append([InlineKeyboardButton("↩️ Назад", callback_data="admin_back")])

        await query.edit_message_text(
            text,
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return ADMIN_STATES["MENU"]

    if data == "admin_interval":
        current = db.get_slot_interval()
        presets = [45, 60, 90, 120]
        buttons = [
            [InlineKeyboardButton(
                f"{'✅ ' if current == m else ''}{m} хв",
                callback_data=f"set_interval_{m}",
            ) for m in presets]
        ]
        buttons.append([InlineKeyboardButton("✏️ Ввести вручну", callback_data="interval_manual")])
        buttons.append([InlineKeyboardButton("↩️ Назад",         callback_data="admin_back")])
        await query.edit_message_text(
            f"⏱ *Інтервал між заняттями*\n\nПоточний: *{current} хв*\n\nОбери новий інтервал:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return ADMIN_STATES["SET_INTERVAL"]

    if data.startswith("set_interval_"):
        minutes = int(data[len("set_interval_"):])
        db.set_slot_interval(minutes)
        await query.edit_message_text(
            f"✅ Інтервал між заняттями: *{minutes} хв*",
            parse_mode="Markdown",
            reply_markup=make_admin_menu_keyboard(),
        )
        return ADMIN_STATES["MENU"]

    if data == "interval_manual":
        await query.edit_message_text("⏱ Введи інтервал у хвилинах (ціле число, не менше 30):")
        return ADMIN_STATES["SET_INTERVAL"]

    if data == "admin_back":
        await query.edit_message_text(
            "⚙️ *Адмін\\-панель*\n\nОбери дію:",
            parse_mode="Markdown",
            reply_markup=make_admin_menu_keyboard(),
        )
        return ADMIN_STATES["MENU"]

    return ADMIN_STATES["MENU"]


async def admin_set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return ConversationHandler.END

    try:
        minutes = int(update.message.text.strip())
        if minutes < 30:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Введи ціле число не менше 30.")
        return ADMIN_STATES["SET_INTERVAL"]

    db.set_slot_interval(minutes)
    await update.message.reply_text(
        f"✅ Інтервал між заняттями встановлено: *{minutes} хв*",
        parse_mode="Markdown",
        reply_markup=make_main_keyboard(admin=True),
    )
    return ConversationHandler.END


async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin = is_admin(update)
    await update.message.reply_text("↩️ Дію скасовано.", reply_markup=make_main_keyboard(admin))
    return ConversationHandler.END


def main():
    global db
    try:
        db = Database()
        logger.info("Database initialized successfully.")
    except Exception as exc:
        logger.critical(f"Failed to initialize DB: {exc}")
        raise SystemExit(1) from exc

    app = Application.builder().token(BOT_TOKEN).build()

    booking_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^📅 Записатися на заняття$"), book_start)
        ],
        states={
            BOOKING_STATES["CHOOSE_DATE"]: [CallbackQueryHandler(book_choose_time)],
            BOOKING_STATES["CHOOSE_TIME"]: [CallbackQueryHandler(book_confirm)],
            BOOKING_STATES["CONFIRM"]:     [CallbackQueryHandler(book_finalize)],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^/cancel$"), cancel_conv),
            MessageHandler(filters.Regex("^📅 Записатися на заняття$"), book_start),
        ],
        per_message=False,
        allow_reentry=True,
    )

    cancel_conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^❌ Скасувати запис$"), cancel_booking_start)
        ],
        states={
            BOOKING_STATES["CANCEL_SELECT"]: [CallbackQueryHandler(cancel_booking_confirm)],
        },
        fallbacks=[MessageHandler(filters.Regex("^/cancel$"), cancel_conv)],
        per_message=False,
        allow_reentry=True,
    )

    admin_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^⚙️ Адмін панель$"), admin_panel)
        ],
        states={
            ADMIN_STATES["MENU"]: [CallbackQueryHandler(admin_callback)],
            ADMIN_STATES["ADD_DAY"]: [CallbackQueryHandler(admin_callback)],
            ADMIN_STATES["DEL_DAY"]: [CallbackQueryHandler(admin_callback)],
            ADMIN_STATES["SET_INTERVAL"]: [
                CallbackQueryHandler(admin_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_set_interval),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^/cancel$"), cancel_conv),
            MessageHandler(filters.Regex("^⚙️ Адмін панель$"), admin_panel),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(booking_conv)
    app.add_handler(cancel_conv_handler)
    app.add_handler(admin_conv)
    app.add_handler(MessageHandler(filters.Regex("^📋 Мої записи$"), my_bookings))

    logger.info("Bot started.")
    app.run_polling()


if __name__ == "__main__":
    main()