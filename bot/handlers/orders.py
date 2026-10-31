"""Order history and Reorder."""
from __future__ import annotations

import html

from telegram import InlineKeyboardButton as Button
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .. import db, texts, ui
from ..services import cart, users
from . import cart as cart_screen
from . import start as home

PATTERN = r"^(orders|reorder:\d+)$"


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    user = await users.ensure_user(update)
    tz = home.get_config(context).timezone

    if data == "orders":
        rows = await db.fetch_all(
            """
            SELECT id, order_code, status, total_etb, created_at
            FROM orders WHERE customer_id = %s ORDER BY created_at DESC LIMIT 10
            """,
            (user["id"],),
        )
        if not rows:
            markup = InlineKeyboardMarkup([[Button("⬅️ Back", callback_data="c:home")]])
            await ui.render(query, texts.ORDERS_EMPTY, markup)
            return
        lines = [texts.ORDERS_HEADER]
        buttons = []
        for r in rows:
            label = texts.STATUS_LABELS.get(r["status"], r["status"])
            when = r["created_at"].astimezone(tz).strftime("%d %b %H:%M")
            lines.append(
                "<b>" + html.escape(r["order_code"]) + "</b> · " + label + " · " + str(r["total_etb"]) + " ETB\n   " + when
            )
            buttons.append([Button("🔁 Reorder " + r["order_code"], callback_data="reorder:" + str(r["id"]))])
        buttons.append([Button("⬅️ Back", callback_data="c:home")])
        await ui.render(query, "\n".join(lines), InlineKeyboardMarkup(buttons))

    elif data.startswith("reorder:"):
        order_id = int(data.split(":")[1])
        owned = await db.fetch_one(
            "SELECT id FROM orders WHERE id = %s AND customer_id = %s", (order_id, user["id"])
        )
        if owned is None:
            return
        await db.execute(
            """
            INSERT INTO cart_items (user_id, meal_id, quantity, note)
            SELECT %s, oi.meal_id, LEAST(oi.quantity, %s), oi.note
            FROM order_items oi JOIN meals m ON m.id = oi.meal_id
            WHERE oi.order_id = %s AND m.is_active
            ON CONFLICT (user_id, meal_id) DO UPDATE SET
                quantity = LEAST(cart_items.quantity + EXCLUDED.quantity, %s)
            """,
            (user["id"], cart.MAX_QUANTITY, order_id, cart.MAX_QUANTITY),
        )
        text, markup = await cart_screen.build_cart(user, tz)
        await ui.render(query, text, markup)
