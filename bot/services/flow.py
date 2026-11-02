"""Pure rules for the kitchen side: status order, delivery-time parsing. No database, no Telegram."""
from __future__ import annotations

import re
from datetime import datetime, timedelta

# One step forward at a time (FR-K6). Anything else is refused.
NEXT_STATUS = {
    "confirmed": "preparing",
    "preparing": "ready",
    "ready": "out_for_delivery",
    "out_for_delivery": "delivered",
}
PREVIOUS_STATUS = {new: old for old, new in NEXT_STATUS.items()}
CANCELLABLE_BY_KITCHEN = ("confirmed", "preparing", "ready")  # paid, not yet out for delivery
QUICK_MINUTES = (30, 45, 60)


def next_status(current: str) -> str | None:
    return NEXT_STATUS.get(current)


def previous_status(new: str) -> str | None:
    return PREVIOUS_STATUS.get(new)


def parse_delivery_time(text: str | None, now: datetime) -> datetime | None:
    """'17:30' or '17.30' -> today at that time (same timezone as `now`). None if invalid or already past."""
    match = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", text or "")
    if not match:
        return None
    hours, minutes = int(match.group(1)), int(match.group(2))
    if hours > 23 or minutes > 59:
        return None
    when = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
    return when if when > now else None


def in_minutes(now: datetime, minutes: int) -> datetime:
    return (now + timedelta(minutes=minutes)).replace(second=0, microsecond=0)
