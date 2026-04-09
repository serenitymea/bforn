import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler,
    MessageHandler, CallbackQueryHandler, filters,
)

from config import AdminState
from db import queries
from services import schedule as sched
from utils.auth import is_admin
from utils.formatting import format_date_ua, escape_mdv2
from utils.keyboards import (
    admin_menu, calendar_keyboard, time_picker_keyboard,
    interval_keyboard, main_keyboard,
)

logger = logging.getLogger(__name__)

_S = AdminState


# Entry

async def panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update):
        await update.message.reply_text("⛔ У тебе немає доступу до цього розділу.")
        return ConversationHandler.END
    sched.set_admin_chat_id(update.effective_user.id)
    await update.message.reply_text(
        "⚙️ *Адмін\\-панель*\n\nОбери дію:",
        parse_mode="MarkdownV2",
        reply_markup=admin_menu(),
    )
    return _S.MENU


# Callback routing

async def callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not is_admin(update):
        await query.answer("⛔ Доступ заборонено", show_alert=True)
        return _S.MENU

    data = query.data

    # static routs
    if data == "cal_ignore":
        return _S.ADD_DAY

    if data == "admin_back":
        await query.edit_message_text(
            "⚙️ *Адмін\\-панель*\n\nОбери дію:",
            parse_mode="MarkdownV2",
            reply_markup=admin_menu(),
        )
        return _S.MENU

    if data == "admin_add_day":
        return await _show_calendar(query, context)

    if data == "admin_del_day":
        return await _show_del_day(query)

    if data == "admin_bookings":
        return await _show_bookings(query)

    if data == "admin_interval":
        return await _show_interval(query)

    if data == "interval_manual":
        await query.edit_message_text("⏱ Введи інтервал у хвилинах (ціле число, не менше 30):")
        return _S.SET_INTERVAL

    # dynamics routes prefix
    if data.startswith(("cal_prev_", "cal_next_")):
        parts = data.split("_")
        year, month = int(parts[-2]), int(parts[-1])
        context.user_data.update(cal_year=year, cal_month=month)
        existing = set(sched.get_available_days(include_past=False))
        await query.edit_message_text(
            "➕ *Додати робочий день*\n\nОбери дату на календарі\\.\\n✅ — день вже додано\\.",
            parse_mode="MarkdownV2",
            reply_markup=calendar_keyboard(year, month, existing),
        )
        return _S.ADD_DAY

    if data.startswith("cal_day_"):
        return await _pick_start_time(query, context, data.removeprefix("cal_day_"))

    if data.startswith("time_start_"):
        return await _pick_end_time(query, context, int(data.removeprefix("time_start_")))

    if data.startswith("time_end_"):
        return await _preview_new_day(query, context, int(data.removeprefix("time_end_")))

    if data.startswith("confirm_day|"):
        return await _save_new_day(query, data)

    if data.startswith("delday_"):
        return await _delete_day(query, data.removeprefix("delday_"))

    if data.startswith("set_interval_"):
        minutes = int(data.removeprefix("set_interval_"))
        sched.set_slot_interval(minutes)
        await query.edit_message_text(
            f"✅ Інтервал між заняттями: *{minutes} хв*",
            parse_mode="Markdown",
            reply_markup=admin_menu(),
        )
        return _S.MENU

    if data.startswith("admin_del_booking_"):
        booking_id = int(data.removeprefix("admin_del_booking_"))
        queries.admin_cancel_booking(booking_id)
        return await _show_bookings(query)

    return _S.MENU


# hand interval write

async def set_interval_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update):
        return ConversationHandler.END
    try:
        minutes = int(update.message.text.strip())
        if minutes < 30:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Введи ціле число не менше 30.")
        return _S.SET_INTERVAL
    sched.set_slot_interval(minutes)
    await update.message.reply_text(
        f"✅ Інтервал: *{minutes} хв*",
        parse_mode="Markdown",
        reply_markup=main_keyboard(admin=True),
    )
    return ConversationHandler.END


async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("↩️ Дію скасовано.", reply_markup=main_keyboard(admin=True))
    return ConversationHandler.END


# private helpers

async def _show_calendar(query, context) -> int:
    from datetime import datetime as _dt
    import pytz
    from config import TIMEZONE
    now      = _dt.now(pytz.timezone(TIMEZONE))
    existing = set(sched.get_available_days(include_past=False))
    context.user_data.update(cal_year=now.year, cal_month=now.month)
    await query.edit_message_text(
        "➕ *Додати робочий день*\n\nОбери дату на календарі\\.\\n✅ — день вже додано\\.",
        parse_mode="MarkdownV2",
        reply_markup=calendar_keyboard(now.year, now.month, existing),
    )
    return _S.ADD_DAY


async def _show_del_day(query) -> int:
    days = sched.get_available_days(include_past=False)
    if not days:
        await query.edit_message_text(
            "😔 Немає доданих днів.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Назад", callback_data="admin_back")]]),
        )
        return _S.MENU
    rows = [[InlineKeyboardButton(
        f"🗑 {format_date_ua(datetime.strptime(d, '%Y-%m-%d'))}", callback_data=f"delday_{d}"
    )] for d in days]
    rows.append([InlineKeyboardButton("↩️ Назад", callback_data="admin_back")])
    await query.edit_message_text(
        "🗑 *Який день видалити?*\n\n⚠️ Всі записи на цей день також будуть видалені.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    return _S.DEL_DAY


async def _show_bookings(query) -> int:
    bookings = queries.get_all_upcoming_bookings()
    if not bookings:
        await query.edit_message_text(
            "📋 Немає активних записів\\.",
            parse_mode="MarkdownV2",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Назад", callback_data="admin_back")]]),
        )
        return _S.MENU
    lines = ["📋 \\*Всі записи:\\*\n"]
    buttons = []
    for i, b in enumerate(bookings, 1):
        dt       = datetime.strptime(b["date"], "%Y-%m-%d")
        name     = b.get("full_name") or b.get("username") or "Невідомий"
        username = f" (@{b['username']})" if b.get("username") else ""
        lines.append(escape_mdv2(f"{i}. {format_date_ua(dt)} о {b['time']} — {name}{username}"))
        buttons.append([InlineKeyboardButton(f"🗑 Видалити №{i}", callback_data=f"admin_del_booking_{b['id']}")])
    buttons.append([InlineKeyboardButton("↩️ Назад", callback_data="admin_back")])
    await query.edit_message_text(
        "\n".join(lines), parse_mode="MarkdownV2", reply_markup=InlineKeyboardMarkup(buttons)
    )
    return _S.MENU


async def _show_interval(query) -> int:
    current = sched.get_slot_interval()
    await query.edit_message_text(
        f"⏱ *Інтервал між заняттями*\n\nПоточний: *{current} хв*\n\nОбери новий інтервал:",
        parse_mode="Markdown",
        reply_markup=interval_keyboard(current),
    )
    return _S.SET_INTERVAL


async def _pick_start_time(query, context, date_str: str) -> int:
    context.user_data["new_day_date"] = date_str
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    await query.edit_message_text(
        f"📅 *{escape_mdv2(format_date_ua(dt))}*\n\n🕐 Обери час *початку* робочого дня:",
        parse_mode="MarkdownV2",
        reply_markup=time_picker_keyboard("start"),
    )
    return _S.ADD_DAY


async def _pick_end_time(query, context, start_h: int) -> int:
    context.user_data["new_day_start"] = f"{start_h:02d}:00"
    date_str = context.user_data.get("new_day_date", "")
    dt       = datetime.strptime(date_str, "%Y-%m-%d")
    await query.edit_message_text(
        f"📅 *{escape_mdv2(format_date_ua(dt))}*\n🕐 Початок: *{start_h:02d}:00*\n\n🕕 Обери час *кінця*:",
        parse_mode="MarkdownV2",
        reply_markup=time_picker_keyboard("end", selected_h=start_h),
    )
    return _S.ADD_DAY


async def _preview_new_day(query, context, end_h: int) -> int:
    end_s    = f"{end_h:02d}:00"
    start_s  = context.user_data.get("new_day_start", "09:00")
    date_str = context.user_data.get("new_day_date", "")
    dt       = datetime.strptime(date_str, "%Y-%m-%d")
    interval = sched.get_slot_interval()
    sh       = int(start_s.split(":")[0])
    slots_n  = (end_h - sh) * 60 // interval
    await query.edit_message_text(
        f"✅ *Підтвердження*\n\n"
        f"📅 {escape_mdv2(format_date_ua(dt))}\n"
        f"🕐 Початок: *{start_s}*\n"
        f"🕕 Кінець:  *{end_s}*\n"
        f"⏱ Слотів по {interval} хв: *{slots_n}*\n\nЗберегти цей день?",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Так, зберегти", callback_data=f"confirm_day|{date_str}|{start_s}|{end_s}")],
            [InlineKeyboardButton("✏️ Змінити час",   callback_data=f"cal_day_{date_str}")],
            [InlineKeyboardButton("↩️ До календаря",  callback_data="admin_add_day")],
        ]),
    )
    return _S.ADD_DAY


async def _save_new_day(query, data: str) -> int:
    _, date_str, start_s, end_s = data.split("|", 3)
    sched.add_working_day(date_str, start_s, end_s)
    dt       = datetime.strptime(date_str, "%Y-%m-%d")
    interval = sched.get_slot_interval()
    await query.edit_message_text(
        f"✅ *Робочий день додано\\!*\n\n"
        f"📅 {escape_mdv2(format_date_ua(dt))}\n"
        f"🕐 {start_s} – {end_s}\n"
        f"⏱ Інтервал: {interval} хв\n\nОбери наступну дію:",
        parse_mode="MarkdownV2",
        reply_markup=admin_menu(),
    )
    return _S.MENU


async def _delete_day(query, day: str) -> int:
    sched.remove_working_day(day)
    dt = datetime.strptime(day, "%Y-%m-%d")
    await query.edit_message_text(
        f"✅ День *{format_date_ua(dt)}* видалено разом із записами.",
        parse_mode="Markdown",
        reply_markup=admin_menu(),
    )
    return _S.MENU


# startup ConversationHandler

def build_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^⚙️ Адмін панель$"), panel)],
        states={
            _S.MENU:         [CallbackQueryHandler(callback)],
            _S.ADD_DAY:      [CallbackQueryHandler(callback)],
            _S.DEL_DAY:      [CallbackQueryHandler(callback)],
            _S.SET_INTERVAL: [
                CallbackQueryHandler(callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_interval_text),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^/cancel$"), cancel_conv),
            MessageHandler(filters.Regex("^⚙️ Адмін панель$"), panel),
        ],
        allow_reentry=True,
    )