"""Browsing: categories, meal list, meal card with allergy warning, add to cart."""
from __future__ import annotations

import html
from datetime import datetime

from telegram import InlineKeyboardButton as Button
from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from .. import db, texts, ui
from ..services import allergy, cart, users
from . import start as home

PATTERN = r"^(browse|cat:\d+|meal:\d+|add:\d+)$"


def _today(context: ContextTypes.DEFAULT_TYPE):
    return datetime.now(home.get_config(context).timezone).date()


async def _categories_screen() -> tuple[str, InlineKeyboardMarkup]:
    rows = await db.fetch_all(
        """
        SELECT c.id, c.name, count(m.id) AS n
        FROM categories c JOIN meals m ON m.category_id = c.id AND m.is_active
        GROUP BY c.id ORDER BY c.sort_order
        """
    )
    if not rows:
        return texts.BROWSE_EMPTY, InlineKeyboardMarkup([[Button("⬅️ Back", callback_data="c:home")]])
    buttons = [[Button(r["name"] + " (" + str(r["n"]) + ")", callback_data="cat:" + str(r["id"]))] for r in rows]
    buttons.append([Button("🛒 View cart", callback_data="cart"), Button("⬅️ Back", callback_data="c:home")])
    return texts.BROWSE_HEADER, InlineKeyboardMarkup(buttons)


async def _category_screen(category_id: int, today) -> tuple[str, InlineKeyboardMarkup] | None:
    category = await db.fetch_one("SELECT name FROM categories WHERE id = %s", (category_id,))
    if category is None:
        return None
    meals = await db.fetch_all(
        """
        SELECT id, meal_code, name, price_etb, sold_out_on
        FROM meals WHERE category_id = %s AND is_active ORDER BY name
        """,
        (category_id,),
    )
    buttons = []
    for m in meals:
        label = m["meal_code"] + " · " + m["name"] + " — " + str(m["price_etb"]) + " ETB"
        if m["sold_out_on"] == today:
            label += " (sold out)"
        buttons.append([Button(label, callback_data="meal:" + str(m["id"]))])
    buttons.append([Button("⬅️ Categories", callback_data="browse"), Button("🛒 View cart", callback_data="cart")])
    return texts.CATEGORY_HEADER.format(name=html.escape(category["name"])), InlineKeyboardMarkup(buttons)


async def _meal_card(meal_id: int, user: dict, today):
    meal = await db.fetch_one(
        """
        SELECT id, meal_code, name, category_id, price_etb, calories, protein_g, carbs_g, fat_g,
               description, photo_file_id, sold_out_on
        FROM meals WHERE id = %s AND is_active
        """,
        (meal_id,),
    )
    if meal is None:
        return None
    ingredients = await db.fetch_all(
        """
        SELECT i.name, i.allergen
        FROM meal_ingredients mi JOIN ingredients i ON i.id = mi.ingredient_id
        WHERE mi.meal_id = %s ORDER BY mi.quantity DESC
        """,
        (meal_id,),
    )
    sold_out = meal["sold_out_on"] == today

    lines = [
        "<b>" + html.escape(meal["name"]) + "</b> · " + html.escape(meal["meal_code"]),
        str(meal["price_etb"]) + " ETB",
        "{} kcal · P {:g}g · C {:g}g · F {:g}g".format(
            meal["calories"], meal["protein_g"], meal["carbs_g"], meal["fat_g"]
        ),
    ]
    if meal["description"]:
        lines += ["", html.escape(meal["description"])]
    if ingredients:
        lines += ["", "<b>Ingredients:</b> " + ", ".join(html.escape(i["name"]) for i in ingredients)]
    hits = allergy.find_conflicts(user.get("allergies"), ingredients)
    if hits:
        lines += ["", texts.ALLERGY_WARNING.format(items=", ".join(html.escape(h) for h in hits))]
    if sold_out:
        lines += ["", texts.SOLD_OUT]
    text = "\n".join(lines)

    rows = []
    if not sold_out:
        rows.append([Button("➕ Add to cart", callback_data="add:" + str(meal_id))])
        rows.append([Button("📝 Add with a note", callback_data="note:add:" + str(meal_id))])
    rows.append([Button("🛒 View cart", callback_data="cart")])
    rows.append([Button("⬅️ Back", callback_data="cat:" + str(meal["category_id"]))])
    return text, InlineKeyboardMarkup(rows), meal["photo_file_id"]


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""
    user = await users.ensure_user(update)
    today = _today(context)

    if data.startswith("add:"):
        meal_id = int(data.split(":")[1])
        meal = await db.fetch_one(
            "SELECT sold_out_on FROM meals WHERE id = %s AND is_active", (meal_id,)
        )
        if meal is None or meal["sold_out_on"] == today:
            await query.answer(texts.MEAL_UNAVAILABLE, show_alert=True)
            return
        result = await cart.add_item(user["id"], meal_id)
        if result == "full":
            await query.answer(texts.CART_FULL.format(n=cart.MAX_LINES), show_alert=True)
        elif result == "max":
            await query.answer(texts.CART_MAX.format(n=cart.MAX_QUANTITY), show_alert=True)
        else:
            await query.answer(texts.ADDED)
        return

    await query.answer()

    if data == "browse":
        text, markup = await _categories_screen()
        await ui.render(query, text, markup)
    elif data.startswith("cat:"):
        screen = await _category_screen(int(data.split(":")[1]), today)
        if screen is None:
            return
        await ui.render(query, screen[0], screen[1])
    elif data.startswith("meal:"):
        card = await _meal_card(int(data.split(":")[1]), user, today)
        if card is None:
            await ui.render(query, texts.MEAL_UNAVAILABLE, InlineKeyboardMarkup([[Button("⬅️ Back", callback_data="browse")]]))
            return
        text, markup, photo = card
        await ui.render(query, text, markup, photo=photo)
