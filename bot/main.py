"""Starts the FitMeal bot.  Run from the project folder:  python -m bot.main"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
import warnings

from telegram import Update
from telegram.error import NetworkError
from telegram.ext import Application, ApplicationBuilder, ContextTypes

from . import db
from .config import load_config
from .handlers import register

if sys.platform == "win32":
    # psycopg's async mode does not work on Windows' default event loop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

log = logging.getLogger("fitmeal")

# PTB prints a harmless notice about inline buttons inside conversations; hide it.
warnings.filterwarnings("ignore", message=r".*per_message.*")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Unhandled error while processing an update", exc_info=context.error)


def build_app(cfg) -> Application:
    async def post_init(app: Application) -> None:
        await db.open_pool(cfg.database_url)
        await db.ensure_owners(cfg.owner_ids)
        log.info("Database connected")

    async def post_shutdown(app: Application) -> None:
        await db.close_pool()

    app = (
        ApplicationBuilder()
        .token(cfg.bot_token)
        # Telegram's defaults (5 seconds) are too short on a slow connection.
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(40)
        .get_updates_write_timeout(30)
        .get_updates_pool_timeout(30)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data["config"] = cfg
    register(app)
    app.add_error_handler(on_error)
    return app


def main() -> None:
    cfg = load_config()
    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    log.info("Starting FitMeal (polling)")
    delay = 5
    while True:
        try:
            # close_loop=False so the next attempt can reuse the event loop after a failed start
            build_app(cfg).run_polling(
                allowed_updates=Update.ALL_TYPES, bootstrap_retries=-1, close_loop=False
            )
            return  # normal stop (Ctrl+C)
        except NetworkError as exc:
            # Could not reach Telegram while starting (dropped connection, timeout...). Try again.
            log.warning("Could not reach Telegram (%s). Retrying in %s seconds...", exc, delay)
            time.sleep(delay)
            delay = min(delay * 2, 60)


if __name__ == "__main__":
    main()
