"""Meal builder: the customer picks ingredients and gets the closest meals on the menu (SRS FR-C10)."""
from __future__ import annotations

import html
from datetime import datetime

from telegram import InlineKeyboardButton as Button
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .. import texts, ui
from ..services import allergy, builder, matcher, users
from . import start as home

PATTERN = r"^mb:(start|clear|go|p:\d+|t:\d+:\d+)$"
PAGE_SIZE = 10     # ingredients per page (two columns)
MAX_PICKS = 10     # most ingredients a customer can pick at once
KEY = "mb_picked"  # where the picks live in context.user_data (lost on restart, which is fine)


def _picked(context: ContextTypes.DEFAULT_TYPE) -> list[int]:
    return context.user_data.setdefault(KEY, [])


def _back_row() -> list[Button]:
    return [Button("⬅️ Menu", callback_data="c:home")]


async def _picker_screen(picked: list[int], page: int) -> tuple[str, InlineKeyboardMarkup]:
    options = await builder.pickable_ingredients()
    if not options:
        return texts.BUILDER_EMPTY, InlineKeyboardMarkup([_back_row()])
    pages = (len(options) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, pages - 1))
    names = {o["id"]: o["name"] for o in options}
    picked = [i for i in picked if i in names]   # forget ingredients that are no longer on the menu

    lines = [texts.BUILDER_PICK]
    if picked:
        lines.append(texts.BUILDER_PICKED.format(n=len(picked), names=", ".join(html.escape(names[i]) for i in picked)))
    else:
        lines.append(texts.BUILDER_NOTHING_PICKED)
    if pages > 1:
        lines.append(texts.BUILDER_PAGE.format(page=page + 1, pages=pages))

    chunk = options[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    rows, row = [], []
    for o in chunk:
        label = ("✅ " if o["id"] in picked else "") + o["name"]
        row.append(Button(label, callback_data="mb:t:{}:{}".format(o["id"], page)))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav = []
    if page > 0:
        nav.append(Button("◀️ Previous", callback_data="mb:p:" + str(page - 1)))
    if page < pages - 1:
        nav.append(Button("Next ▶️", callback_data="mb:p:" + str(page + 1)))
    if nav:
        rows.append(nav)
    if picked:
        rows.append([Button("🔎 Find meals ({})".format(len(picked)), callback_data="mb:go"),
                     Button("🧹 Clear", callback_data="mb:clear")])
    rows.append(_back_row())
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def _results_screen(picked: list[int], user: dict, today) -> tuple[str, InlineKeyboardMarkup]:
    options = await builder.pickable_ingredients()
    names = {o["id"]: o["name"] for o in options}
    selected = {i for i in picked if i in names}

    meals = await builder.menu_for_matching()
    for m in meals:
        m["sold_out"] = m["sold_out_on"] == today
        m["conflict"] = bool(allergy.find_conflicts(user.get("allergies"), m["ingredients"]))
    matches = matcher.rank(selected, meals)

    change = [Button("✏️ Change ingredients", callback_data="mb:p:0")]
    if not matches:
        return texts.BUILDER_NONE, InlineKeyboardMarkup([change, _back_row()])

    wanted = ", ".join(html.escape(names[i]) for i in sorted(selected, key=lambda i: names[i]))
    lines = [texts.BUILDER_RESULTS_HEADER.format(names=wanted)]
    buttons = []
    for number, match in enumerate(matches, start=1):
        meal = match.meal
        lines.append("")
        lines.append("{}. <b>{}</b> {} · {} ETB".format(
            number, html.escape(meal["meal_code"]), html.escape(meal["name"]), meal["price_etb"]))
        if match.complete:
            lines.append(texts.BUILDER_HAS_ALL)
        else:
            lines.append(texts.BUILDER_HAS_SOME.format(have=len(match.have), total=len(selected)))
            lines.append(texts.BUILDER_NOT_IN.format(
                names=html.escape(matcher.short_list([names[i] for i in match.missing]))))
        if match.extra:
            lines.append(texts.BUILDER_ALSO.format(
                names=html.escape(matcher.short_list([e["name"] for e in match.extra]))))
        if meal["conflict"]:
            lines.append(texts.BUILDER_ALLERGY)
        if meal["sold_out"]:
            lines.append(texts.BUILDER_SOLD_OUT)
        buttons.append([Button("🍽 {} · {}".format(meal["meal_code"], meal["name"]), callback_data="meal:" + str(meal["id"]))])
    lines += ["", texts.BUILDER_FOOTER]
    buttons.append(change)
    buttons.append(_back_row())
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    parts = (query.data or "").split(":")
    action = parts[1]
    picked = _picked(context)

    if action == "t":
        ingredient_id, page = int(parts[2]), int(parts[3])
        if ingredient_id in picked:
            picked.remove(ingredient_id)
        else:
            options = await builder.pickable_ingredients()
            if ingredient_id not in {o["id"] for o in options}:
                await query.answer(texts.BUILDER_GONE, show_alert=True)
                text, markup = await _picker_screen(picked, page)
                await ui.render(query, text, markup)
                return
            if len(picked) >= MAX_PICKS:
                await query.answer(texts.BUILDER_MAX.format(n=MAX_PICKS), show_alert=True)
                return
            picked.append(ingredient_id)
        await query.answer()
        text, markup = await _picker_screen(picked, page)
        await ui.render(query, text, markup)
        return

    if action == "go":
        if not picked:
            await query.answer(texts.BUILDER_PICK_FIRST, show_alert=True)
            return
        user = await users.ensure_user(update)
        today = datetime.now(home.get_config(context).timezone).date()
        text, markup = await _results_screen(picked, user, today)
        await query.answer()
        await ui.render(query, text, markup)
        return

    await query.answer()
    page = 0
    if action in ("start", "clear"):
        picked.clear()
    elif action == "p":
        page = int(parts[2])
    text, markup = await _picker_screen(picked, page)
    await ui.render(query, text, markup)
