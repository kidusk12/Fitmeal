"""Operations (Phase 8): /status, /backup, the daily backup, the start-up notice, logging to a file,
and friendly answers when buttons or text from before a restart arrive."""
from __future__ import annotations

import logging
import os
import time as clock
from datetime import datetime, time, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters,
)

from .. import backup, db, texts
from ..services import notify, opsrules, payments, users
from . import payment
from . import start as home

log = logging.getLogger("fitmeal.ops")

ROOT = Path(__file__).resolve().parent.parent.parent
LOG_FILE = ROOT / "logs" / "fitmeal.log"
# Buttons that are meant to do nothing. If a screen has one of these, tapping it stays silent.
QUIET_BUTTONS = {"noop", "nop", "none", "ignore", "-"}


# ---------- settings from .env (all optional) ----------

def _backup_time() -> time:
    return opsrules.parse_hhmm(os.getenv("BACKUP_TIME"), time(3, 0))


def _backup_keep() -> int:
    try:
        return max(1, int(os.getenv("BACKUP_KEEP", "14") or 14))
    except ValueError:
        return 14


def _flag(name: str, default: bool = True) -> bool:
    value = os.getenv(name, "").strip().lower()
    return default if value == "" else value not in ("0", "no", "false", "off")


# ---------- logging to a file ----------

def add_file_logging() -> None:
    """Keeps the last ~15 MB of logs in logs/fitmeal.log, next to what the console shows."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
        logging.getLogger().addHandler(handler)
    except OSError as exc:
        log.warning("Could not open the log file: %s", exc)


# ---------- start-up ----------

async def _counts() -> dict[str, int]:
    row = await db.fetch_one(
        """
        SELECT count(*) FILTER (WHERE status = 'payment_review')                                  AS review,
               count(*) FILTER (WHERE status = 'awaiting_payment')                                AS awaiting,
               count(*) FILTER (WHERE status IN ('confirmed','preparing','ready','out_for_delivery')) AS active
        FROM orders
        """
    )
    return {k: int(row[k]) for k in ("review", "awaiting", "active")}


async def on_startup(app: Application, cfg) -> None:
    """Called once the database is connected: schedules the daily backup and tells the owner(s) the bot is up."""
    app.bot_data["started_at"] = clock.time()
    app.job_queue.run_daily(
        daily_backup, time=_backup_time().replace(tzinfo=cfg.timezone), name="daily_backup"
    )
    log.info("Daily backup scheduled for %s", _backup_time().strftime("%H:%M"))
    if _flag("STARTUP_NOTICE"):
        try:
            counts = await _counts()
            text = texts.OPS_STARTED.format(**counts)
            for owner_id in cfg.owner_ids:
                await notify.send_customer(app.bot, owner_id, text)
        except Exception:  # a notice must never stop the bot from starting
            log.exception("Could not send the start-up notice")


# ---------- backups ----------

async def _send_file(bot, chat_id: int, path: Path, caption: str) -> bool:
    try:
        with open(path, "rb") as handle:
            await bot.send_document(chat_id, handle, filename=path.name, caption=caption)
        return True
    except (TelegramError, OSError) as exc:
        log.warning("Could not send the backup to %s: %s", chat_id, exc)
        return False


async def daily_backup(context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = home.get_config(context)
    try:
        path, counts = await backup.make_backup_async(cfg.database_url, keep=_backup_keep(), tz=cfg.timezone)
    except Exception as exc:
        log.exception("Daily backup failed")
        for owner_id in cfg.owner_ids:
            await notify.send_customer(context.bot, owner_id, texts.OPS_DAILY_BACKUP_FAILED.format(error=_short(exc)))
        return
    if _flag("BACKUP_SEND"):
        for owner_id in cfg.owner_ids:
            await _send_file(context.bot, owner_id, path, texts.OPS_BACKUP_CAPTION.format(rows=sum(counts.values())))


def _short(exc: Exception) -> str:
    import html
    return html.escape(str(exc).strip().splitlines()[0][:200] if str(exc).strip() else type(exc).__name__)


async def _owner_only(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    role = await home.get_role(update, context)
    if role != "owner":
        if update.message:
            await update.message.reply_text(texts.OPS_OWNER_ONLY)
        return False
    return True


async def backup_now(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _owner_only(update, context):
        return
    cfg = home.get_config(context)
    await update.message.reply_text(texts.OPS_BACKUP_WORKING)
    try:
        path, counts = await backup.make_backup_async(cfg.database_url, keep=_backup_keep(), tz=cfg.timezone)
    except Exception as exc:
        log.exception("Backup on request failed")
        await update.message.reply_text(texts.OPS_BACKUP_FAILED.format(error=_short(exc)), parse_mode=ParseMode.HTML)
        return
    sent = await _send_file(context.bot, update.effective_chat.id, path,
                            texts.OPS_BACKUP_CAPTION.format(rows=sum(counts.values())))
    if not sent:
        await update.message.reply_text(texts.OPS_BACKUP_SAVED_ONLY.format(name=path.name))


# ---------- /status ----------

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _owner_only(update, context):
        return
    cfg = home.get_config(context)
    lines = [texts.OPS_STATUS_HEADER]

    started = context.application.bot_data.get("started_at")
    if started:
        lines.append(texts.OPS_STATUS_UPTIME.format(uptime=opsrules.format_uptime(clock.time() - started)))

    began = clock.perf_counter()
    try:
        await db.fetch_one("SELECT 1 AS ok")
        lines.append(texts.OPS_STATUS_DB_OK.format(ms=int((clock.perf_counter() - began) * 1000)))
    except Exception:
        lines.append(texts.OPS_STATUS_DB_DOWN)
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)
        return

    jobs = context.application.job_queue.get_jobs_by_name("payment_timers")
    next_run = getattr(jobs[0], "next_t", None) if jobs else None
    if next_run:
        seconds = max(0, int((next_run - datetime.now(timezone.utc)).total_seconds()))
        lines.append(texts.OPS_STATUS_TIMER_OK.format(seconds=seconds))
    else:
        lines.append(texts.OPS_STATUS_TIMER_DOWN)

    latest = backup.latest_backup()
    if latest:
        when = datetime.fromtimestamp(latest.stat().st_mtime, cfg.timezone).strftime("%Y-%m-%d %H:%M")
        lines.append(texts.OPS_STATUS_BACKUP.format(when=when))
    else:
        lines.append(texts.OPS_STATUS_NO_BACKUP)

    midnight = datetime.now(cfg.timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await db.fetch_all(
        "SELECT status, count(*) AS n FROM orders WHERE created_at >= %s GROUP BY status ORDER BY status", (midnight,)
    )
    total = sum(int(r["n"]) for r in rows)
    detail = ", ".join("{} {}".format(texts.STATUS_LABELS.get(r["status"], r["status"]), r["n"]) for r in rows)
    lines.append(texts.OPS_STATUS_TODAY.format(total=total, detail=(" (" + detail + ")") if detail else ""))
    counts = await _counts()
    lines.append(texts.OPS_STATUS_WAITING.format(**counts))
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


# ---------- after a restart ----------

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Text nobody was waiting for. A customer who owes a screenshot gets the usual reminder;
    anyone else (for example someone whose half-finished checkout was lost in a restart) is pointed to /start."""
    user = await users.ensure_user(update)
    if await payments.candidates(user["id"]):
        await payment.on_text_while_unpaid(update, context)
        return
    now = clock.monotonic()
    if opsrules.stray_reply_allowed(context.user_data.get("stray_at"), now):
        context.user_data["stray_at"] = now
        await update.message.reply_text(texts.OPS_STRAY)


async def on_stale_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A button no handler wants: usually an old message from before a restart."""
    query = update.callback_query
    if (query.data or "") in QUIET_BUTTONS:
        await query.answer()
        return
    await query.answer(texts.OPS_STALE, show_alert=True)


def register(app: Application) -> None:
    """Called at the end of handlers.register(), after every other handler is in place."""
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("backup", backup_now))

    # Swap the old "text while unpaid" handler for ours, in the same position, so it still comes last.
    new_text = MessageHandler(filters.TEXT & ~filters.COMMAND, on_text)
    handlers = app.handlers.get(0, [])
    for index, existing in enumerate(handlers):
        if getattr(existing, "callback", None) is payment.on_text_while_unpaid:
            handlers[index] = new_text
            break
    else:
        app.add_handler(new_text)
        log.warning("The old text handler was not found; added the new one at the end")

    # Last of all: any button nobody handled.
    app.add_handler(CallbackQueryHandler(on_stale_button))
