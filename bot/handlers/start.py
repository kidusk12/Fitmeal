"""Phase 1 handlers: /start, role-based menus, and a read-only menu listing from the database."""
from __future__ import annotations

import html

from telegram import InlineKeyboardButton as Button
from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from .. import auth, db, texts
from ..config import Config


def _cfg(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return context.application.bot_data["config"]


async def _role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    return await auth.get_role(update.effective_user.id, _cfg(context).owner_ids)


async def _remember_user(update: Update) -> None:
    u = update.effective_user
    await db.execute(
        """
        INSERT INTO users (tg_user_id, username, full_name) VALUES (%s, %s, %s)
        ON CONFLICT (tg_user_id)
        DO UPDATE SET username = EXCLUDED.username, full_name = EXCLUDED.full_name, updated_at = now()
        """,
        (u.id, u.username, u.full_name),
    )


# ---------- menus ----------

def customer_menu(role: str) -> tuple[str, InlineKeyboardMarkup]:
    rows = [
        [Button("🍽 Browse menu", callback_data="c:menu")],
        [Button("🛒 My cart", callback_data="soon:2"), Button("📦 My orders", callback_data="soon:3")],
        [Button("👤 Profile", callback_data="soon:2")],
    ]
    if auth.is_staff(role):
        rows.append([Button("↩️ Back to staff menu", callback_data="home")])
    return texts.WELCOME_CUSTOMER, InlineKeyboardMarkup(rows)


def staff_menu(role: str) -> tuple[str, InlineKeyboardMarkup]:
    rows = [
        [Button("📋 Order queue", callback_data="soon:5")],
        [Button("🍲 Meals", callback_data="soon:6")],
    ]
    if role == "owner":
        rows.append([Button("⚙️ Settings", callback_data="soon:6"), Button("👥 Staff", callback_data="soon:6")])
    rows.append([Button("🛍 Preview customer menu", callback_data="c:home")])
    return texts.WELCOME_STAFF.format(role=role), InlineKeyboardMarkup(rows)


def home_for(role: str) -> tuple[str, InlineKeyboardMarkup]:
    return staff_menu(role) if auth.is_staff(role) else customer_menu(role)


async def _menu_listing() -> str:
    rows = await db.fetch_all(
        """
        SELECT c.name AS category, m.meal_code, m.name, m.price_etb,
               m.calories, m.protein_g, m.carbs_g, m.fat_g
        FROM meals m JOIN categories c ON c.id = m.category_id
        WHERE m.is_active
        ORDER BY c.sort_order, m.name
        """
    )
    if not rows:
        return texts.MENU_EMPTY
    lines = [texts.MENU_HEADER]
    current = None
    for r in rows:
        if r["category"] != current:
            current = r["category"]
            lines.append(f"\n<b>{html.escape(current)}</b>")
        lines.append(
            f"{html.escape(r['meal_code'])} · {html.escape(r['name'])} — {r['price_etb']} ETB\n"
            f"   {r['calories']} kcal · P {r['protein_g']:g}g · C {r['carbs_g']:g}g · F {r['fat_g']:g}g"
        )
    return "\n".join(lines)


# ---------- commands ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _remember_user(update)
    role = await _role(update, context)
    text, markup = home_for(role)
    await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    role = await _role(update, context)
    await update.effective_chat.send_message(f"Your Telegram ID: {update.effective_user.id}\nRole: {role}")


async def customer_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    role = await _role(update, context)
    text, markup = customer_menu(role)
    await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)


# ---------- buttons ----------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""

    if data.startswith("soon:"):
        await query.answer(texts.COMING_SOON.format(phase=data.split(":")[1]), show_alert=True)
        return

    await query.answer()
    role = await _role(update, context)

    if data == "home":
        text, markup = home_for(role)
    elif data == "c:home":
        text, markup = customer_menu(role)
    elif data == "c:menu":
        text = await _menu_listing()
        markup = InlineKeyboardMarkup([[Button("⬅️ Back", callback_data="c:home")]])
    else:
        return

    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
