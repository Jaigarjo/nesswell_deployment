from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, available_timezones


def logical_day(ts: datetime, tz_name: str, cutoff_hour: int = 4) -> date:
    """The day a log belongs to, in the user's local time.

    Anything before `cutoff_hour` counts toward the previous day, so an evening
    check-in at 1am on Saturday is Friday's evening log.
    """
    if ts.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    local = ts.astimezone(ZoneInfo(tz_name))
    return (local - timedelta(hours=cutoff_hour)).date()


def is_valid_timezone(tz_name: str) -> bool:
    return tz_name in available_timezones()


def reminder_due(
    now: datetime,
    tz_name: str,
    reminder: time,
    cutoff_hour: int = 4,
    window: timedelta = timedelta(hours=3),
) -> date | None:
    """If a reminder should fire now, return the logical day it's for, else None.

    Times are compared on the logical-day clock (which starts at `cutoff_hour`),
    so a 00:30 evening reminder still belongs to the day before. The window lets
    a late-running scheduler still send, but never hours later.
    """
    shifted = now.astimezone(ZoneInfo(tz_name)) - timedelta(hours=cutoff_hour)
    now_min = shifted.hour * 60 + shifted.minute
    rem_min = ((reminder.hour - cutoff_hour) % 24) * 60 + reminder.minute
    if 0 <= now_min - rem_min <= window.total_seconds() / 60:
        return shifted.date()
    return None
