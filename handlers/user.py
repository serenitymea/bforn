import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from db import queries
from utils.auth import is_admin
from utils.formatting import format_date_ua, escape_mdv2
from utils.keyboards import main_keyboard

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    queries.upsert_user(user.id, user.username or "", user.full_name)
    admin = is_admin(update)
    name  = escape_mdv2(user.first_name or "учню")
    text  = (
        f"👋 Вітаю, {name}\\!\n\n"
        "Це бот для запису на заняття\\. Тут ти можеш:\n"
        "• Обрати зручний час і записатися\n"
        "• Переглянути свої записи\n"
        "• Скасувати запис\n\n"
        "Обери дію нижче 👇"
    )
    if admin:
        text += "\n\n🔑 Ти маєш доступ до адмін\\-панелі\\."
    await update.message.reply_text(text, reply_markup=main_keyboard(admin), parse_mode="MarkdownV2")


async def my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if is_admin(update):
        bookings = queries.get_all_upcoming_bookings()
        if not bookings:
            await update.message.reply_text("📋 Немає активних записів учнів.")
            return
        lines = ["📋 Всі записи учнів:\n"]
        for b in bookings:
            dt   = datetime.strptime(b["date"], "%Y-%m-%d")
            name = b.get("full_name") or b.get("username") or "Невідомий"
            lines.append(f"• {format_date_ua(dt)} о {b['time']} — {name}")
        await update.message.reply_text("\n".join(lines))
    else:
        user_id  = update.effective_user.id
        bookings = queries.get_user_bookings(user_id)
        if not bookings:
            await update.message.reply_text(
                "📋 У тебе немає активних записів.\n"
                "Натисни «📅 Записатися на заняття», щоб обрати час."
            )
            return
        lines = ["📋 Твої записи:\n"]
        for b in bookings:
            dt = datetime.strptime(b["date"], "%Y-%m-%d")
            lines.append(f"• {format_date_ua(dt)} о {b['time']}")
        await update.message.reply_text("\n".join(lines))