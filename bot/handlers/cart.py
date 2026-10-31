"""Cart screen (quantities, remove, clear) and the 'add a note' conversation."""
from __future__ import annotations

import html
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton as Button
from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .. import db, texts, ui
from ..services import allergy, cart, users
from . import start as home

PATTERN = r"^(cart|cart:(inc|dec|del):\d+|cart:clear)$"
NOTE = 0


async def build_cart(user: dict, tz: ZoneInfo) -> tuple[str, InlineKeyboardMarkup]:
    items = await cart.list_items(user["id"])
    if not items:
        markup = InlineKeyboardMarkup(
            [
                [Button("🍽 Browse menu", callback_data="browse")],
                [Button("⬅️ Back", callback_data="c:home")],
            ]
        )
        return texts.CART_EMPTY, markup

    today = datetime.now(tz).date()
    ingredients = await cart.ingredients_for([i["meal_id"] for i in items])
    show_legend = False
    subtotal = 0
    lines = [texts.CART_HEADER]
    buttons = []

    for n, item in enumerate(items, start=1):
        available = item["is_active"] and item["sold_out_on"] != today
        hits = allergy.find_conflicts(user.get("allergies"), ingredients.get(item["meal_id"], []))
        line = "{}. <b>{}</b> {} × {} — {} ETB".format(
            n,
            html.escape(item["meal_code"]),
            html.escape(item["name"]),
            item["quantity"],
            item["price_etb"] * item["quantity"],
        )
        if hits:
            line += " ⚠️"
            show_legend = True
        lines.append(line)
        if item["note"]:
            lines.append("   📝 " + html.escape(item["note"]))
        if available:
            subtotal += item["price_etb"] * item["quantity"]
        else:
            lines.append(texts.CART_UNAVAILABLE)
        mid = str(item["meal_id"])
        buttons.append(
            [
                Button("➖", callback_data="cart:dec:" + mid),
                Button(item["meal_code"] + " ×" + str(item["quantity"]), callback_data="meal:" + mid),
                Button("➕", callback_data="cart:inc:" + mid),
                Button("📝", callback_data="note:edit:" + mid),
                Button("🗑", callback_data="cart:del:" + mid),
            ]
        )

    text = "\n".join(lines) + texts.CART_FOOTER.format(subtotal=subtotal)
    if show_legend:
        text += texts.CART_ALLERGY_LEGEND
    buttons.append([Button("🍽 Add more meals", callback_data="browse"), Button("🧹 Clear cart", callback_data="cart:clear")])
    buttons.append([Button("✅ Checkout", callback_data="checkout")])
    buttons.append([Button("⬅️ Back", callback_data="c:home")])
    return text, InlineKeyboardMarkup(buttons)


async def send_cart(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict) -> None:
    text, markup = await build_cart(user, home.get_config(context).timezone)
    await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""
    user = await users.ensure_user(update)

    if data.startswith("cart:inc:"):
        result = await cart.add_item(user["id"], int(data.split(":")[2]))
        if result == "max":
            await query.answer(texts.CART_MAX.format(n=cart.MAX_QUANTITY), show_alert=True)
        else:
            await query.answer()
    elif data.startswith("cart:dec:"):
        await cart.decrease_item(user["id"], int(data.split(":")[2]))
        await query.answer()
    elif data.startswith("cart:del:"):
        await cart.remove_item(user["id"], int(data.split(":")[2]))
        await query.answer()
    elif data == "cart:clear":
        await cart.clear(user["id"])
        await query.answer()
    else:
        await query.answer()

    text, markup = await build_cart(user, home.get_config(context).timezone)
    await ui.render(query, text, markup)


# ---------- notes ----------

async def note_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    _, mode, meal_id_text = query.data.split(":")
    meal_id = int(meal_id_text)
    meal = await db.fetch_one("SELECT meal_code, name FROM meals WHERE id = %s AND is_active", (meal_id,))
    if meal is None:
        await query.answer(texts.MEAL_UNAVAILABLE, show_alert=True)
        return ConversationHandler.END
    await query.answer()
    context.user_data["note_target"] = {"meal_id": meal_id, "mode": mode}
    rows = []
    if mode == "edit":
        rows.append([Button("🗑 Remove note", callback_data="note:clear")])
    rows.append([Button("✖️ Cancel", callback_data="note:cancel")])
    await update.effective_chat.send_message(
        texts.ASK_NOTE.format(code=html.escape(meal["meal_code"]), name=html.escape(meal["name"])),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(rows),
    )
    return NOTE


async def note_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target = context.user_data.get("note_target")
    if not target:
        return ConversationHandler.END
    note = (update.message.text or "").strip()
    if not note:
        return NOTE
    if len(note) > 120:
        await update.message.reply_text(texts.NOTE_TOO_LONG)
        return NOTE
    context.user_data.pop("note_target", None)
    user = await users.ensure_user(update)
    if target["mode"] == "add":
        result = await cart.add_item(user["id"], target["meal_id"], note)
        if result == "full":
            await update.message.reply_text(texts.CART_FULL.format(n=cart.MAX_LINES))
        elif result == "max":
            await update.message.reply_text(texts.CART_MAX.format(n=cart.MAX_QUANTITY))
    else:
        await cart.set_note(user["id"], target["meal_id"], note)
    await send_cart(update, context, user)
    return ConversationHandler.END


async def note_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    target = context.user_data.pop("note_target", None)
    user = await users.ensure_user(update)
    if target:
        await cart.set_note(user["id"], target["meal_id"], None)
    await send_cart(update, context, user)
    return ConversationHandler.END


async def note_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data.pop("note_target", None)
    user = await users.ensure_user(update)
    await send_cart(update, context, user)
    return ConversationHandler.END


async def note_abort_to_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/start while a note is being typed: drop the note and show the home menu."""
    context.user_data.pop("note_target", None)
    await users.ensure_user(update)
    role = await home.get_role(update, context)
    text, markup = home.home_for(role)
    await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    return ConversationHandler.END


def note_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(note_entry, pattern=r"^note:(add|edit):\d+$")],
        states={
            NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, note_text),
                CallbackQueryHandler(note_clear, pattern=r"^note:clear$"),
                CallbackQueryHandler(note_cancel, pattern=r"^note:cancel$"),
            ]
        },
        fallbacks=[
            CommandHandler("start", note_abort_to_home),
            CommandHandler("cancel", note_cancel),
        ],
        allow_reentry=True,
    )
