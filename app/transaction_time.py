from datetime import datetime, timedelta, timezone


MOSCOW_TZ = timezone(timedelta(hours=3), name="MSK")


def moscow_now() -> datetime:
    return datetime.now(MOSCOW_TZ)


def to_moscow(value: datetime) -> datetime:
    # Значение без смещения считается московским местным временем.
    if value.tzinfo is None:
        return value.replace(tzinfo=MOSCOW_TZ)
    return value.astimezone(MOSCOW_TZ)


def moscow_db_now() -> datetime:
    # SQLite не сохраняет timezone: храним местное время МСК без смещения.
    return moscow_now().replace(tzinfo=None)
