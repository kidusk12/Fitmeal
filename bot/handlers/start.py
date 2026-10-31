"""Home menus (customer and staff) and small commands."""
from __future__ import annotations

from telegram import InlineKeyboardButton as Button
from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from .. import auth, texts, ui
from ..config import Config

PATTERN = r"^(home|c:home|soon:\d+)$"


def get_config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return context.application.bot_data["config"]


async def get_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    return await auth.get_role(update.effective_user.id, get_config(context).owner_ids)


def customer_menu(role: str) -> tuple[str, InlineKeyboardMarkup]:
    rows = [
        [Button("🍽 Browse menu", callback_data="browse")],
        [Button("🛒 My cart", callback_data="cart"), Button("📦 My orders", callback_data="orders")],
        [Button("👤 Profile", callback_data="profile")],
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


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    role = await get_role(update, context)
    await update.effective_chat.send_message(f"Your Telegram ID: {update.effective_user.id}\nRole: {role}")


async def customer_preview(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    role = await get_role(update, context)
    text, markup = customer_menu(role)
    await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data or ""

    if data.startswith("soon:"):
        await query.answer(texts.COMING_SOON.format(phase=data.split(":")[1]), show_alert=True)
        return

    await query.answer()
    role = await get_role(update, context)
    text, markup = home_for(role) if data == "home" else customer_menu(role)
    await ui.render(query, text, markup)
