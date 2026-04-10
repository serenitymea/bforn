import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler,
    MessageHandler, CallbackQueryHandler, filters,
)

from config import BookingState, ADMIN_USER_ID
from db import queries
from services import booking as booking_svc
from services.schedule import get_available_days, get_admin_chat_id
from utils.auth import is_admin
from utils.formatting import format_date_ua, escape_md
from utils.keyboards import dates_keyboard, slots_keyboard, confirm_booking_keyboard, main_keyboard

logger = logging.getLogger(__name__)

_S = BookingState  # short alias


# addddhelp

async def _render_dates(query) -> int:
    """Перемальовує список дат (повторне використання з book_start і «назад»)."""
    days = get_available_days()
    if not days:
        await query.edit_message_text(
            "😔 Зараз немає доступних дат. Спробуй пізніше або зв'яжись з учителем."
        )
        return ConversationHandler.END
    await query.edit_message_text(
        "📅 *Обери дату заняття:*",
        parse_mode="Markdown",
        reply_markup=dates_keyboard(days, format_date_ua),
    )
    return _S.CHOOSE_DATE


# Handlers

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    queries.upsert_user(user.id, user.username or "", user.full_name)
    days = get_available_days()
    if not days:
        await update.message.reply_text(
            "😔 Зараз немає доступних дат. Спробуй пізніше або зв'яжись з учителем."
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "📅 *Обери дату заняття:*",
        parse_mode="Markdown",
        reply_markup=dates_keyboard(days, format_date_ua),
    )
    return _S.CHOOSE_DATE


async def choose_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("❌ Запис скасовано.")
        return ConversationHandler.END

    date_str = query.data.removeprefix("date_")
    context.user_data["booking_date"] = date_str

    slots = booking_svc.get_free_slots(date_str, update.effective_user.id)
    if not slots:
        await query.edit_message_text("😔 На цю дату вільних місць немає.")
        return await _render_dates(query)

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    await query.edit_message_text(
        f"📅 *{format_date_ua(dt)}*\n\nОбери зручний час:",
        parse_mode="Markdown",
        reply_markup=slots_keyboard(slots),
    )
    return _S.CHOOSE_TIME


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_dates":
        return await _render_dates(query)

    time_str = query.data.split("|", 1)[1]
    date_str = context.user_data.get("booking_date", "")

    slots = booking_svc.get_free_slots(date_str, update.effective_user.id)
    if time_str not in slots:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        await query.edit_message_text(
            f"⚠️ Цей час вже зайнятий.\n\n📅 *{format_date_ua(dt)}*\n\nОбери інший час:",
            parse_mode="Markdown",
            reply_markup=slots_keyboard(slots),
        )
        return _S.CHOOSE_TIME

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    await query.edit_message_text(
        f"📋 *Підтвердження запису*\n\n📅 {format_date_ua(dt)}\n🕐 {time_str}\n\nПідтверджуєш?",
        parse_mode="Markdown",
        reply_markup=confirm_booking_keyboard(date_str, time_str),
    )
    return _S.CONFIRM


async def finalize(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("❌ Запис скасовано.")
        return ConversationHandler.END

    parts = query.data.split("|")
    if len(parts) < 3:
        await query.edit_message_text("⚠️ Помилка даних.")
        return ConversationHandler.END

    _, date_str, time_str = parts
    user = update.effective_user

    if booking_svc.book(user.id, date_str, time_str):
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        await query.edit_message_text(
            f"✅ *Запис підтверджено!*\n\n📅 {format_date_ua(dt)}\n🕐 {time_str}\n\n"
            "Чекаємо тебе! Якщо плани зміняться — скасуй запис заздалегідь.",
            parse_mode="Markdown",
        )
        await _notify_admin(context, user, date_str, time_str)
    else:
        await query.edit_message_text("⚠️ Не вдалося записатися. Місце вже зайнято. Спробуй ще раз.")

    return ConversationHandler.END


async def _notify_admin(context, user, date_str: str, time_str: str) -> None:
    try:
        admin_id = get_admin_chat_id() or ADMIN_USER_ID
        if not admin_id:
            return
        dt       = datetime.strptime(date_str, "%Y-%m-%d")
        name     = escape_md(user.full_name or user.first_name or "Невідомий")
        username = f"@{escape_md(user.username)}" if user.username else "без юзернейму"
        await context.bot.send_message(
            admin_id,
            f"📬 *Новий запис!*\n\n👤 {name} ({username})\n📅 {format_date_ua(dt)}\n🕐 {time_str}",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.error("Failed to notify admin: %s", exc)


async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("↩️ Дію скасовано.", reply_markup=main_keyboard(is_admin(update)))
    return ConversationHandler.END


# startup ConversationHandler

def build_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^📅 Записатися на заняття$"), start)],
        states={
            _S.CHOOSE_DATE: [CallbackQueryHandler(choose_time)],
            _S.CHOOSE_TIME: [CallbackQueryHandler(confirm)],
            _S.CONFIRM:     [CallbackQueryHandler(finalize)],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^/cancel$"), cancel_conv),
            MessageHandler(filters.Regex("^📅 Записатися на заняття$"), start),
        ],
        per_message=False,
        allow_reentry=True,
    )