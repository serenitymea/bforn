import logging
from datetime import datetime

import pytz

from config import TIMEZONE
from db.queries import purge_past_data

logger = logging.getLogger(__name__)


def purge_past(tz_name: str = TIMEZONE) -> None:

    today = datetime.now(pytz.timezone(tz_name)).strftime("%Y-%m-%d")
    try:
        deleted_bookings, deleted_days = purge_past_data(before_date=today)
        if deleted_bookings or deleted_days:
            logger.info(
                "Cleanup: removed %d booking(s) and %d working day(s) before %s",
                deleted_bookings, deleted_days, today,
            )
        else:
            logger.debug("Cleanup: nothing to remove (before %s)", today)
    except Exception:
        logger.exception("Cleanup failed — will retry at next scheduled run")