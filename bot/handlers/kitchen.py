"""Kitchen console: payment review, delivery time, status buttons, recipes, refunds, dashboard, sold out."""
from __future__ import annotations

import html
import logging
from datetime import datetime

from telegram import InlineKeyboardButton as Button
from telegram import InlineKeyboardMarkup, LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, TelegramError
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .. import auth, db, texts
from ..services import flow, kitchen, location, notify, rules
from ..services import orders as order_service
from . import start as home

log = logging.getLogger("fitmeal.kitchen")

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
DEFAULT_REVIEW_MIN = 30
PATTERN = r"^k:(dash|meals|list:\w+|view:\d+|shot:\d+|rec:\d+|ok:\d+|okm:\d+:\d+|st:\d+:\w+|so:\d+)$"
TIME, REASON, RESEND, CX_REASON, RF_METHOD, RF_REF = range(6)
REFUND_METHODS = {"telebirr": "Telebirr", "bank": "Bank transfer", "cash": "Cash", "other": "Other"}


# ---------- helpers ----------

async def _is_staff(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return auth.is_staff(await home.get_role(update, context))


async def _review_min() -> int:
    return await db.get_setting_int("kitchen_review_min", DEFAULT_REVIEW_MIN)


async def _edit(query, text: str, markup: InlineKeyboardMarkup | None) -> None:
    try:
        await query.edit_message_text(
            text, parse_mode=ParseMode.HTML, reply_markup=markup, link_preview_options=NO_PREVIEW
        )
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise


async def _send(chat, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    await chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup, link_preview_options=NO_PREVIEW)


async def _tell_customer(context: ContextTypes.DEFAULT_TYPE, tg_user_id: int, text: str, order_id: int) -> bool:
    markup = InlineKeyboardMarkup([[Button("🔎 Track order", callback_data="track:" + str(order_id))]])
    return await notify.send_customer(context.bot, tg_user_id, text, markup)


async def _send_proof(bot, chat_id: int, file_id: str, caption: str | None = None) -> None:
    """Send the payment screenshot. It may have been uploaded as a photo or as an image file."""
    try:
        await bot.send_photo(chat_id, file_id, caption=caption, parse_mode=ParseMode.HTML)
    except BadRequest:
        await bot.send_document(chat_id, file_id, caption=caption, parse_mode=ParseMode.HTML)


# ---------- the order card (FR-K3, FR-K8) ----------

async def build_card(order_id: int, tz, notice: str | None = None) -> tuple[str, InlineKeyboardMarkup] | None:
    order = await kitchen.get_order(order_id)
    if order is None:
        return None
    items = await order_service.order_lines(order_id)
    status = order["status"]
    now = datetime.now(tz)

    lines = []
    if notice:
        lines += [notice, ""]
    lines.append("📦 <b>{}</b> · {}".format(html.escape(order["order_code"]), texts.STATUS_LABELS.get(status, status)))
    if status == "payment_review" and order["review_started_at"]:
        waited = (now - order["review_started_at"]).total_seconds() / 60
        if waited >= await _review_min():
            lines.append(texts.CARD_OVERDUE.format(minutes=int(waited)))
    lines.append("👤 {} · {}".format(html.escape(order["full_name"] or "?"), html.escape(order["phone"] or "?")))
    when = "🕒 Placed " + rules.clock(order["created_at"], tz)
    if order["delivery_time"]:
        when += " · Delivery time: <b>" + rules.clock(order["delivery_time"], tz) + "</b>"
    lines += [when, ""]

    for item in items:  # meal code and order ID on every card so nothing gets mixed up (FR-K8)
        line = "<b>{}</b> {} × {}".format(html.escape(item["meal_code"]), html.escape(item["meal_name"]), item["quantity"])
        if item["note"]:
            line += "\n   📝 " + html.escape(item["note"])
        lines.append(line)
    lines.append("")
    lines.append(
        "Subtotal {} · Delivery {} · <b>Total {} ETB</b>".format(
            order["subtotal_etb"], order["delivery_fee_etb"], order["total_etb"]
        )
    )

    where = html.escape(order["dest_text"]) if order["dest_text"] else "Map pin"
    lines.append("📍 " + where)
    maps = order["dest_maps_url"]
    if not maps and order["dest_latitude"] is not None:
        maps = location.maps_url(order["dest_latitude"], order["dest_longitude"])
    if maps:
        lines.append('🗺 <a href="' + html.escape(maps, quote=True) + '">Open in Maps</a>')
    lines.append(
        "🙋 Receiver: {} · {}".format(html.escape(order["receiver_name"] or "?"), html.escape(order["receiver_phone"] or "?"))
    )
    if order["cancel_reason"] and status in ("refund_needed", "refunded"):
        lines.append("Reason: " + html.escape(order["cancel_reason"]))

    id_text = str(order_id)
    rows = []
    if status == "payment_review":
        rows.append([Button("✅ Approve", callback_data="k:ok:" + id_text), Button("❌ Deny", callback_data="k:no:" + id_text)])
        rows.append([Button("📸 Screenshot", callback_data="k:shot:" + id_text)])
    nxt = flow.next_status(status)
    if nxt:
        label = {"preparing": "👨‍🍳 Preparing", "ready": "✅ Ready", "out_for_delivery": "🛵 Out for delivery", "delivered": "📦 Delivered"}[nxt]
        rows.append([Button(label, callback_data="k:st:" + id_text + ":" + nxt)])
    if status in ("payment_review", "confirmed", "preparing", "ready", "out_for_delivery"):
        rows.append([Button("📖 Show recipe", callback_data="k:rec:" + id_text)])
    if status in flow.CANCELLABLE_BY_KITCHEN:
        rows.append([Button("❌ Cancel and refund", callback_data="k:cx:" + id_text)])
    if status == "refund_needed":
        rows.append([Button("💸 Mark refunded", callback_data="k:rf:" + id_text)])
    rows.append([Button("⬅️ Dashboard", callback_data="k:dash")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def _show_card(query, context, order_id: int, notice: str | None = None) -> None:
    card = await build_card(order_id, home.get_config(context).timezone, notice)
    if card is None:
        await _edit(query, "Order not found.", InlineKeyboardMarkup([[Button("⬅️ Dashboard", callback_data="k:dash")]]))
        return
    await _edit(query, card[0], card[1])


async def _send_card(chat, context, order_id: int, notice: str | None = None) -> None:
    card = await build_card(order_id, home.get_config(context).timezone, notice)
    if card is not None:
        await _send(chat, card[0], card[1])


async def alert_new_payment(context: ContextTypes.DEFAULT_TYPE, order_id: int, file_id: str) -> None:
    """A customer sent a screenshot: staff get the picture, then the full order card with buttons."""
    cfg = home.get_config(context)
    order = await kitchen.get_order(order_id)
    card = await build_card(order_id, cfg.timezone)
    if order is None or card is None:
        return
    caption = texts.STAFF_SHOT_CAPTION.format(
        code=html.escape(order["order_code"]), total=order["total_etb"], name=html.escape(order["full_name"] or "?")
    )
    for chat_id in await notify.staff_ids(cfg):
        try:
            await _send_proof(context.bot, chat_id, file_id, caption)
            await context.bot.send_message(
                chat_id, card[0], parse_mode=ParseMode.HTML, reply_markup=card[1], link_preview_options=NO_PREVIEW
            )
        except TelegramError as exc:
            log.warning("Could not alert staff %s: %s", chat_id, exc)


# ---------- dashboard, lists, sold out ----------

async def _dashboard(query, context) -> None:
    counts = await kitchen.queue_counts(await _review_min())
    text = texts.DASH_HEADER + texts.DASH_BODY.format(**counts)
    rows = [
        [Button("💳 Review ({})".format(counts["review"]), callback_data="k:list:review"),
         Button("🚨 Overdue ({})".format(counts["overdue"]), callback_data="k:list:overdue")],
        [Button("🍳 Cook ({})".format(counts["cook"]), callback_data="k:list:cook"),
         Button("🛵 Delivery ({})".format(counts["delivery"]), callback_data="k:list:delivery")],
        [Button("💸 Refunds ({})".format(counts["refunds"]), callback_data="k:list:refunds")],
        [Button("🔄 Refresh", callback_data="k:dash"), Button("⬅️ Menu", callback_data="home")],
    ]
    await _edit(query, text, InlineKeyboardMarkup(rows))


async def _list(query, context, queue: str) -> None:
    tz = home.get_config(context).timezone
    orders = await kitchen.queue_list(queue, await _review_min())
    lines = ["<b>" + texts.QUEUE_TITLES[queue] + "</b>\n"]
    rows = []
    for o in orders:
        label = "{} · {} ETB · {}".format(o["order_code"], o["total_etb"], (o["full_name"] or "?")[:18])
        if o["delivery_time"]:
            label += " · " + rules.clock(o["delivery_time"], tz)
        rows.append([Button(label, callback_data="k:view:" + str(o["id"]))])
    if not orders:
        lines.append(texts.QUEUE_EMPTY)
    rows.append([Button("⬅️ Dashboard", callback_data="k:dash")])
    await _edit(query, "\n".join(lines), InlineKeyboardMarkup(rows))


async def _meals(query, context) -> None:
    today = datetime.now(home.get_config(context).timezone).date()
    rows = []
    for m in await kitchen.meals_for_toggle():
        mark = "❌ Sold out" if m["sold_out_on"] == today else "✅ On sale"
        rows.append([Button("{} · {} {}".format(mark, m["meal_code"], m["name"]), callback_data="k:so:" + str(m["id"]))])
    rows.append([Button("⬅️ Menu", callback_data="home")])
    await _edit(query, texts.MEALS_HEADER, InlineKeyboardMarkup(rows))


# ---------- button dispatcher ----------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not await _is_staff(update, context):
        await query.answer(texts.STAFF_ONLY, show_alert=True)
        return
    parts = (query.data or "").split(":")
    action = parts[1]
    staff_id = update.effective_user.id
    tz = home.get_config(context).timezone

    if action == "dash":
        await query.answer()
        await _dashboard(query, context)
    elif action == "list":
        await query.answer()
        if parts[2] in kitchen.QUEUE_NAMES:
            await _list(query, context, parts[2])
    elif action == "meals":
        await query.answer()
        await _meals(query, context)
    elif action == "so":
        await query.answer()
        await kitchen.toggle_sold_out(int(parts[2]), datetime.now(tz).date())
        await _meals(query, context)
    elif action == "view":
        await query.answer()
        await _show_card(query, context, int(parts[2]))
    elif action == "shot":
        await query.answer()
        payment = await kitchen.latest_payment(int(parts[2]))
        if payment is None:
            await query.message.chat.send_message(texts.NO_SCREENSHOT)
        else:
            await _send_proof(context.bot, query.message.chat_id, payment["telegram_file_id"])
    elif action == "rec":
        await query.answer()
        order_id = int(parts[2])
        order = await kitchen.get_order(order_id)
        if order is None:
            return
        blocks = [texts.RECIPE_HEADER.format(code=html.escape(order["order_code"]))]
        for r in await kitchen.recipes_for(order_id):
            blocks.append("<b>{}</b> {}\n{}\n".format(
                html.escape(r["meal_code"]), html.escape(r["meal_name"]), html.escape(r["recipe"] or texts.NO_RECIPE)
            ))
        await _send(query.message.chat, "\n".join(blocks))
    elif action == "ok":
        order_id = int(parts[2])
        order = await kitchen.get_order(order_id)
        if order is None or order["status"] != "payment_review":
            await query.answer(texts.ALREADY_HANDLED, show_alert=True)  # a callback can be answered only once
            await _show_card(query, context, order_id)
            return
        await query.answer()
        now = datetime.now(tz)
        rows = [[Button("+{} min · {}".format(m, rules.clock(flow.in_minutes(now, m), tz)), callback_data="k:okm:{}:{}".format(order_id, m))
                 for m in flow.QUICK_MINUTES]]
        rows.append([Button("⌨️ Type a time", callback_data="k:okt:" + str(order_id))])
        rows.append([Button("⬅️ Back", callback_data="k:view:" + str(order_id))])
        await _edit(query, texts.ASK_APPROVE_TIME.format(code=html.escape(order["order_code"])), InlineKeyboardMarkup(rows))
    elif action == "okm":
        order_id, minutes = int(parts[2]), int(parts[3])
        if minutes not in flow.QUICK_MINUTES:
            await query.answer()
            return
        ok, reached = await _approve(context, order_id, staff_id, flow.in_minutes(datetime.now(tz), minutes))
        await _after_action(query, context, order_id, ok, reached)
    elif action == "st":
        order_id, new_status = int(parts[2]), parts[3]
        if flow.previous_status(new_status) is None:
            await query.answer()
            return
        ok = await kitchen.advance(order_id, staff_id, new_status)
        reached = True
        if ok:
            order = await kitchen.get_order(order_id)
            reached = await _tell_customer(
                context, order["tg_user_id"], texts.CUST_STATUS[new_status].format(code=html.escape(order["order_code"])), order_id
            )
        await _after_action(query, context, order_id, ok, reached)


async def _after_action(query, context, order_id: int, ok: bool, reached: bool) -> None:
    if not ok:
        await query.answer(texts.ALREADY_HANDLED, show_alert=True)
        await _show_card(query, context, order_id)
        return
    await query.answer()
    notice = None
    if not reached:
        order = await kitchen.get_order(order_id)
        notice = texts.CUSTOMER_UNREACHED.format(phone=html.escape(order["phone"] or "?"))
    await _show_card(query, context, order_id, notice)


async def _approve(context, order_id: int, staff_id: int, when: datetime) -> tuple[bool, bool]:
    if not await kitchen.approve(order_id, staff_id, when):
        return False, False
    order = await kitchen.get_order(order_id)
    tz = home.get_config(context).timezone
    text = texts.CUST_APPROVED.format(code=html.escape(order["order_code"]), time=rules.clock(when, tz))
    return True, await _tell_customer(context, order["tg_user_id"], text, order_id)


# ---------- conversations: typing a time, a reason, a refund note ----------

def _cancel_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[Button(texts.STAFF_CANCEL_BTN, callback_data="k:abort")]])


async def _entry_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Returns the order ID from the button, or None if the user is not staff."""
    query = update.callback_query
    if not await _is_staff(update, context):
        await query.answer(texts.STAFF_ONLY, show_alert=True)
        return None
    await query.answer()
    order_id = int(query.data.split(":")[2])
    context.user_data["k_order"] = order_id
    return order_id


async def entry_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await _entry_guard(update, context) is None:
        return ConversationHandler.END
    await _send(update.effective_chat, texts.ASK_TYPED_TIME, _cancel_markup())
    return TIME


async def got_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tz = home.get_config(context).timezone
    when = flow.parse_delivery_time(update.message.text, datetime.now(tz))
    if when is None:
        await update.message.reply_text(texts.ERR_TIME)
        return TIME
    order_id = context.user_data.pop("k_order", None)
    if order_id is None:
        return ConversationHandler.END
    ok, reached = await _approve(context, order_id, update.effective_user.id, when)
    await _finish_text(update, context, order_id, ok, reached)
    return ConversationHandler.END


async def entry_deny(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await _entry_guard(update, context) is None:
        return ConversationHandler.END
    await _send(update.effective_chat, texts.ASK_DENY_REASON, _cancel_markup())
    return REASON


async def got_deny_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reason = (update.message.text or "").strip()
    if not 3 <= len(reason) <= 200:
        await update.message.reply_text(texts.ERR_REASON)
        return REASON
    context.user_data["k_reason"] = reason
    order_id = context.user_data.get("k_order")
    rows = [
        [Button("🔁 Allow a new screenshot", callback_data="k:nr:{}:1".format(order_id))],
        [Button("🚫 Final denial", callback_data="k:nr:{}:0".format(order_id))],
        [Button(texts.STAFF_CANCEL_BTN, callback_data="k:abort")],
    ]
    await _send(update.effective_chat, texts.ASK_RESEND, InlineKeyboardMarkup(rows))
    return RESEND


async def got_resend_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, _, order_id_text, flag = query.data.split(":")
    order_id, allow = int(order_id_text), flag == "1"
    reason = context.user_data.pop("k_reason", None)
    context.user_data.pop("k_order", None)
    if not reason:
        return ConversationHandler.END
    ok = await kitchen.deny(order_id, update.effective_user.id, reason, allow)
    reached = True
    if ok:
        order = await kitchen.get_order(order_id)
        text = texts.CUST_DENIED.format(
            code=html.escape(order["order_code"]),
            reason=html.escape(reason),
            next_step=texts.DENIED_RESEND if allow else texts.DENIED_FINAL,
        )
        reached = await _tell_customer(context, order["tg_user_id"], text, order_id)
    await _finish_text(update, context, order_id, ok, reached)
    return ConversationHandler.END


async def entry_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if await _entry_guard(update, context) is None:
        return ConversationHandler.END
    await _send(update.effective_chat, texts.ASK_CANCEL_REASON, _cancel_markup())
    return CX_REASON


async def got_cancel_reason(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reason = (update.message.text or "").strip()
    if not 3 <= len(reason) <= 200:
        await update.message.reply_text(texts.ERR_REASON)
        return CX_REASON
    order_id = context.user_data.pop("k_order", None)
    if order_id is None:
        return ConversationHandler.END
    ok = await kitchen.cancel_for_refund(order_id, update.effective_user.id, reason)
    reached = True
    if ok:
        order = await kitchen.get_order(order_id)
        text = texts.CUST_KITCHEN_CANCELLED.format(
            code=html.escape(order["order_code"]), reason=html.escape(reason), total=order["total_etb"]
        )
        reached = await _tell_customer(context, order["tg_user_id"], text, order_id)
    await _finish_text(update, context, order_id, ok, reached)
    return ConversationHandler.END


async def entry_refund(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    order_id = await _entry_guard(update, context)
    if order_id is None:
        return ConversationHandler.END
    rows = [[Button(label, callback_data="k:rfm:{}:{}".format(order_id, key))] for key, label in REFUND_METHODS.items()]
    rows.append([Button(texts.STAFF_CANCEL_BTN, callback_data="k:abort")])
    await _send(update.effective_chat, texts.ASK_REFUND_METHOD, InlineKeyboardMarkup(rows))
    return RF_METHOD


async def got_refund_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    key = query.data.split(":")[3]
    if key not in REFUND_METHODS:
        return RF_METHOD
    context.user_data["k_method"] = REFUND_METHODS[key]
    await _send(update.effective_chat, texts.ASK_REFUND_REF, _cancel_markup())
    return RF_REF


async def got_refund_ref(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    reference = None if text in ("-", "") else text[:100]
    order_id = context.user_data.pop("k_order", None)
    method = context.user_data.pop("k_method", "Other")
    if order_id is None:
        return ConversationHandler.END
    result = await kitchen.mark_refunded(order_id, update.effective_user.id, method, reference)
    reached = True
    if result is not None:
        order = await kitchen.get_order(order_id)
        message = texts.CUST_REFUNDED.format(
            code=html.escape(order["order_code"]),
            total=result["total"],
            method=html.escape(method),
            reference=(" (ref " + html.escape(reference) + ")") if reference else "",
        )
        reached = await _tell_customer(context, order["tg_user_id"], message, order_id)
    await _finish_text(update, context, order_id, result is not None, reached)
    return ConversationHandler.END


async def _finish_text(update, context, order_id: int, ok: bool, reached: bool) -> None:
    """After a typed step: tell the staff member what happened and show the order card again."""
    chat = update.effective_chat
    if not ok:
        await chat.send_message(texts.ALREADY_HANDLED)
        await _send_card(chat, context, order_id)
        return
    notice = None
    if not reached:
        order = await kitchen.get_order(order_id)
        notice = texts.CUSTOMER_UNREACHED.format(phone=html.escape(order["phone"] or "?"))
    await _send_card(chat, context, order_id, notice)


def _clear(context) -> None:
    for key in ("k_order", "k_reason", "k_method"):
        context.user_data.pop(key, None)


async def abort(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    _clear(context)
    await update.effective_chat.send_message(texts.KITCHEN_CANCELLED)
    return ConversationHandler.END


async def abort_to_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear(context)
    role = await home.get_role(update, context)
    text, markup = home.home_for(role)
    await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    return ConversationHandler.END


def conversation() -> ConversationHandler:
    text_only = filters.TEXT & ~filters.COMMAND
    cancel = CallbackQueryHandler(abort, pattern=r"^k:abort$")
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(entry_time, pattern=r"^k:okt:\d+$"),
            CallbackQueryHandler(entry_deny, pattern=r"^k:no:\d+$"),
            CallbackQueryHandler(entry_cancel, pattern=r"^k:cx:\d+$"),
            CallbackQueryHandler(entry_refund, pattern=r"^k:rf:\d+$"),
        ],
        states={
            TIME: [MessageHandler(text_only, got_time), cancel],
            REASON: [MessageHandler(text_only, got_deny_reason), cancel],
            RESEND: [CallbackQueryHandler(got_resend_choice, pattern=r"^k:nr:\d+:[01]$"), cancel],
            CX_REASON: [MessageHandler(text_only, got_cancel_reason), cancel],
            RF_METHOD: [CallbackQueryHandler(got_refund_method, pattern=r"^k:rfm:\d+:\w+$"), cancel],
            RF_REF: [MessageHandler(text_only, got_refund_ref), cancel],
        },
        fallbacks=[CommandHandler("cancel", abort), CommandHandler("start", abort_to_home)],
        allow_reentry=True,
    )
