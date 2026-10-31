"""Checkout: destination, receiver, confirmation, placing an order, and cancelling it.

Flow:  cart -> Checkout -> destination -> receiver -> confirm -> order placed
The destination can be a Telegram pin, a Google Maps link, typed text, or a saved address.
"""
from __future__ import annotations

import html

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
from ..services import location, users
from ..services import orders as order_service
from ..services.orders import OrderRefused
from ..services.phone import normalize_phone
from . import cart as cart_screen
from . import start as home

DEST, RECEIVER, RCV_NAME, RCV_PHONE, CONFIRM, LABEL = range(6)
MAX_SAVED_ADDRESSES = 10
KEY = "checkout"

# Order cancelling works outside the conversation (from "My orders" or the confirmation screen)
PATTERN = r"^co:(cancel|cancelyes):\d+$"
# Any button that is not part of checkout: used to drop a half-finished checkout
LEAVING = r"^(?!co:|checkout$).*"


# ---------- small helpers ----------

async def _show(update: Update, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Edit the current message when a button was tapped, otherwise send a new message."""
    if update.callback_query:
        await ui.render(update.callback_query, text, markup)
    else:
        await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)


def _back_to_cart_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[Button("⬅️ Back to cart", callback_data="cart")]])


def _item_lines(items: list[dict]) -> list[str]:
    lines = []
    for n, item in enumerate(items, start=1):
        lines.append(
            "{}. <b>{}</b> {} × {} — {} ETB".format(
                n,
                html.escape(item["meal_code"]),
                html.escape(item["name"]),
                item["quantity"],
                item["price_etb"] * item["quantity"],
            )
        )
        if item["note"]:
            lines.append("   📝 " + html.escape(item["note"]))
    return lines


def _totals(q: dict) -> str:
    return (
        f"Subtotal: {q['subtotal']} ETB\n"
        f"Delivery: {q['fee']} ETB\n"
        f"<b>Total: {q['total']} ETB</b>"
    )


def _destination_line(state: dict) -> str:
    parts = []
    if state.get("text"):
        parts.append(html.escape(state["text"]))
    if state.get("lat") is not None:
        parts.append("📍 pinned location")
    return " · ".join(parts)


def _ready(state: dict | None) -> bool:
    return bool(
        state
        and (state.get("text") or state.get("lat") is not None)
        and state.get("receiver_name")
        and state.get("receiver_phone")
    )


# ---------- entry and destination ----------

async def _ask_destination(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict) -> int:
    tz = home.get_config(context).timezone
    q = await order_service.quote(user["id"], tz)
    saved = await db.fetch_all(
        "SELECT id, label FROM addresses WHERE user_id = %s ORDER BY id DESC LIMIT 5", (user["id"],)
    )
    rows = [[Button("📌 " + a["label"], callback_data=f"co:addr:{a['id']}")] for a in saved]
    rows.append([Button("⬅️ Back to cart", callback_data="co:abort")])
    summary = "\n".join(_item_lines(q["items"])) + "\n\n" + _totals(q)
    await _show(update, texts.CHECKOUT_DEST.format(summary=summary), InlineKeyboardMarkup(rows))
    return DEST


async def entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = await users.ensure_user(update)
    tz = home.get_config(context).timezone
    context.user_data.pop(KEY, None)

    q = await order_service.quote(user["id"], tz)
    if not q["items"]:
        await ui.render(query, texts.CHECKOUT_EMPTY, _back_to_cart_markup())
        return ConversationHandler.END
    if q["unavailable"]:
        names = ", ".join(i["meal_code"] for i in q["unavailable"])
        await ui.render(query, texts.CHECKOUT_UNAVAILABLE.format(names=html.escape(names)), _back_to_cart_markup())
        return ConversationHandler.END
    problem = await order_service.closed_message(tz)
    if problem:
        await ui.render(query, problem, _back_to_cart_markup())
        return ConversationHandler.END

    context.user_data[KEY] = {}
    return await _ask_destination(update, context, user)


async def _destination_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE, preview: bool) -> int:
    """Called once a destination is stored. Next: the receiver, or straight to confirm when changing it later."""
    state = context.user_data[KEY]
    user = await users.ensure_user(update)
    if preview and state.get("lat") is not None:
        # Send the pin back as a map so the customer can check what we understood (SRS 5.2).
        await update.effective_chat.send_location(state["lat"], state["lng"])
    if state.get("receiver_name"):
        return await _show_confirm(update, context, user)
    return await _ask_receiver(update, context, user)


async def pick_saved(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    state = context.user_data.get(KEY)
    if state is None:
        await ui.render(query, texts.CHECKOUT_EXPIRED, _back_to_cart_markup())
        return ConversationHandler.END
    user = await users.ensure_user(update)
    address_id = int(query.data.split(":")[2])
    row = await db.fetch_one(
        "SELECT latitude, longitude, address_text FROM addresses WHERE id = %s AND user_id = %s",
        (address_id, user["id"]),
    )
    if row is None:
        return DEST
    lat, lng = row["latitude"], row["longitude"]
    state.update(
        lat=lat, lng=lng, text=row["address_text"], address_id=address_id,
        maps_url=location.maps_link(lat, lng) if lat is not None else None,
    )
    return await _destination_chosen(update, context, preview=True)


async def dest_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    state = context.user_data.get(KEY)
    if state is None:
        await update.message.reply_text(texts.CHECKOUT_EXPIRED)
        return ConversationHandler.END
    msg = update.message
    lat, lng = msg.location.latitude, msg.location.longitude
    venue_text = None
    if msg.venue:  # a place picked from Telegram's venue list
        venue_text = ", ".join(part for part in (msg.venue.title, msg.venue.address) if part)[:200]
    state.update(lat=lat, lng=lng, text=venue_text, address_id=None, maps_url=location.maps_link(lat, lng))
    return await _destination_chosen(update, context, preview=False)


async def dest_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    state = context.user_data.get(KEY)
    if state is None:
        await update.message.reply_text(texts.CHECKOUT_EXPIRED)
        return ConversationHandler.END
    raw = (update.message.text or "").strip()
    url = location.find_url(raw)
    if url:
        coords = await location.coordinates_from_link(url)
        if coords is None:
            await update.message.reply_text(texts.ERR_MAPS_LINK)
            return DEST
        lat, lng = coords
        extra = raw.replace(url, "").strip()[:200] or None  # any words typed along with the link
        state.update(lat=lat, lng=lng, text=extra, address_id=None, maps_url=location.maps_link(lat, lng))
        return await _destination_chosen(update, context, preview=True)
    if not 3 <= len(raw) <= 200:
        await update.message.reply_text(texts.ERR_ADDRESS)
        return DEST
    state.update(lat=None, lng=None, text=raw, address_id=None, maps_url=None)
    return await _destination_chosen(update, context, preview=False)


# ---------- receiver ----------

async def _ask_receiver(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict) -> int:
    if not (user.get("full_name") and user.get("phone")):
        # No complete profile (for example a staff member previewing): ask for the receiver directly.
        await _show(update, texts.ASK_RECEIVER_NAME, InlineKeyboardMarkup([[Button("⬅️ Back", callback_data="co:back:dest")]]))
        return RCV_NAME
    me = f"👤 Me: {user['full_name']}, {user['phone']}"
    rows = [
        [Button(me, callback_data="co:rcv:me")],
        [Button("🎁 Someone else", callback_data="co:rcv:other")],
        [Button("⬅️ Back", callback_data="co:back:dest")],
    ]
    await _show(update, texts.ASK_RECEIVER, InlineKeyboardMarkup(rows))
    return RECEIVER


async def receiver_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    state = context.user_data.get(KEY)
    if state is None:
        await ui.render(query, texts.CHECKOUT_EXPIRED, _back_to_cart_markup())
        return ConversationHandler.END
    user = await users.ensure_user(update)
    if query.data == "co:rcv:me":
        state.update(receiver_name=user["full_name"], receiver_phone=user["phone"])
        return await _show_confirm(update, context, user)
    await ui.render(query, texts.ASK_RECEIVER_NAME, InlineKeyboardMarkup([[Button("⬅️ Back", callback_data="co:back:rcv")]]))
    return RCV_NAME


async def rcv_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    state = context.user_data.get(KEY)
    if state is None:
        await update.message.reply_text(texts.CHECKOUT_EXPIRED)
        return ConversationHandler.END
    name = (update.message.text or "").strip()
    if not 2 <= len(name) <= 80:
        await update.message.reply_text(texts.ERR_NAME, parse_mode=ParseMode.HTML)
        return RCV_NAME
    state["pending_receiver_name"] = name
    await update.message.reply_text(texts.ASK_RECEIVER_PHONE, parse_mode=ParseMode.HTML)
    return RCV_PHONE


async def rcv_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    state = context.user_data.get(KEY)
    if state is None:
        await update.message.reply_text(texts.CHECKOUT_EXPIRED)
        return ConversationHandler.END
    phone = normalize_phone(update.message.text)
    if phone is None:
        await update.message.reply_text(texts.ERR_PHONE)
        return RCV_PHONE
    state.update(receiver_name=state.pop("pending_receiver_name", None) or "Receiver", receiver_phone=phone)
    user = await users.ensure_user(update)
    return await _show_confirm(update, context, user)


# ---------- confirmation ----------

async def _show_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict, notice: str | None = None) -> int:
    tz = home.get_config(context).timezone
    state = context.user_data[KEY]
    q = await order_service.quote(user["id"], tz)
    if not q["items"]:
        await _show(update, texts.CHECKOUT_EMPTY, _back_to_cart_markup())
        context.user_data.pop(KEY, None)
        return ConversationHandler.END
    if q["unavailable"]:
        names = ", ".join(i["meal_code"] for i in q["unavailable"])
        await _show(update, texts.CHECKOUT_UNAVAILABLE.format(names=html.escape(names)), _back_to_cart_markup())
        context.user_data.pop(KEY, None)
        return ConversationHandler.END

    state["total"] = q["total"]  # what the customer is shown; checked again when they confirm
    lines = [texts.CONFIRM_HEADER]
    if notice:
        lines += [notice, ""]
    lines += _item_lines(q["items"])
    lines += ["", _totals(q), ""]
    lines.append("📍 Deliver to: " + _destination_line(state))
    lines.append("👤 Receiver: " + html.escape(state["receiver_name"]) + ", " + html.escape(state["receiver_phone"]))
    text = "\n".join(lines) + texts.CONFIRM_FOOTER

    rows = [[Button("✅ Place order", callback_data="co:place")]]
    if state.get("maps_url"):
        rows.append([Button("🗺 Open on map", url=state["maps_url"])])
    if not state.get("address_id"):
        rows.append([Button("💾 Save this address", callback_data="co:save")])
    rows.append(
        [Button("✏️ Destination", callback_data="co:back:dest"), Button("✏️ Receiver", callback_data="co:back:rcv")]
    )
    rows.append([Button("✖️ Cancel", callback_data="co:abort")])
    await _show(update, text, InlineKeyboardMarkup(rows))
    return CONFIRM


async def back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if context.user_data.get(KEY) is None:
        await ui.render(query, texts.CHECKOUT_EXPIRED, _back_to_cart_markup())
        return ConversationHandler.END
    user = await users.ensure_user(update)
    target = query.data.split(":")[2]
    if target == "dest":
        return await _ask_destination(update, context, user)
    if target == "rcv":
        return await _ask_receiver(update, context, user)
    return await _show_confirm(update, context, user)


async def abort(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Leave checkout and go back to the cart (the cart is untouched)."""
    query = update.callback_query
    await query.answer()
    context.user_data.pop(KEY, None)
    user = await users.ensure_user(update)
    text, markup = await cart_screen.build_cart(user, home.get_config(context).timezone)
    await ui.render(query, text, markup)
    return ConversationHandler.END


async def start_abort(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/start while checking out: drop the checkout and show the home menu."""
    context.user_data.pop(KEY, None)
    await users.ensure_user(update)
    role = await home.get_role(update, context)
    text, markup = home.home_for(role)
    await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    return ConversationHandler.END


async def forget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs (in an earlier handler group) whenever the customer taps something outside checkout.
    It only clears the half-finished checkout, so stray typed text is not mistaken for an address."""
    context.user_data.pop(KEY, None)


# ---------- saving an address ----------

async def save_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    state = context.user_data.get(KEY)
    if state is None:
        await query.answer()
        await ui.render(query, texts.CHECKOUT_EXPIRED, _back_to_cart_markup())
        return ConversationHandler.END
    user = await users.ensure_user(update)
    count = await db.fetch_one("SELECT count(*) AS n FROM addresses WHERE user_id = %s", (user["id"],))
    if count["n"] >= MAX_SAVED_ADDRESSES:
        await query.answer(texts.ADDRESS_LIMIT.format(n=MAX_SAVED_ADDRESSES), show_alert=True)
        return CONFIRM
    await query.answer()
    await ui.render(query, texts.ASK_ADDRESS_LABEL, InlineKeyboardMarkup([[Button("⬅️ Back", callback_data="co:back:confirm")]]))
    return LABEL


async def label_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    state = context.user_data.get(KEY)
    if state is None:
        await update.message.reply_text(texts.CHECKOUT_EXPIRED)
        return ConversationHandler.END
    label = (update.message.text or "").strip()
    if not 1 <= len(label) <= 30:
        await update.message.reply_text(texts.ERR_ADDRESS_LABEL)
        return LABEL
    user = await users.ensure_user(update)
    row = await db.fetch_one(
        """
        INSERT INTO addresses (user_id, label, latitude, longitude, address_text)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
        """,
        (user["id"], label, state.get("lat"), state.get("lng"), state.get("text")),
    )
    state["address_id"] = row["id"]
    return await _show_confirm(update, context, user, notice=texts.ADDRESS_SAVED)


# ---------- placing the order ----------

async def place(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    state = context.user_data.get(KEY)
    if not _ready(state):
        await query.answer()
        await ui.render(query, texts.CHECKOUT_EXPIRED, _back_to_cart_markup())
        context.user_data.pop(KEY, None)
        return ConversationHandler.END
    await query.answer()
    user = await users.ensure_user(update)
    tz = home.get_config(context).timezone
    try:
        order = await order_service.place_order(
            user_id=user["id"],
            dest={"lat": state.get("lat"), "lng": state.get("lng"), "text": state.get("text"), "maps_url": state.get("maps_url")},
            receiver={"name": state["receiver_name"], "phone": state["receiver_phone"]},
            tz=tz,
            expected_total=state["total"],
        )
    except OrderRefused as refusal:
        if refusal.reason == "price_changed":
            return await _show_confirm(update, context, user, notice=refusal.message)
        context.user_data.pop(KEY, None)
        await ui.render(query, refusal.message, _back_to_cart_markup())
        return ConversationHandler.END

    context.user_data.pop(KEY, None)
    items = await order_service.order_lines(order["id"])
    lines = []
    for item in items:
        line = "<b>{}</b> {} × {}".format(html.escape(item["meal_code"]), html.escape(item["meal_name"]), item["quantity"])
        if item["note"]:
            line += "\n   📝 " + html.escape(item["note"])
        lines.append(line)
    text = texts.ORDER_PLACED.format(
        code=html.escape(order["order_code"]), lines="\n".join(lines), total=order["total_etb"]
    )
    rows = [
        [Button("❌ Cancel this order", callback_data=f"co:cancel:{order['id']}")],
        [Button("📦 My orders", callback_data="orders"), Button("🏠 Home", callback_data="c:home")],
    ]
    await ui.render(query, text, InlineKeyboardMarkup(rows))
    return ConversationHandler.END


# ---------- cancelling an order (outside the conversation) ----------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, action, order_id_text = (query.data or "").split(":")
    order_id = int(order_id_text)
    user = await users.ensure_user(update)
    order = await db.fetch_one(
        "SELECT id, order_code, status FROM orders WHERE id = %s AND customer_id = %s", (order_id, user["id"])
    )
    if order is None:
        return
    to_orders = InlineKeyboardMarkup([[Button("📦 My orders", callback_data="orders")]])
    code = html.escape(order["order_code"])

    if order["status"] not in order_service.OPEN_STATUSES_FOR_CANCEL:
        text = texts.ORDER_CANCELLED.format(code=code) if order["status"] == "cancelled" else texts.CANNOT_CANCEL
        await ui.render(query, text, to_orders)
        return

    if action == "cancel":
        rows = [
            [Button("Yes, cancel it", callback_data=f"co:cancelyes:{order_id}")],
            [Button("Keep my order", callback_data="orders")],
        ]
        await ui.render(query, texts.CANCEL_ASK.format(code=code), InlineKeyboardMarkup(rows))
        return

    cancelled = await order_service.cancel_order(order_id, user["id"], update.effective_user.id)
    text = texts.ORDER_CANCELLED.format(code=code) if cancelled else texts.CANNOT_CANCEL
    await ui.render(query, text, to_orders)


# ---------- wiring ----------

def conversation() -> ConversationHandler:
    nav = [
        CallbackQueryHandler(back, pattern=r"^co:back:(dest|rcv|confirm)$"),
        CallbackQueryHandler(abort, pattern=r"^co:abort$"),
    ]
    text_filter = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(entry, pattern=r"^checkout$")],
        states={
            DEST: [
                CallbackQueryHandler(pick_saved, pattern=r"^co:addr:\d+$"),
                MessageHandler(filters.LOCATION, dest_location),
                MessageHandler(text_filter, dest_text),
                CallbackQueryHandler(abort, pattern=r"^co:abort$"),
            ],
            RECEIVER: [CallbackQueryHandler(receiver_choice, pattern=r"^co:rcv:(me|other)$"), *nav],
            RCV_NAME: [MessageHandler(text_filter, rcv_name), *nav],
            RCV_PHONE: [MessageHandler(text_filter, rcv_phone), *nav],
            CONFIRM: [
                CallbackQueryHandler(place, pattern=r"^co:place$"),
                CallbackQueryHandler(save_address, pattern=r"^co:save$"),
                *nav,
            ],
            LABEL: [MessageHandler(text_filter, label_text), *nav],
        },
        fallbacks=[CommandHandler("start", start_abort), CommandHandler("cancel", start_abort)],
        allow_reentry=True,
        conversation_timeout=900,  # forget a checkout that was left open for 15 minutes
    )
