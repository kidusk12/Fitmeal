"""Owner tools: settings, staff, payment accounts, meal editor, broadcasts, reports (SRS FR-A1 to FR-A5).

Every button re-checks that the person is an owner (FR-K1 style). Screens are opened with plain
buttons (on_callback); anything that needs typing runs inside one conversation (conversation()).
"""
from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton as Button
from telegram import InlineKeyboardMarkup, LinkPreviewOptions, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .. import texts
from ..services import admin, notify, owner_rules
from . import start as home

log = logging.getLogger("fitmeal.owner")

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
PATTERN = (
    r"^o:(set|staff|sr:\d+|sry:\d+|acct|av:\d+|at:\d+|ad:\d+|ady:\d+|ml:\d+|mv:\d+|mh:\d+|rep|rp:\w+)$"
)
INPUT = 0
CONVERSATION_TIMEOUT = 900  # seconds; a forgotten half-typed form closes by itself

SETTING_DEFAULTS = {
    "delivery_fee_etb": "50",
    "daily_order_limit": "100",
    "opening_time": "08:00",
    "closing_time": "21:00",
    "payment_window_min": "10",
    "kitchen_review_min": "30",
    "alert_repeat_min": "10",
}
ACCOUNT_FIELDS = {"label": ("label", "name"), "number": ("account_number", "account number"), "holder": ("holder_name", "holder name")}
MEAL_EDIT_FIELDS = ("name", "category", "price", "macros", "description", "recipe", "photo", "ingredients")
ADD_ORDER = ["name", "category", "price", "macros", "description", "recipe", "photo", "ingredients", "confirm"]
ALLERGEN_LABELS = {"none": "None", "dairy": "Dairy", "egg": "Egg", "peanut": "Peanut", "gluten": "Gluten"}
BROADCAST_PAUSE = 0.05  # seconds between messages, well inside Telegram's limits


# ---------- helpers ----------

async def _is_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return await home.get_role(update, context) == "owner"


async def _edit(query, text: str, markup: InlineKeyboardMarkup | None) -> None:
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup, link_preview_options=NO_PREVIEW)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise


async def _send(chat, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    await chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup, link_preview_options=NO_PREVIEW)


def _esc(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def _num(value) -> str:
    return f"{value:g}"


def _menu_row() -> list[Button]:
    return [Button(texts.OWNER_MENU_BTN, callback_data="home")]


def _cancel_row() -> list[Button]:
    return [Button(texts.OWNER_CANCEL_BTN, callback_data="o:abort")]


def _today(context) -> datetime:
    return datetime.now(home.get_config(context).timezone)


# ---------- screens (each returns text and buttons) ----------

async def settings_screen() -> tuple[str, InlineKeyboardMarkup]:
    s = {**SETTING_DEFAULTS, **await admin.all_settings()}
    opens = owner_rules.parse_time(s["opening_time"]) or SETTING_DEFAULTS["opening_time"]
    closes = owner_rules.parse_time(s["closing_time"]) or SETTING_DEFAULTS["closing_time"]
    text = texts.SETTINGS_SCREEN.format(
        fee=_esc(s["delivery_fee_etb"]), limit=_esc(s["daily_order_limit"]), opens=opens, closes=closes,
        window=_esc(s["payment_window_min"]), review=_esc(s["kitchen_review_min"]), repeat=_esc(s["alert_repeat_min"]),
    )
    rows = [
        [Button("🚚 Delivery fee", callback_data="o:ss:delivery_fee_etb"), Button("📦 Daily limit", callback_data="o:ss:daily_order_limit")],
        [Button("🕗 Opening time", callback_data="o:ss:opening_time"), Button("🕘 Closing time", callback_data="o:ss:closing_time")],
        [Button("⏱ Payment window", callback_data="o:ss:payment_window_min"), Button("🔎 Review window", callback_data="o:ss:kitchen_review_min")],
        [Button("🔔 Alert repeat", callback_data="o:ss:alert_repeat_min")],
        _menu_row(),
    ]
    return text, InlineKeyboardMarkup(rows)


async def staff_screen() -> tuple[str, InlineKeyboardMarkup]:
    lines: list[str] = []
    rows = [[Button("➕ Add kitchen staff", callback_data="o:sa")]]
    for person in await admin.list_staff():
        if not person["is_active"]:
            continue
        icon = "👑" if person["role"] == "owner" else "👨‍🍳"
        lines.append(f"{icon} {_esc(person['name'])} · <code>{person['tg_user_id']}</code>")
        if person["role"] == "kitchen":
            rows.append([Button("🗑 Remove " + person["name"][:24], callback_data=f"o:sr:{person['tg_user_id']}")])
    rows.append(_menu_row())
    return texts.STAFF_SCREEN.format(people="\n".join(lines) or texts.STAFF_NONE), InlineKeyboardMarkup(rows)


async def accounts_screen() -> tuple[str, InlineKeyboardMarkup]:
    lines: list[str] = []
    rows = []
    for acc in await admin.list_accounts():
        mark = "✅" if acc["is_active"] else "🙈"
        lines.append(f"{mark} <b>{_esc(acc['label'])}</b> · {_esc(acc['account_number'])} · {_esc(acc['holder_name'])}")
        rows.append([Button(f"{mark} {acc['label'][:30]}", callback_data=f"o:av:{acc['id']}")])
    rows.append([Button("➕ Add account", callback_data="o:aa")])
    rows.append(_menu_row())
    return texts.ACCOUNTS_SCREEN.format(accounts="\n".join(lines) or texts.ACCOUNTS_NONE), InlineKeyboardMarkup(rows)


async def account_screen(account_id: int) -> tuple[str, InlineKeyboardMarkup] | None:
    acc = await admin.get_account(account_id)
    if acc is None:
        return None
    text = texts.ACCOUNT_VIEW.format(
        label=_esc(acc["label"]), number=_esc(acc["account_number"]), holder=_esc(acc["holder_name"]),
        status="✅ Visible to customers" if acc["is_active"] else "🙈 Hidden",
    )
    i = str(account_id)
    rows = [
        [Button("🙈 Hide" if acc["is_active"] else "✅ Show", callback_data="o:at:" + i)],
        [Button("✏️ Name", callback_data=f"o:ae:{i}:label"), Button("✏️ Number", callback_data=f"o:ae:{i}:number"),
         Button("✏️ Holder", callback_data=f"o:ae:{i}:holder")],
        [Button("🗑 Delete", callback_data="o:ad:" + i)],
        [Button("⬅️ Accounts", callback_data="o:acct")],
    ]
    return text, InlineKeyboardMarkup(rows)


def _meal_status(meal: dict, today) -> str:
    if not meal["is_active"]:
        return texts.MEAL_STATUS_HIDDEN
    if meal["sold_out_on"] == today:
        return texts.MEAL_STATUS_SOLD_OUT
    return texts.MEAL_STATUS_ON


async def meals_screen(page: int, today) -> tuple[str, InlineKeyboardMarkup]:
    total = await admin.count_meals()
    last_page = max(0, (total - 1) // admin.MEALS_PER_PAGE)
    page = min(max(page, 0), last_page)
    rows = []
    for m in await admin.list_meals(page):
        mark = "🙈 " if not m["is_active"] else ("❌ " if m["sold_out_on"] == today else "")
        rows.append([Button(f"{mark}{m['meal_code']} {m['name'][:26]} · {m['price_etb']}", callback_data=f"o:mv:{m['id']}")])
    nav = []
    if page > 0:
        nav.append(Button("◀️ Previous", callback_data=f"o:ml:{page - 1}"))
    if page < last_page:
        nav.append(Button("Next ▶️", callback_data=f"o:ml:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([Button("➕ Add meal", callback_data="o:ma")])
    rows.append(_menu_row())
    return texts.MEALS_SCREEN.format(total=total), InlineKeyboardMarkup(rows)


def _ingredient_line(i: dict) -> str:
    line = f"{_esc(i['name'])} {_num(i['quantity'])} {_esc(i['unit'])}"
    return line + (f" ⚠️ {_esc(i['allergen'])}" if i["allergen"] else "")


async def meal_screen(meal_id: int, today) -> tuple[str, InlineKeyboardMarkup] | None:
    meal = await admin.get_meal(meal_id)
    if meal is None:
        return None
    ings = await admin.meal_ingredients(meal_id)
    empty = texts.MEAL_EMPTY_FIELD
    text = texts.MEAL_VIEW.format(
        code=_esc(meal["meal_code"]), name=_esc(meal["name"]), category=_esc(meal["category"]), price=meal["price_etb"],
        calories=meal["calories"], protein=_num(meal["protein_g"]), carbs=_num(meal["carbs_g"]), fat=_num(meal["fat_g"]),
        status=_meal_status(meal, today), photo="yes 📷" if meal["photo_file_id"] else "none",
        ingredients="\n".join(_ingredient_line(i) for i in ings) or empty,
        description=_esc(meal["description"]) or empty, recipe=_esc(meal["recipe"]) or empty,
    )
    i = str(meal_id)
    rows = [
        [Button("✏️ Name", callback_data=f"o:me:{i}:name"), Button("🏷 Category", callback_data=f"o:me:{i}:category")],
        [Button("💰 Price", callback_data=f"o:me:{i}:price"), Button("🔢 Macros", callback_data=f"o:me:{i}:macros")],
        [Button("📝 Description", callback_data=f"o:me:{i}:description"), Button("📖 Recipe", callback_data=f"o:me:{i}:recipe")],
        [Button("📷 Photo", callback_data=f"o:me:{i}:photo"), Button("🥕 Ingredients", callback_data=f"o:me:{i}:ingredients")],
        [Button("✅ Show to customers" if not meal["is_active"] else "🙈 Hide from customers", callback_data="o:mh:" + i)],
        [Button("⬅️ Meals", callback_data="o:ml:0")],
    ]
    return text[:4000], InlineKeyboardMarkup(rows)


def _reports_menu() -> tuple[str, InlineKeyboardMarkup]:
    rows = [
        [Button("Today", callback_data="o:rp:today"), Button("Yesterday", callback_data="o:rp:yesterday")],
        [Button("Last 7 days", callback_data="o:rp:week")],
        _menu_row(),
    ]
    return texts.REPORTS_SCREEN, InlineKeyboardMarkup(rows)


async def report_screen(kind: str, tz) -> tuple[str, InlineKeyboardMarkup] | None:
    bounds = owner_rules.period_bounds(datetime.now(tz), kind)
    if bounds is None:
        return None
    start, end = bounds
    data = await admin.report(start, end)
    last_day = (end - timedelta(days=1)).strftime("%d %b %Y")
    first_day = start.strftime("%d %b %Y")
    dates = first_day if first_day == last_day else f"{start.strftime('%d %b')} to {last_day}"
    top = "\n".join(
        f"{n}. <b>{_esc(t['meal_code'])}</b> {_esc(t['meal_name'])} × {t['qty']}" for n, t in enumerate(data["top"], 1)
    ) or texts.REPORT_NO_MEALS
    text = texts.REPORT_BODY.format(
        title=owner_rules.PERIOD_LABELS[kind], dates=dates, placed=data["placed"], confirmed=data["confirmed"],
        delivered=data["delivered"], revenue=f"{data['revenue']:,}", food=f"{data['revenue'] - data['fees']:,}",
        fees=f"{data['fees']:,}", denied=data["denied"], refunded=data["refunded"],
        refunded_etb=f"{data['refunded_etb']:,}", refund_waiting=data["refund_waiting"],
        closed_unpaid=data["closed_unpaid"], customers=data["customers"], top=top,
    )
    rows = [
        [Button("Today", callback_data="o:rp:today"), Button("Yesterday", callback_data="o:rp:yesterday"),
         Button("7 days", callback_data="o:rp:week")],
        [Button("🔄 Refresh", callback_data="o:rp:" + kind)],
        _menu_row(),
    ]
    return text, InlineKeyboardMarkup(rows)


# ---------- plain buttons ----------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not await _is_owner(update, context):
        await query.answer(texts.OWNER_ONLY, show_alert=True)
        return
    parts = (query.data or "").split(":")
    action = parts[1]
    tz = home.get_config(context).timezone
    today = datetime.now(tz).date()

    if action == "set":
        await query.answer()
        await _edit(query, *await settings_screen())
    elif action == "staff":
        await query.answer()
        await _edit(query, *await staff_screen())
    elif action == "sr":
        person = await admin.get_staff(int(parts[2]))
        if person is None or person["role"] != "kitchen" or not person["is_active"]:
            await query.answer(texts.STAFF_REMOVE_FAILED, show_alert=True)
            return
        await query.answer()
        rows = [
            [Button("✅ Yes, remove", callback_data="o:sry:" + parts[2])],
            [Button("⬅️ No, keep", callback_data="o:staff")],
        ]
        await _edit(query, texts.STAFF_REMOVE_ASK.format(name=_esc(person["name"])), InlineKeyboardMarkup(rows))
    elif action == "sry":
        await query.answer()
        person = await admin.get_staff(int(parts[2]))
        removed = await admin.remove_staff(int(parts[2]))
        notice = texts.STAFF_REMOVED.format(name=_esc(person["name"])) if removed and person else texts.STAFF_REMOVE_FAILED
        text, markup = await staff_screen()
        await _edit(query, notice + "\n\n" + text, markup)
    elif action == "acct":
        await query.answer()
        await _edit(query, *await accounts_screen())
    elif action == "av":
        screen = await account_screen(int(parts[2]))
        if screen is None:
            await query.answer(texts.ACCT_GONE, show_alert=True)
            return
        await query.answer()
        await _edit(query, *screen)
    elif action == "at":
        result = await admin.toggle_account(int(parts[2]))
        if result == "last":
            await query.answer(texts.ACCT_LAST, show_alert=True)
            return
        await query.answer()
        screen = await account_screen(int(parts[2]))
        await _edit(query, *(screen or await accounts_screen()))
    elif action == "ad":
        screen = await account_screen(int(parts[2]))
        if screen is None:
            await query.answer(texts.ACCT_GONE, show_alert=True)
            return
        await query.answer()
        acc = await admin.get_account(int(parts[2]))
        rows = [
            [Button("✅ Yes, delete", callback_data="o:ady:" + parts[2])],
            [Button("⬅️ No, keep", callback_data="o:av:" + parts[2])],
        ]
        await _edit(query, texts.ACCT_DELETE_ASK.format(label=_esc(acc["label"])), InlineKeyboardMarkup(rows))
    elif action == "ady":
        result = await admin.delete_account(int(parts[2]))
        if result == "last":
            await query.answer(texts.ACCT_LAST, show_alert=True)
            return
        await query.answer()
        text, markup = await accounts_screen()
        notice = texts.ACCT_DELETED if result == "deleted" else texts.ACCT_GONE
        await _edit(query, notice + "\n\n" + text, markup)
    elif action == "ml":
        await query.answer()
        await _edit(query, *await meals_screen(int(parts[2]), today))
    elif action == "mv":
        screen = await meal_screen(int(parts[2]), today)
        if screen is None:
            await query.answer(texts.MEAL_GONE, show_alert=True)
            return
        await query.answer()
        await _edit(query, *screen)
    elif action == "mh":
        now_active = await admin.toggle_meal_active(int(parts[2]))
        if now_active is None:
            await query.answer(texts.MEAL_GONE, show_alert=True)
            return
        await query.answer(texts.MEAL_TOGGLED_SHOWN if now_active else texts.MEAL_TOGGLED_HIDDEN)
        screen = await meal_screen(int(parts[2]), today)
        await _edit(query, *screen)
    elif action == "rep":
        await query.answer()
        await _edit(query, *_reports_menu())
    elif action == "rp":
        screen = await report_screen(parts[2], tz)
        if screen is None:
            await query.answer()
            return
        await query.answer()
        await _edit(query, *screen)


# ---------- conversation: everything that needs typing ----------

def _flow(context) -> dict | None:
    return context.user_data.get("o_flow")


def _clear(context) -> None:
    context.user_data.pop("o_flow", None)


async def _begin(update: Update, context: ContextTypes.DEFAULT_TYPE, flow: dict) -> int:
    context.user_data["o_flow"] = flow
    await _ask(update.effective_chat, context)
    return INPUT


async def _guard_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Owner check for every entry button. Answers the tap either way."""
    query = update.callback_query
    if not await _is_owner(update, context):
        await query.answer(texts.OWNER_ONLY, show_alert=True)
        return False
    await query.answer()
    return True


async def entry_setting(update, context) -> int:
    if not await _guard_entry(update, context):
        return ConversationHandler.END
    key = update.callback_query.data.split(":")[2]
    if key not in owner_rules.SETTINGS:
        return ConversationHandler.END
    return await _begin(update, context, {"kind": "setting", "step": "setting_value", "data": {"key": key}})


async def entry_staff_add(update, context) -> int:
    if not await _guard_entry(update, context):
        return ConversationHandler.END
    return await _begin(update, context, {"kind": "staff_add", "step": "staff_id", "data": {}})


async def entry_acct_add(update, context) -> int:
    if not await _guard_entry(update, context):
        return ConversationHandler.END
    return await _begin(update, context, {"kind": "acct_add", "step": "acct_label", "data": {}})


async def entry_acct_edit(update, context) -> int:
    if not await _guard_entry(update, context):
        return ConversationHandler.END
    _, _, account_id, short = update.callback_query.data.split(":")
    acc = await admin.get_account(int(account_id))
    if acc is None or short not in ACCOUNT_FIELDS:
        await update.effective_chat.send_message(texts.ACCT_GONE)
        return ConversationHandler.END
    column, what = ACCOUNT_FIELDS[short]
    data = {"account_id": int(account_id), "column": column, "what": what, "current": acc[column]}
    return await _begin(update, context, {"kind": "acct_edit", "step": "acct_value", "data": data})


async def entry_meal_add(update, context) -> int:
    if not await _guard_entry(update, context):
        return ConversationHandler.END
    return await _begin(update, context, {"kind": "meal_add", "step": "name", "data": {}})


async def entry_meal_edit(update, context) -> int:
    if not await _guard_entry(update, context):
        return ConversationHandler.END
    _, _, meal_id, field = update.callback_query.data.split(":")
    if field not in MEAL_EDIT_FIELDS or await admin.get_meal(int(meal_id)) is None:
        await update.effective_chat.send_message(texts.MEAL_GONE)
        return ConversationHandler.END
    return await _begin(
        update, context, {"kind": "meal_edit", "step": field, "data": {"meal_id": int(meal_id), "field": field}}
    )


async def entry_broadcast(update, context) -> int:
    if not await _guard_entry(update, context):
        return ConversationHandler.END
    return await _begin(update, context, {"kind": "broadcast", "step": "bc_content", "data": {}})


async def _current_hint(flow: dict) -> str:
    """For edits: a line showing what the field holds now, so the owner can see what is being replaced."""
    if flow["kind"] != "meal_edit":
        return ""
    meal = await admin.get_meal(flow["data"]["meal_id"])
    if meal is None:
        return ""
    field = flow["data"]["field"]
    if field == "name":
        current = meal["name"]
    elif field == "price":
        current = f"{meal['price_etb']} ETB"
    elif field == "macros":
        current = f"{meal['calories']} {_num(meal['protein_g'])} {_num(meal['carbs_g'])} {_num(meal['fat_g'])}"
    elif field == "description":
        current = meal["description"] or texts.MEAL_EMPTY_FIELD
    elif field == "recipe":
        current = meal["recipe"] or texts.MEAL_EMPTY_FIELD
    elif field == "ingredients":
        ings = await admin.meal_ingredients(meal["id"])
        current = ", ".join(f"{i['name']} {_num(i['quantity'])}" for i in ings) or texts.MEAL_EMPTY_FIELD
    else:
        return ""
    return "\n\nCurrent: <code>" + _esc(current[:600]) + "</code>"


def _summary(d: dict, category: str) -> str:
    cal, protein, carbs, fat = d["macros"]
    items = d["items"]
    return texts.MEAL_CONFIRM.format(
        name=_esc(d["name"]), category=_esc(category), price=d["price"], calories=cal, protein=_num(protein),
        carbs=_num(carbs), fat=_num(fat), ingredients=_esc(", ".join(f"{n} {_num(q)}" for n, q, _ in items)),
        photo="yes 📷" if d.get("photo") else "none", description=_esc(d.get("description") or texts.MEAL_EMPTY_FIELD),
        recipe=_esc((d.get("recipe") or texts.MEAL_EMPTY_FIELD)[:200]),
    )


async def _ask(chat, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the prompt for the current step, always with a Cancel button."""
    flow = _flow(context)
    step, kind, d = flow["step"], flow["kind"], flow["data"]
    rows: list[list[Button]] = []
    text = ""

    if step == "setting_value":
        key = d["key"]
        current = {**SETTING_DEFAULTS, **await admin.all_settings()}[key]
        unit = owner_rules.SETTINGS[key][4]
        text = texts.ASK_SETTING.format(
            label=owner_rules.SETTINGS[key][0], hint=owner_rules.setting_hint(key), current=_esc(current + (" " + unit if unit else ""))
        )
    elif step == "staff_id":
        text = texts.ASK_STAFF_ID
    elif step == "staff_name":
        text = texts.ASK_STAFF_NAME
    elif step == "acct_label":
        text = texts.ASK_ACCT_LABEL
    elif step == "acct_number":
        text = texts.ASK_ACCT_NUMBER
    elif step == "acct_holder":
        text = texts.ASK_ACCT_HOLDER
    elif step == "acct_value":
        text = texts.ASK_ACCT_VALUE.format(what=d["what"], current=_esc(d["current"]))
    elif step == "name":
        text = texts.ASK_MEAL_NAME
    elif step == "category":
        text = texts.ASK_MEAL_CATEGORY
        for c in await admin.categories():
            rows.append([Button(c["name"], callback_data=f"o:pc:{c['id']}")])
        rows.append([Button("➕ New category", callback_data="o:pc:new")])
    elif step == "catname":
        text = texts.ASK_NEW_CATEGORY
    elif step == "price":
        text = texts.ASK_MEAL_PRICE
    elif step == "macros":
        text = texts.ASK_MEAL_MACROS
    elif step == "description":
        text = texts.ASK_MEAL_DESCRIPTION
    elif step == "recipe":
        text = texts.ASK_MEAL_RECIPE
    elif step == "photo":
        text = texts.ASK_MEAL_PHOTO
        label = texts.SKIP_PHOTO_BTN if kind == "meal_add" else texts.REMOVE_PHOTO_BTN
        rows.append([Button(label, callback_data="o:skip")])
    elif step == "ingredients":
        text = texts.ASK_MEAL_INGREDIENTS
    elif step == "allergen":
        text = texts.ASK_ALLERGEN.format(name=_esc(d["pending"][0]))
        rows.append([Button(ALLERGEN_LABELS[k], callback_data="o:pg:" + k) for k in ("none", "dairy", "egg")])
        rows.append([Button(ALLERGEN_LABELS[k], callback_data="o:pg:" + k) for k in ("peanut", "gluten")])
    elif step == "confirm":
        category = next((c["name"] for c in await admin.categories() if c["id"] == d["category"]), "?")
        text = _summary(d, category)
        rows.append([Button("✅ Save meal", callback_data="o:yes")])
    elif step == "bc_content":
        text = texts.BC_ASK
    elif step == "audience":
        counts = await admin.audience_counts()
        text = texts.BC_AUDIENCE
        rows.append([Button(f"👥 All customers ({counts['everyone']})", callback_data="o:aud:all")])
        rows.append([Button(f"🔥 Ordered in the last 30 days ({counts['active']})", callback_data="o:aud:active")])
        rows.append([Button("📱 Specific customers", callback_data="o:aud:some")])
    elif step == "phones":
        text = texts.BC_ASK_PHONES

    if step in ("name", "price", "macros", "description", "recipe", "ingredients") and kind == "meal_edit":
        text += await _current_hint(flow)
    rows.append(_cancel_row())
    await _send(chat, text, InlineKeyboardMarkup(rows))


async def _goto(update, context, step: str) -> int:
    _flow(context)["step"] = step
    await _ask(update.effective_chat, context)
    return INPUT


async def _complete(update, context, key: str, value) -> int:
    """A step of a meal form is done: store it, then continue the add form or save the edit."""
    flow = _flow(context)
    flow["data"][key] = value
    if flow["kind"] == "meal_edit":
        return await _apply_meal_edit(update, context)
    return await _goto(update, context, ADD_ORDER[ADD_ORDER.index(key) + 1])


async def _apply_meal_edit(update, context) -> int:
    flow = _flow(context)
    d = flow["data"]
    meal_id, field = d["meal_id"], d["field"]
    if field == "name":
        ok = await admin.update_meal_field(meal_id, "name", d["name"])
    elif field == "category":
        ok = await admin.update_meal_field(meal_id, "category_id", d["category"])
    elif field == "price":
        ok = await admin.update_meal_field(meal_id, "price_etb", d["price"])
    elif field == "macros":
        ok = await admin.update_meal_macros(meal_id, *d["macros"])
    elif field == "description":
        ok = await admin.update_meal_field(meal_id, "description", d["description"] or None)
    elif field == "recipe":
        ok = await admin.update_meal_field(meal_id, "recipe", d["recipe"] or None)
    elif field == "photo":
        ok = await admin.update_meal_field(meal_id, "photo_file_id", d["photo"])
    else:
        ok = await admin.replace_meal_ingredients(meal_id, d["items"], d.get("allergens", {}))
    _clear(context)
    chat = update.effective_chat
    if not ok:
        await _send(chat, texts.MEAL_GONE)
        return ConversationHandler.END
    await _send(chat, texts.MEAL_UPDATED)
    await _send(chat, *await meal_screen(meal_id, _today(context).date()))
    return ConversationHandler.END


# ----- typed answers, one small function per step -----

async def _t_setting_value(update, context, flow, text) -> int:
    key = flow["data"]["key"]
    value = owner_rules.parse_setting(key, text)
    if value is None:
        await update.message.reply_text(texts.ERR_SETTING.format(hint=owner_rules.setting_hint(key)), parse_mode=ParseMode.HTML)
        return INPUT
    await admin.set_setting(key, value)
    _clear(context)
    label, _, _, _, unit = owner_rules.SETTINGS[key]
    chat = update.effective_chat
    await _send(chat, texts.SETTING_SAVED.format(label=label, value=_esc(value + (" " + unit if unit else ""))))
    await _send(chat, *await settings_screen())
    return ConversationHandler.END


async def _t_staff_id(update, context, flow, text) -> int:
    tg_id = owner_rules.parse_telegram_id(text)
    if tg_id is None:
        await update.message.reply_text(texts.ERR_STAFF_ID)
        return INPUT
    person = await admin.get_staff(tg_id)
    chat = update.effective_chat
    if person and (person["role"] == "owner" or person["is_active"]):
        _clear(context)
        await _send(chat, texts.STAFF_IS_OWNER if person["role"] == "owner" else texts.STAFF_EXISTS)
        await _send(chat, *await staff_screen())
        return ConversationHandler.END
    flow["data"]["tg_id"] = tg_id
    return await _goto(update, context, "staff_name")


async def _t_staff_name(update, context, flow, text) -> int:
    name = owner_rules.parse_name(text, 2, 60)
    if name is None:
        await update.message.reply_text(texts.ERR_PERSON_NAME)
        return INPUT
    tg_id = flow["data"]["tg_id"]
    result = await admin.add_staff(tg_id, name)
    _clear(context)
    chat = update.effective_chat
    if result in ("added", "reactivated"):
        notice = (texts.STAFF_ADDED if result == "added" else texts.STAFF_REACTIVATED).format(name=_esc(name))
        if not await notify.send_customer(context.bot, tg_id, texts.STAFF_WELCOME):
            notice += "\n" + texts.STAFF_NOT_NOTIFIED
    else:
        notice = texts.STAFF_IS_OWNER if result == "owner" else texts.STAFF_EXISTS
    await _send(chat, notice)
    await _send(chat, *await staff_screen())
    return ConversationHandler.END


async def _t_acct_label(update, context, flow, text) -> int:
    value = owner_rules.parse_name(text, 1, 30)
    if value is None:
        await update.message.reply_text(texts.ERR_ACCT_LABEL)
        return INPUT
    flow["data"]["label"] = value
    return await _goto(update, context, "acct_number")


async def _t_acct_number(update, context, flow, text) -> int:
    value = owner_rules.parse_name(text, 3, 40)
    if value is None:
        await update.message.reply_text(texts.ERR_ACCT_NUMBER)
        return INPUT
    flow["data"]["number"] = value
    return await _goto(update, context, "acct_holder")


async def _t_acct_holder(update, context, flow, text) -> int:
    value = owner_rules.parse_name(text, 2, 60)
    if value is None:
        await update.message.reply_text(texts.ERR_PERSON_NAME)
        return INPUT
    d = flow["data"]
    await admin.add_account(d["label"], d["number"], value)
    _clear(context)
    await _send(update.effective_chat, texts.ACCT_SAVED)
    await _send(update.effective_chat, *await accounts_screen())
    return ConversationHandler.END


async def _t_acct_value(update, context, flow, text) -> int:
    d = flow["data"]
    low, high = {"label": (1, 30), "account_number": (3, 40), "holder_name": (2, 60)}[d["column"]]
    value = owner_rules.parse_name(text, low, high)
    if value is None:
        await update.message.reply_text(texts.ERR_ACCT_NUMBER if d["column"] == "account_number" else texts.ERR_ACCT_LABEL if d["column"] == "label" else texts.ERR_PERSON_NAME)
        return INPUT
    ok = await admin.update_account(d["account_id"], d["column"], value)
    _clear(context)
    chat = update.effective_chat
    if not ok:
        await _send(chat, texts.ACCT_GONE)
        return ConversationHandler.END
    await _send(chat, texts.ACCT_SAVED)
    await _send(chat, *(await account_screen(d["account_id"])))
    return ConversationHandler.END


async def _t_name(update, context, flow, text) -> int:
    value = owner_rules.parse_name(text, 2, 60)
    if value is None:
        await update.message.reply_text(texts.ERR_PERSON_NAME)
        return INPUT
    return await _complete(update, context, "name", value)


async def _t_catname(update, context, flow, text) -> int:
    value = owner_rules.parse_name(text, 2, 40)
    if value is None:
        await update.message.reply_text(texts.ERR_CATEGORY)
        return INPUT
    return await _complete(update, context, "category", await admin.get_or_create_category(value))


async def _t_price(update, context, flow, text) -> int:
    value = owner_rules.parse_price(text)
    if value is None:
        await update.message.reply_text(texts.ERR_MEAL_PRICE)
        return INPUT
    return await _complete(update, context, "price", value)


async def _t_macros(update, context, flow, text) -> int:
    value = owner_rules.parse_macros(text)
    if value is None:
        await update.message.reply_text(texts.ERR_MEAL_MACROS)
        return INPUT
    return await _complete(update, context, "macros", value)


async def _t_description(update, context, flow, text) -> int:
    value = owner_rules.parse_optional_text(text, 300)
    if value is False:
        await update.message.reply_text(texts.ERR_MEAL_DESCRIPTION)
        return INPUT
    return await _complete(update, context, "description", value)


async def _t_recipe(update, context, flow, text) -> int:
    value = owner_rules.parse_optional_text(text, 1000)
    if value is False:
        await update.message.reply_text(texts.ERR_MEAL_RECIPE)
        return INPUT
    return await _complete(update, context, "recipe", value)


async def _t_ingredients(update, context, flow, text) -> int:
    items, error = owner_rules.parse_ingredients(text)
    if error:
        await update.message.reply_text(texts.ERR_ING[error], parse_mode=ParseMode.HTML)
        return INPUT
    d = flow["data"]
    d["items"] = items
    d["allergens"] = {}
    d["pending"] = await admin.unknown_ingredients([n for n, _, _ in items])
    if d["pending"]:
        return await _goto(update, context, "allergen")
    return await _complete(update, context, "ingredients", items)


async def _t_bc_content(update, context, flow, text) -> int:
    value = owner_rules.clean_text(text)
    if not value or len(value) > 1000:
        await update.message.reply_text(texts.ERR_BC_CONTENT)
        return INPUT
    flow["data"]["text"], flow["data"]["photo"] = value, None
    return await _goto(update, context, "audience")


async def _t_phones(update, context, flow, text) -> int:
    valid, _ = owner_rules.normalize_phones(text)
    found = await admin.matched_phones(valid) if valid else set()
    if not found:
        await update.message.reply_text(texts.ERR_BC_PHONES)
        return INPUT
    d = flow["data"]
    d["audience"], d["phones"] = "some", sorted(found)
    missing = [p for p in valid if p not in found]
    if missing:
        await _send(update.effective_chat, texts.BC_PHONES_MISSING.format(numbers=_esc(", ".join(missing))))
    return await _bc_preview(update, context)


TEXT_STEPS = {
    "setting_value": _t_setting_value, "staff_id": _t_staff_id, "staff_name": _t_staff_name,
    "acct_label": _t_acct_label, "acct_number": _t_acct_number, "acct_holder": _t_acct_holder,
    "acct_value": _t_acct_value, "name": _t_name, "catname": _t_catname, "price": _t_price,
    "macros": _t_macros, "description": _t_description, "recipe": _t_recipe, "ingredients": _t_ingredients,
    "bc_content": _t_bc_content, "phones": _t_phones,
}


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = _flow(context)
    if not flow or not await _is_owner(update, context):
        _clear(context)
        return ConversationHandler.END
    handler = TEXT_STEPS.get(flow["step"])
    if handler is None:
        await update.message.reply_text(texts.OWNER_USE_BUTTONS)
        return INPUT
    return await handler(update, context, flow, update.message.text or "")


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = _flow(context)
    if not flow or not await _is_owner(update, context):
        _clear(context)
        return ConversationHandler.END
    file_id = update.message.photo[-1].file_id
    if flow["step"] == "photo":
        return await _complete(update, context, "photo", file_id)
    if flow["step"] == "bc_content":
        caption = owner_rules.clean_text(update.message.caption)
        if len(caption) > 1000:
            await update.message.reply_text(texts.ERR_BC_CONTENT)
            return INPUT
        flow["data"]["text"], flow["data"]["photo"] = caption or None, file_id
        return await _goto(update, context, "audience")
    await update.message.reply_text(texts.OWNER_USE_TEXT)
    return INPUT


async def on_image_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    flow = _flow(context)
    if flow and flow["step"] in ("photo", "bc_content"):
        await update.message.reply_text(texts.ERR_PHOTO_FILE, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(texts.OWNER_USE_TEXT)
    return INPUT


# ----- buttons inside the conversation -----

async def _step_button(update, context, *steps: str) -> dict | None:
    """The flow if it is on one of `steps` and the tapper is the owner; otherwise answers the tap and returns None."""
    query = update.callback_query
    if not await _is_owner(update, context):
        await query.answer(texts.OWNER_ONLY, show_alert=True)
        return None
    flow = _flow(context)
    if not flow or flow["step"] not in steps:
        await query.answer(texts.OWNER_STALE, show_alert=True)
        return None
    await query.answer()
    return flow


async def on_category(update, context) -> int:
    flow = await _step_button(update, context, "category")
    if flow is None:
        return INPUT
    value = update.callback_query.data.split(":")[2]
    if value == "new":
        return await _goto(update, context, "catname")
    return await _complete(update, context, "category", int(value))


async def on_allergen(update, context) -> int:
    flow = await _step_button(update, context, "allergen")
    if flow is None:
        return INPUT
    tag = update.callback_query.data.split(":")[2]
    d = flow["data"]
    name = d["pending"].pop(0)
    d["allergens"][name.lower()] = None if tag == "none" else tag
    if d["pending"]:
        return await _goto(update, context, "allergen")
    return await _complete(update, context, "ingredients", d["items"])


async def on_skip(update, context) -> int:
    flow = await _step_button(update, context, "photo")
    if flow is None:
        return INPUT
    return await _complete(update, context, "photo", None)


async def on_save_meal(update, context) -> int:
    flow = await _step_button(update, context, "confirm")
    if flow is None:
        return INPUT
    d = flow["data"]
    cal, protein, carbs, fat = d["macros"]
    meal = await admin.create_meal(
        {
            "name": d["name"], "category_id": d["category"], "price": d["price"], "calories": cal,
            "protein": protein, "carbs": carbs, "fat": fat, "description": d.get("description"),
            "recipe": d.get("recipe"), "photo": d.get("photo"),
        },
        d["items"], d.get("allergens", {}),
    )
    _clear(context)
    chat = update.effective_chat
    await _send(chat, texts.MEAL_ADDED.format(code=_esc(meal["meal_code"]), name=_esc(d["name"])))
    await _send(chat, *await meal_screen(meal["id"], _today(context).date()))
    return ConversationHandler.END


async def on_audience(update, context) -> int:
    flow = await _step_button(update, context, "audience")
    if flow is None:
        return INPUT
    kind = update.callback_query.data.split(":")[2]
    if kind == "some":
        return await _goto(update, context, "phones")
    if not await admin.audience(kind):
        await _send(update.effective_chat, texts.BC_EMPTY)
        return INPUT
    flow["data"]["audience"], flow["data"]["phones"] = kind, None
    return await _bc_preview(update, context)


async def _bc_preview(update, context) -> int:
    """Show the owner exactly what customers will get, then ask for the final go-ahead."""
    flow = _flow(context)
    d = flow["data"]
    chat = update.effective_chat
    count = len(await admin.audience(d["audience"], d.get("phones")))
    if d.get("photo"):
        await chat.send_photo(d["photo"], caption=d.get("text") or None)
    else:
        await chat.send_message(d["text"])
    flow["step"] = "bc_confirm"
    rows = [[Button("📣 Send now", callback_data="o:send")], _cancel_row()]
    await _send(chat, texts.BC_CONFIRM.format(count=count), InlineKeyboardMarkup(rows))
    return INPUT


async def on_send(update, context) -> int:
    flow = await _step_button(update, context, "bc_confirm")
    if flow is None:
        return INPUT
    d = flow["data"]
    ids = list(dict.fromkeys(await admin.audience(d["audience"], d.get("phones"))))
    _clear(context)
    chat = update.effective_chat
    if not ids:
        await _send(chat, texts.BC_EMPTY)
        return ConversationHandler.END
    await _send(chat, texts.BC_SENDING.format(count=len(ids)))
    # A background task, so the bot keeps answering other people while the broadcast goes out.
    context.application.create_task(
        _run_broadcast(context.bot, chat.id, update.effective_user.id, ids, d.get("text"), d.get("photo")),
        update=update,
    )
    return ConversationHandler.END


async def _deliver(bot, chat_id: int, text: str | None, photo: str | None) -> bool:
    for attempt in (1, 2):
        try:
            if photo:
                await bot.send_photo(chat_id, photo, caption=text or None)
            else:
                await bot.send_message(chat_id, text)
            return True
        except RetryAfter as exc:
            if attempt == 2:
                return False
            await asyncio.sleep(exc.retry_after + 1)
        except (Forbidden, BadRequest, TelegramError) as exc:
            log.info("Broadcast could not reach %s: %s", chat_id, exc)
            return False
    return False


async def _run_broadcast(bot, owner_chat: int, sender: int, ids: list[int], text, photo) -> None:
    delivered = 0
    for chat_id in ids:
        if await _deliver(bot, chat_id, text, photo):
            delivered += 1
        await asyncio.sleep(BROADCAST_PAUSE)
    try:
        await admin.log_broadcast(sender, text, photo, delivered)
    except Exception:  # the customers already got the message; a logging problem must not hide that
        log.exception("Could not write the broadcast log")
    failed = len(ids) - delivered
    summary = texts.BC_DONE.format(
        delivered=delivered, total=len(ids), failed=texts.BC_FAILED.format(failed=failed) if failed else ""
    )
    try:
        await bot.send_message(owner_chat, summary, parse_mode=ParseMode.HTML)
    except TelegramError as exc:
        log.warning("Could not tell the owner the broadcast finished: %s", exc)


async def abort(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
    _clear(context)
    await _send(update.effective_chat, texts.OWNER_CANCELLED, InlineKeyboardMarkup([_menu_row()]))
    return ConversationHandler.END


async def abort_to_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear(context)
    role = await home.get_role(update, context)
    text, markup = home.home_for(role)
    await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    return ConversationHandler.END


def conversation() -> ConversationHandler:
    text_only = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(entry_setting, pattern=r"^o:ss:\w+$"),
            CallbackQueryHandler(entry_staff_add, pattern=r"^o:sa$"),
            CallbackQueryHandler(entry_acct_add, pattern=r"^o:aa$"),
            CallbackQueryHandler(entry_acct_edit, pattern=r"^o:ae:\d+:(label|number|holder)$"),
            CallbackQueryHandler(entry_meal_add, pattern=r"^o:ma$"),
            CallbackQueryHandler(entry_meal_edit, pattern=r"^o:me:\d+:\w+$"),
            CallbackQueryHandler(entry_broadcast, pattern=r"^o:bc$"),
        ],
        states={
            INPUT: [
                CallbackQueryHandler(on_category, pattern=r"^o:pc:(\d+|new)$"),
                CallbackQueryHandler(on_allergen, pattern=r"^o:pg:(none|dairy|egg|peanut|gluten)$"),
                CallbackQueryHandler(on_skip, pattern=r"^o:skip$"),
                CallbackQueryHandler(on_save_meal, pattern=r"^o:yes$"),
                CallbackQueryHandler(on_audience, pattern=r"^o:aud:(all|active|some)$"),
                CallbackQueryHandler(on_send, pattern=r"^o:send$"),
                CallbackQueryHandler(abort, pattern=r"^o:abort$"),
                MessageHandler(text_only, on_text),
                MessageHandler(filters.PHOTO, on_photo),
                MessageHandler(filters.Document.IMAGE, on_image_file),
            ],
        },
        fallbacks=[CommandHandler("cancel", abort), CommandHandler("start", abort_to_home)],
        allow_reentry=True,
        conversation_timeout=CONVERSATION_TIMEOUT,
    )
