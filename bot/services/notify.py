"""Sending messages to staff and customers. A failed message is logged, never raised."""
from __future__ import annotations

import logging

from telegram import InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import TelegramError

from .. import db

log = logging.getLogger("fitmeal.notify")


async def staff_ids(cfg) -> set[int]:
    """Every active staff member plus every owner listed in ADMIN_IDS."""
    rows = await db.fetch_all("SELECT tg_user_id FROM staff WHERE is_active")
    return set(cfg.owner_ids) | {r["tg_user_id"] for r in rows}


async def send_staff(bot, cfg, text: str, photo: str | None = None, markup: InlineKeyboardMarkup | None = None) -> int:
    """Send to all staff. Returns how many received it."""
    delivered = 0
    for chat_id in await staff_ids(cfg):
        try:
            if photo:
                await bot.send_photo(chat_id, photo, caption=text, parse_mode=ParseMode.HTML, reply_markup=markup)
            else:
                await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=markup)
            delivered += 1
        except TelegramError as exc:
            log.warning("Could not message staff %s: %s", chat_id, exc)
    return delivered


async def send_customer(bot, tg_user_id: int, text: str, markup: InlineKeyboardMarkup | None = None) -> bool:
    try:
        await bot.send_message(tg_user_id, text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return True
    except TelegramError as exc:
        log.warning("Could not message customer %s: %s", tg_user_id, exc)
        return False
