"""Payment instructions, screenshot upload, order tracking, refund requests and the timer job."""
from __future__ import annotations

import html
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton as Button
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from .. import db, texts, ui
from ..services import notify, payments, rules, users
from ..services import orders as order_service
from . import start as home

log = logging.getLogger("fitmeal.payment")

PATTERN = r"^(track:\d+|pay:(show|pick|refund):\d+)$"

DEFAULT_REVIEW_MIN = 30
DEFAULT_REPEAT_MIN = 10
TICK_SECONDS = 15


# ---------- text builders ----------

async def payment_block(total: int, deadline: datetime, tz: ZoneInfo) -> str:
    """Order ID is shown by the caller. This is the 'how to pay' part (FR-P1)."""
    accounts = await payments.accounts()
    if not accounts:
        return texts.PAYMENT_NO_ACCOUNTS
    lines = [
        "<b>{}</b>: <code>{}</code>\n   {}".format(
            html.escape(a["label"]), html.escape(a["account_number"]), html.escape(a["holder_name"])
        )
        for a in accounts
    ]
    window = await db.get_setting_int("payment_window_min", 10)
    return texts.PAYMENT_BLOCK.format(
        total=total, accounts="\n".join(lines), deadline=rules.clock(deadline, tz), minutes=window
    )


def _payment_line(order: dict, tz: ZoneInfo) -> str:
    status, pay = order["status"], order["pay_status"]
    if status == "expired":
        return "Expired (no screenshot in time)"
    if status in ("refund_needed", "refunded"):
        return "Refund pending" if status == "refund_needed" else "Refunded"
    if pay == "approved":
        return "Confirmed ✅"
    if pay == "pending":
        return "Screenshot received, under review"
    if pay == "denied":
        line = "Denied" + (": " + html.escape(order["pay_reason"]) if order["pay_reason"] else "")
        return line + ("\n   You can send a new screenshot here." if order["allow_resend"] else "")
    if status == "awaiting_payment" and order["payment_deadline_at"]:
        return "Not paid yet. Send your screenshot before " + rules.clock(order["payment_deadline_at"], tz)
    return "Not paid"


async def _track_screen(order: dict, tz: ZoneInfo, review_min: int) -> tuple[str, InlineKeyboardMarkup]:
    items = await order_service.order_lines(order["id"])
    lines = [texts.TRACK_HEADER.format(code=html.escape(order["order_code"]))]
    lines.append("Status: <b>" + texts.STATUS_LABELS.get(order["status"], order["status"]) + "</b>")
    lines.append("Payment: " + _payment_line(order, tz))
    lines.append(
        "Delivery time: "
        + (rules.clock(order["delivery_time"], tz) if order["delivery_time"] else "not set yet (the kitchen sets it when your payment is confirmed)")
    )
    lines.append("")
    for item in items:
        line = "<b>{}</b> {} × {}".format(html.escape(item["meal_code"]), html.escape(item["meal_name"]), item["quantity"])
        if item["note"]:
            line += "\n   📝 " + html.escape(item["note"])
        lines.append(line)
    lines.append("")
    lines.append(f"Subtotal: {order['subtotal_etb']} ETB · Delivery: {order['delivery_fee_etb']} ETB")
    lines.append(f"<b>Total: {order['total_etb']} ETB</b>")
    dest = []
    if order["dest_text"]:
        dest.append(html.escape(order["dest_text"]))
    if order["dest_latitude"] is not None:
        dest.append("📍 pinned location")
    lines.append("Delivery to: " + " · ".join(dest))

    now = datetime.now(tz)
    rows = []
    status = order["status"]
    if status == "awaiting_payment" and order["payment_deadline_at"] and order["payment_deadline_at"] > now:
        rows.append([Button("💳 How to pay", callback_data=f"pay:show:{order['id']}")])
    if status == "payment_review" and order["review_started_at"]:
        waited = (now - order["review_started_at"]).total_seconds() / 60
        if waited >= review_min:
            rows.append([Button("💸 Request refund", callback_data=f"pay:refund:{order['id']}")])
    if status in order_service.OPEN_STATUSES_FOR_CANCEL:
        rows.append([Button("❌ Cancel order", callback_data=f"co:cancel:{order['id']}")])
    rows.append([Button("⬅️ My orders", callback_data="orders")])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


# ---------- customer actions ----------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""
    user = await users.ensure_user(update)
    tz = home.get_config(context).timezone
    parts = data.split(":")
    order_id = int(parts[-1])
    review_min = await db.get_setting_int("kitchen_review_min", DEFAULT_REVIEW_MIN)

    if parts[0] == "pay" and parts[1] == "pick":
        await query.answer()
        file_id = context.user_data.pop("pending_shot", None)
        if not file_id:
            await ui.render(query, texts.SHOT_LOST, InlineKeyboardMarkup([[Button("📦 My orders", callback_data="orders")]]))
            return
        await _submit(update, context, user, order_id, file_id, query)
        return

    order = await payments.order_view(order_id, user["id"])
    if order is None:
        await query.answer()
        return

    if parts[0] == "pay" and parts[1] == "refund":
        refund = await payments.request_refund(order_id, user["id"], update.effective_user.id, review_min)
        if refund is None:
            if order["status"] in ("refund_needed", "refunded"):
                await query.answer(texts.REFUND_ALREADY, show_alert=True)
            else:
                await query.answer(texts.REFUND_TOO_EARLY, show_alert=True)
            return
        code = html.escape(refund["order_code"])
        await notify.send_staff(
            context.bot,
            home.get_config(context),
            texts.STAFF_REFUND.format(
                code=code,
                total=refund["total_etb"],
                name=html.escape(user["full_name"] or "?"),
                phone=html.escape(user["phone"] or "?"),
                reason="customer asked for a refund because the review was overdue",
            ),
        )
        try:
            await query.answer()
            await ui.render(
                query,
                texts.REFUND_REQUESTED.format(code=code),
                InlineKeyboardMarkup([[Button("📦 My orders", callback_data="orders")]]),
            )
        except TelegramError as exc:
            log.warning("Could not confirm the refund request to the customer: %s", exc)
        return
        

    await query.answer()
    if parts[0] == "pay" and parts[1] == "show":
        deadline = order["payment_deadline_at"]
        if order["status"] != "awaiting_payment" or deadline is None or deadline <= datetime.now(tz):
            await ui.render(query, texts.SHOT_TOO_LATE, InlineKeyboardMarkup([[Button("📦 My orders", callback_data="orders")]]))
            return
        text = "<b>Order {}</b>\n\n".format(html.escape(order["order_code"])) + await payment_block(order["total_etb"], deadline, tz)
        rows = [[Button("⬅️ Back", callback_data=f"track:{order_id}")]]
        await ui.render(query, text, InlineKeyboardMarkup(rows))
        return

    text, markup = await _track_screen(order, tz, review_min)
    await ui.render(query, text, markup)


async def on_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """A photo (or image file) from the customer: treat it as a payment screenshot (FR-P2)."""
    msg = update.message
    file_id = msg.photo[-1].file_id if msg.photo else msg.document.file_id
    user = await users.ensure_user(update)
    options = await payments.candidates(user["id"])

    if not options:
        reply = texts.SHOT_ALREADY if await payments.has_in_review(user["id"]) else texts.SHOT_NO_ORDER
        await msg.reply_text(reply, parse_mode="HTML")
        return
    if len(options) == 1:
        await _submit(update, context, user, options[0]["id"], file_id, None)
        return
    context.user_data["pending_shot"] = file_id
    rows = [
        [Button(f"{o['order_code']} · {o['total_etb']} ETB", callback_data=f"pay:pick:{o['id']}")] for o in options
    ]
    await msg.reply_text(texts.SHOT_PICK, reply_markup=InlineKeyboardMarkup(rows))


async def _submit(update, context, user: dict, order_id: int, file_id: str, query) -> None:
    order = await payments.submit_screenshot(order_id, user["id"], file_id)
    if order is None:
        if query is not None:
            await ui.render(query, texts.SHOT_TOO_LATE, InlineKeyboardMarkup([[Button("📦 My orders", callback_data="orders")]]))
        else:
            await update.message.reply_text(texts.SHOT_TOO_LATE)
        return
    code = html.escape(order["order_code"])
    markup = InlineKeyboardMarkup([[Button("🔎 Track order", callback_data=f"track:{order_id}")]])
    if query is not None:
        await ui.render(query, texts.SHOT_RECEIVED.format(code=code), markup)
    else:
        await update.effective_chat.send_message(texts.SHOT_RECEIVED.format(code=code), parse_mode="HTML", reply_markup=markup)
    # Staff get the screenshot itself (Phase 5 adds Approve / Deny buttons to this message).
    await notify.send_staff(
        context.bot,
        home.get_config(context),
        texts.STAFF_NEW_SHOT.format(
            code=code,
            total=order["total_etb"],
            name=html.escape(order["full_name"] or "?"),
            phone=html.escape(order["phone"] or "?"),
        ),
        photo=file_id,
    )


# ---------- timers ----------

async def tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs every few seconds. Expires unpaid orders and sends kitchen reminders and overdue alerts."""
    try:
        await _expire(context)
        await _review_alerts(context)
    except Exception:  # a database hiccup must not stop the timer job for good
        log.exception("Payment timer tick failed")


async def _expire(context: ContextTypes.DEFAULT_TYPE) -> None:
    for row in await payments.expire_due():
        markup = InlineKeyboardMarkup([[Button("🏠 Main menu", callback_data="c:home")]])
        await notify.send_customer(
            context.bot, row["tg_user_id"], texts.EXPIRED_MSG.format(code=html.escape(row["order_code"])), markup
        )


async def _review_alerts(context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = home.get_config(context)
    review_min = await db.get_setting_int("kitchen_review_min", DEFAULT_REVIEW_MIN)
    repeat_min = max(1, await db.get_setting_int("alert_repeat_min", DEFAULT_REPEAT_MIN))
    for row in await payments.claim_due_alerts(repeat_min):
        elapsed = float(row["elapsed_min"])
        kind = rules.alert_kind(elapsed, review_min)
        template = texts.STAFF_OVERDUE if kind == "overdue" else texts.STAFF_REMINDER
        delivered = await notify.send_staff(
            context.bot,
            cfg,
            template.format(
                code=html.escape(row["order_code"]),
                total=row["total_etb"],
                name=html.escape(row["full_name"] or "?"),
                phone=html.escape(row["phone"] or "?"),
                minutes=int(elapsed),
            ),
        )
        if delivered == 0:
            await payments.release_alert(row["id"])  # nobody got it (network?): try again next tick
            continue
        if kind == "overdue" and not row["already_overdue"]:
            markup = InlineKeyboardMarkup([[Button("💸 Request refund", callback_data=f"pay:refund:{row['id']}")]])
            told = await notify.send_customer(
                context.bot, row["tg_user_id"], texts.CUSTOMER_OVERDUE.format(code=html.escape(row["order_code"])), markup
            )
            if told:  # only record it once the customer really got it; otherwise the next alert retries
                await payments.mark_overdue(row["id"])
