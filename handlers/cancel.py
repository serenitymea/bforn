from datetime import datetime

from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler,
    MessageHandler, CallbackQueryHandler, filters,
)

from config import BookingState
from db import queries
from services import booking as booking_svc
from utils.auth import is_admin
from utils.formatting import format_date_ua
from utils.keyboards import cancel_bookings_keyboard, main_keyboard

_S = BookingState


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id  = update.effective_user.id
    bookings = queries.get_user_bookings(user_id)
    if not bookings:
        await update.message.reply_text("📋 У тебе немає активних записів для скасування.")
        return ConversationHandler.END
    await update.message.reply_text(
        "Який запис скасувати?",
        reply_markup=cancel_bookings_keyboard(bookings, format_date_ua),
    )
    return _S.CANCEL_SELECT


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("↩️ Скасування відмінено.")
        return ConversationHandler.END

    booking_id = int(query.data.removeprefix("cancel_book_"))
    booking_svc.cancel(booking_id, update.effective_user.id)
    await query.edit_message_text("✅ Запис успішно скасовано.")
    return ConversationHandler.END


async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("↩️ Дію скасовано.", reply_markup=main_keyboard(is_admin(update)))
    return ConversationHandler.END


def build_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^❌ Скасувати запис$"), start)],
        states={
            _S.CANCEL_SELECT: [CallbackQueryHandler(confirm, pattern=r"^(cancel_book_\d+|cancel$)")],
        },
        fallbacks=[MessageHandler(filters.Regex("^/cancel$"), cancel_conv)],
        per_message=False,
        allow_reentry=True,
    )