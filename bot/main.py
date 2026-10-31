"""Starts the FitMeal bot.  Run from the project folder:  python -m bot.main"""
from __future__ import annotations

import asyncio
import logging
import sys

from telegram import Update
from telegram.ext import Application, ApplicationBuilder, ContextTypes

from . import db
from .config import load_config
from .handlers import register

if sys.platform == "win32":
    # psycopg's async mode does not work on Windows' default event loop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

log = logging.getLogger("fitmeal")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Unhandled error while processing an update", exc_info=context.error)


def main() -> None:
    cfg = load_config()
    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    async def post_init(app: Application) -> None:
        await db.open_pool(cfg.database_url)
        await db.ensure_owners(cfg.owner_ids)
        log.info("Database connected")

    async def post_shutdown(app: Application) -> None:
        await db.close_pool()

    app = (
        ApplicationBuilder()
        .token(cfg.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.bot_data["config"] = cfg
    register(app)
    app.add_error_handler(on_error)

    log.info("Starting FitMeal (polling)")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
