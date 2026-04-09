import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config import BOT_TOKEN, CLEANUP_HOUR, TIMEZONE
from db.pool import init_pool
from db.queries import create_tables
from services.cleanup import purge_past
import handlers.user    as user_h
import handlers.booking as booking_h
import handlers.cancel  as cancel_h
import handlers.admin   as admin_h

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def _start_scheduler() -> BackgroundScheduler:
    """
    cleaning in CLEANUP_HOUR in choosen timezone.
    """
    scheduler = BackgroundScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        purge_past,
        trigger=CronTrigger(hour=CLEANUP_HOUR, minute=0, timezone=TIMEZONE),
        id="nightly_cleanup",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started — cleanup at %02d:00 %s", CLEANUP_HOUR, TIMEZONE)
    return scheduler


def main() -> None:
    # db
    try:
        init_pool()
        create_tables()
        logger.info("Database ready.")
    except Exception as exc:
        logger.critical("DB init failed: %s", exc)
        raise SystemExit(1) from exc

    # CLEANUP_HOUR cleaning
    _start_scheduler()

    # Telegram Application
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", user_h.start))
    app.add_handler(booking_h.build_handler())
    app.add_handler(cancel_h.build_handler())
    app.add_handler(admin_h.build_handler())
    app.add_handler(MessageHandler(filters.Regex("^📋 Мої записи$"), user_h.my_bookings))

    logger.info("Bot is running.")
    app.run_polling()


if __name__ == "__main__":
    main()