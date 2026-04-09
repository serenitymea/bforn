from db import queries


def add_working_day(date: str, start_time: str, end_time: str) -> None:
    queries.upsert_working_day(date, start_time, end_time)


def remove_working_day(date: str) -> None:
    queries.delete_working_day(date)


def get_available_days(include_past: bool = False) -> list[str]:
    return queries.get_working_days(include_past=include_past)


def get_slot_interval() -> int:
    return int(queries.get_setting("slot_interval", "90"))


def set_slot_interval(minutes: int) -> None:
    queries.set_setting("slot_interval", str(minutes))


def get_admin_chat_id() -> int | None:
    v = queries.get_setting("admin_chat_id", "")
    return int(v) if v.strip().isdigit() else None


def set_admin_chat_id(chat_id: int) -> None:
    queries.set_setting("admin_chat_id", str(chat_id))