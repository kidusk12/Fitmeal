"""Reads settings from the .env file. Nothing secret lives in the code."""
from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_url: str
    owner_ids: frozenset[int]
    timezone: ZoneInfo
    log_level: str


def _parse_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            raise SystemExit(f"ADMIN_IDS contains a non-numeric value: {part!r}")
    return frozenset(ids)


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN is missing in .env")
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("DATABASE_URL is missing in .env")
    owner_ids = _parse_ids(os.getenv("ADMIN_IDS", ""))
    if not owner_ids:
        raise SystemExit("ADMIN_IDS must contain at least one Telegram ID")
    return Config(
        bot_token=token,
        database_url=dsn,
        owner_ids=owner_ids,
        timezone=ZoneInfo(os.getenv("TIMEZONE", "Africa/Addis_Ababa").strip()),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
    )
