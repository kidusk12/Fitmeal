"""Pure rules for the owner tools (SRS FR-A1 to FR-A5): input parsing and report periods.

Nothing here touches the database or Telegram, so it is easy to test.
Every parser returns None (or an error code) instead of raising, so the handler can just re-ask.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from . import phone, rules

# Settings the owner can change. key -> (label, kind, low, high, unit)
SETTINGS = {
    "delivery_fee_etb": ("Delivery fee", "int", 0, 5000, "ETB"),
    "daily_order_limit": ("Daily order limit", "int", 1, 2000, "orders"),
    "opening_time": ("Opening time", "time", None, None, ""),
    "closing_time": ("Closing time", "time", None, None, ""),
    "payment_window_min": ("Customer payment window", "int", 1, 120, "minutes"),
    "kitchen_review_min": ("Kitchen review window", "int", 1, 240, "minutes"),
    "alert_repeat_min": ("Overdue alert repeat", "int", 1, 120, "minutes"),
}

# The four allergen tags the allergy check understands (see services/allergy.py)
ALLERGENS = ("dairy", "egg", "peanut", "gluten")
UNITS = ("g", "ml", "pcs")

MAX_INGREDIENTS = 20

# Orders whose payment was approved and not refunded: these count as revenue (FR-A5)
CONFIRMED_STATUSES = ("confirmed", "preparing", "ready", "out_for_delivery", "delivered")


def clean_text(text: str | None) -> str:
    """Trim and collapse inner spaces and tabs (new lines are kept)."""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in (text or "").strip().splitlines()]
    return "\n".join(lines).strip()


def parse_name(text: str | None, low: int = 2, high: int = 60) -> str | None:
    value = re.sub(r"\s+", " ", (text or "").strip())
    return value if low <= len(value) <= high else None


def parse_optional_text(text: str | None, high: int) -> str | None | bool:
    """'-' means 'leave it empty' and returns ''. Too long or empty input returns False."""
    value = clean_text(text)
    if value == "-":
        return ""
    if not value or len(value) > high:
        return False
    return value


def parse_int(text: str | None, low: int, high: int) -> int | None:
    value = (text or "").strip()
    if not re.fullmatch(r"\d{1,9}", value):
        return None
    number = int(value)
    return number if low <= number <= high else None


def parse_time(text: str | None) -> str | None:
    """'8:00', '08:00' or '8.30' -> '08:00' / '08:30'. None if it is not a real time of day."""
    match = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", text or "")
    if not match:
        return None
    hours, minutes = int(match.group(1)), int(match.group(2))
    if hours > 23 or minutes > 59:
        return None
    return f"{hours:02d}:{minutes:02d}"


def parse_setting(key: str, text: str | None) -> str | None:
    """Validate a new value for one of the SETTINGS and return it as the string we store."""
    spec = SETTINGS.get(key)
    if spec is None:
        return None
    _, kind, low, high, _ = spec
    if kind == "time":
        return parse_time(text)
    number = parse_int(text, low, high)
    return None if number is None else str(number)


def setting_hint(key: str) -> str:
    label, kind, low, high, unit = SETTINGS[key]
    if kind == "time":
        return "a time as HH:MM (24-hour, Addis Ababa time), for example 08:00"
    return f"a whole number from {low} to {high} ({unit})"


def parse_telegram_id(text: str | None) -> int | None:
    value = (text or "").strip()
    if not re.fullmatch(r"\d{5,15}", value):
        return None
    return int(value)


def _decimal(token: str, high: int) -> Decimal | None:
    try:
        number = Decimal(token.replace(",", "."))
    except InvalidOperation:
        return None
    if not number.is_finite() or number < 0 or number > high:
        return None
    return number.quantize(Decimal("0.1"))


def parse_macros(text: str | None) -> tuple[int, Decimal, Decimal, Decimal] | None:
    """'420 28 55 10' -> (calories, protein_g, carbs_g, fat_g). Spaces or semicolons between the numbers."""
    tokens = [t for t in re.split(r"[\s;]+", (text or "").strip()) if t]
    if len(tokens) != 4 or not re.fullmatch(r"\d{1,4}", tokens[0]):
        return None
    calories = int(tokens[0])
    if calories > 5000:
        return None
    grams = [_decimal(t, 500) for t in tokens[1:]]
    if any(g is None for g in grams):
        return None
    return calories, grams[0], grams[1], grams[2]


def parse_price(text: str | None) -> int | None:
    return parse_int(text, 1, 100000)


_ING_LINE = re.compile(r"^(?P<name>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>g|ml|pcs)?$", re.IGNORECASE)


def parse_ingredients(text: str | None) -> tuple[list[tuple[str, Decimal, str | None]], str | None]:
    """'Chicken breast 150, Egg 3, Olive oil 5ml' -> ([(name, qty, unit_or_None), ...], error_code).

    Items are separated by commas or new lines. error_code is one of
    empty, format, qty, name, dup, toomany or None when everything is fine.
    """
    parts = [p.strip() for p in re.split(r"[,\n]+", text or "") if p.strip()]
    if not parts:
        return [], "empty"
    if len(parts) > MAX_INGREDIENTS:
        return [], "toomany"
    items: list[tuple[str, Decimal, str | None]] = []
    seen: set[str] = set()
    for part in parts:
        match = _ING_LINE.match(part)
        if not match:
            return [], "format"
        name = re.sub(r"\s+", " ", match.group("name")).strip(" -:")
        if not 2 <= len(name) <= 40 or not re.search(r"[A-Za-z]", name):
            return [], "name"
        try:
            qty = Decimal(match.group("qty"))
        except InvalidOperation:
            return [], "format"
        if qty <= 0 or qty > 99999:
            return [], "qty"
        key = name.lower()
        if key in seen:
            return [], "dup"
        seen.add(key)
        unit = match.group("unit").lower() if match.group("unit") else None
        items.append((name[:1].upper() + name[1:], qty.quantize(Decimal("0.01")), unit))
    return items, None


def next_meal_code(highest_number: int) -> str:
    """M-012 style code for the next meal, given the highest number used so far."""
    return f"M-{highest_number + 1:03d}"


def normalize_phones(text: str | None) -> tuple[list[str], list[str]]:
    """Split a typed list of phone numbers into (valid in +251 form, unreadable pieces)."""
    valid: list[str] = []
    bad: list[str] = []
    for piece in re.split(r"[,;\n]+|\s{2,}", text or ""):
        piece = piece.strip()
        if not piece:
            continue
        # A single space inside a number is allowed (0911 22 33 44), so also try the whole piece first
        number = phone.normalize_phone(piece)
        if number:
            if number not in valid:
                valid.append(number)
            continue
        for word in piece.split():
            number = phone.normalize_phone(word)
            if number:
                if number not in valid:
                    valid.append(number)
            else:
                bad.append(word)
    return valid, bad


PERIOD_LABELS = {"today": "Today", "yesterday": "Yesterday", "week": "Last 7 days"}


def period_bounds(now: datetime, kind: str) -> tuple[datetime, datetime] | None:
    """(start inclusive, end exclusive) in the shop's timezone for a report period (NFR-8)."""
    day_start, day_end = rules.day_bounds(now)
    if kind == "today":
        return day_start, day_end
    if kind == "yesterday":
        return day_start - timedelta(days=1), day_start
    if kind == "week":
        return day_start - timedelta(days=6), day_end
    return None
