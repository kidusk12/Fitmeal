"""Pure helpers for backups and operations (Phase 8). No database, no Telegram."""
from __future__ import annotations

import re
from datetime import time


def parse_hhmm(text: str | None, default: time) -> time:
    """'03:00' or '3.30' -> time. Anything else gives the default."""
    match = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", text or "")
    if not match:
        return default
    hours, minutes = int(match.group(1)), int(match.group(2))
    return time(hours, minutes) if hours < 24 and minutes < 60 else default


def format_uptime(seconds: float) -> str:
    seconds = max(0, int(seconds))
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return "{}d {}h".format(days, hours)
    if hours:
        return "{}h {}m".format(hours, minutes)
    return "{}m".format(minutes)


def order_tables(tables: list[str], foreign_keys: list[tuple[str, str]]) -> list[str]:
    """Parents before children, so a restore never inserts a row whose parent is missing.

    foreign_keys is a list of (child_table, parent_table). A table that points at itself is ignored.
    Tables left in a cycle are added at the end, A to Z.
    """
    parents = {t: set() for t in tables}
    for child, parent in foreign_keys:
        if child in parents and parent in parents and child != parent:
            parents[child].add(parent)
    ordered: list[str] = []
    remaining = sorted(tables)
    while remaining:
        ready = [t for t in remaining if parents[t] <= set(ordered)]
        if not ready:
            ordered.extend(remaining)
            break
        ordered.extend(ready)
        remaining = [t for t in remaining if t not in ready]
    return ordered


def files_to_delete(names: list[str], keep: int) -> list[str]:
    """Backup file names are fitmeal-YYYYMMDD-HHMMSS.sql, so sorting by name sorts by time."""
    backups = sorted(n for n in names if re.fullmatch(r"fitmeal-\d{8}-\d{6}\.sql", n))
    return backups[:-keep] if keep > 0 and len(backups) > keep else ([] if keep > 0 else backups)


def stray_reply_allowed(last_sent: float | None, now: float, gap_seconds: float = 60.0) -> bool:
    """Do not answer stray text more than once a minute per person."""
    return last_sent is None or now - last_sent >= gap_seconds
