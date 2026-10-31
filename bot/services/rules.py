"""Small pure rules for ordering: opening hours, day boundaries and Order IDs.

Nothing here touches the database or Telegram, so it is easy to test.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta


def parse_hhmm(value: str | None, default: time) -> time:
    """Turn '08:00' into a time. Falls back to `default` if the setting is missing or malformed."""
    try:
        hours, minutes = str(value).strip().split(":")
        return time(int(hours), int(minutes))
    except (ValueError, TypeError):
        return default


def is_open(now: time, opens: time, closes: time) -> bool:
    """True if `now` is inside opening hours.

    Handles kitchens that close after midnight (opens 18:00, closes 02:00).
    If opens == closes the kitchen is treated as open all day.
    """
    if opens == closes:
        return True
    if opens < closes:
        return opens <= now < closes
    return now >= opens or now < closes


def day_bounds(now: datetime) -> tuple[datetime, datetime]:
    """Start (inclusive) and end (exclusive) of the local calendar day containing `now`."""
    start = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)
    return start, start + timedelta(days=1)


def order_code(day: date, number: int) -> str:
    """FIT-YYMMDD-NNN, for example FIT-261030-007."""
    return f"FIT-{day:%y%m%d}-{number:03d}"


def alert_kind(elapsed_minutes: float, review_minutes: int) -> str:
    """'reminder' while the kitchen is still inside its review window, 'overdue' once it is over (FR-P4)."""
    return "overdue" if elapsed_minutes >= review_minutes else "reminder"


def clock(moment: datetime, tz) -> str:
    """Time of day in the shop's timezone, e.g. '14:32'."""
    return moment.astimezone(tz).strftime("%H:%M")
