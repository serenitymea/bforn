from datetime import datetime

_MONTHS_UA   = ["січня","лютого","березня","квітня","травня","червня",
                 "липня","серпня","вересня","жовтня","листопада","грудня"]
_WEEKDAYS_UA = ["понеділок","вівторок","середа","четвер","п'ятниця","субота","неділя"]


def format_date_ua(dt: datetime) -> str:
    return f"{dt.day} {_MONTHS_UA[dt.month - 1]} ({_WEEKDAYS_UA[dt.weekday()]})"


def escape_mdv2(text: str) -> str:
    """parse_mode=Markdown(V2)"""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def escape_md(text: str) -> str:
    """parse_mode=Markdown(v1)"""
    for ch in r"\_*`[":
        text = text.replace(ch, f"\\{ch}")
    return text