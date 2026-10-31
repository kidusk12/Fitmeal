"""Customer signup (first /start) and profile editing, as a step-by-step conversation."""
from __future__ import annotations

import html
import re

from telegram import InlineKeyboardButton as Button
from telegram import (
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .. import auth, texts, ui
from ..services import users
from ..services.phone import normalize_phone
from . import start as home

NAME, PHONE, ALLERGIES, GOAL, LOCATION = range(5)
FLOW = [NAME, PHONE, ALLERGIES, GOAL, LOCATION]
KEEP = "Keep current"

# step -> (database column, question, quick-answer buttons, offer "share my number")
STEPS = {
    NAME: ("full_name", texts.ASK_NAME, [], False),
    PHONE: ("phone", texts.ASK_PHONE, [], True),
    ALLERGIES: ("allergies", texts.ASK_ALLERGIES, ["None"], False),
    GOAL: ("fitness_goal", texts.ASK_GOAL, ["Weight loss", "Muscle gain", "Stay fit"], False),
    LOCATION: ("location_hint", texts.ASK_LOCATION, [], False),
}


def _validate(step: int, text: str) -> str | None:
    """Return the cleaned value, or None if the text is not acceptable."""
    if step == NAME:
        return text if 2 <= len(text) <= 80 else None
    if step == PHONE:
        return normalize_phone(text)
    if step == ALLERGIES:
        return text if 1 <= len(text) <= 200 else None
    if step == GOAL:
        return text if 2 <= len(text) <= 60 else None
    if step == LOCATION:
        return text if 2 <= len(text) <= 120 else None
    return None


ERRORS = {
    NAME: texts.ERR_NAME,
    PHONE: texts.ERR_PHONE,
    ALLERGIES: texts.ERR_ALLERGIES,
    GOAL: texts.ERR_GOAL,
    LOCATION: texts.ERR_LOCATION,
}


async def _ask(update: Update, context: ContextTypes.DEFAULT_TYPE, step: int) -> None:
    column, question, quick, offer_contact = STEPS[step]
    current = context.user_data.get("profile_before", {}).get(column)
    rows = []
    if offer_contact:
        rows.append([KeyboardButton(texts.SHARE_NUMBER, request_contact=True)])
    if quick:
        rows.append([KeyboardButton(label) for label in quick])
    if current:
        rows.append([KeyboardButton(KEEP)])
    markup = (
        ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)
        if rows
        else ReplyKeyboardRemove()
    )
    text = question
    if current:
        text += "\n\nCurrent: <i>" + html.escape(str(current)) + "</i>"
    await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)


async def _begin(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict) -> int:
    context.user_data["profile_before"] = {STEPS[s][0]: user.get(STEPS[s][0]) for s in FLOW}
    await _ask(update, context, NAME)
    return NAME


async def start_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/start: new customers go through signup, everyone else sees their home menu."""
    user = await users.ensure_user(update)
    role = await home.get_role(update, context)
    if not auth.is_staff(role) and not user["signup_complete"]:
        await update.effective_chat.send_message(texts.SIGNUP_INTRO, parse_mode=ParseMode.HTML)
        return await _begin(update, context, user)
    text, markup = home.home_for(role)
    await update.effective_chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    return ConversationHandler.END


async def edit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    user = await users.ensure_user(update)
    await update.effective_chat.send_message(texts.UPDATE_INTRO, parse_mode=ParseMode.HTML)
    return await _begin(update, context, user)


def _step_handler(step: int):
    column = STEPS[step][0]

    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        message = update.message
        before = context.user_data.get("profile_before", {})
        text = (message.text or "").strip()

        if step == PHONE and message.contact:
            number = message.contact.phone_number or ""
            value = normalize_phone(number) or ("+" + re.sub(r"\D", "", number))
        elif text == KEEP and before.get(column):
            value = before[column]
        else:
            value = _validate(step, text)

        if value is None:
            await message.reply_text(ERRORS[step])
            return step

        await users.set_field(update.effective_user.id, column, value)

        position = FLOW.index(step)
        if position + 1 < len(FLOW):
            next_step = FLOW[position + 1]
            await _ask(update, context, next_step)
            return next_step
        return await _finish(update, context)

    return handler


async def _finish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await users.mark_signup_complete(update.effective_user.id)
    context.user_data.pop("profile_before", None)
    role = await home.get_role(update, context)
    chat = update.effective_chat
    await chat.send_message(texts.SIGNUP_DONE, reply_markup=ReplyKeyboardRemove())
    text, markup = home.home_for(role)
    await chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("profile_before", None)
    role = await home.get_role(update, context)
    chat = update.effective_chat
    await chat.send_message(texts.CANCELLED, reply_markup=ReplyKeyboardRemove())
    text, markup = home.home_for(role)
    await chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    return ConversationHandler.END


def conversation() -> ConversationHandler:
    text_only = filters.TEXT & ~filters.COMMAND
    states = {step: [MessageHandler(text_only, _step_handler(step))] for step in FLOW}
    states[PHONE].append(MessageHandler(filters.CONTACT, _step_handler(PHONE)))
    return ConversationHandler(
        entry_points=[
            CommandHandler("start", start_entry),
            CallbackQueryHandler(edit_entry, pattern=r"^p:edit$"),
        ],
        states=states,
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start_entry)],
        allow_reentry=True,
    )


# ---------- profile screen ----------

def _show(value: object) -> str:
    return html.escape(str(value)) if value else "—"


async def on_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = await users.ensure_user(update)
    text = texts.PROFILE.format(
        name=_show(user["full_name"]),
        phone=_show(user["phone"]),
        allergies=_show(user["allergies"]),
        goal=_show(user["fitness_goal"]),
        location=_show(user["location_hint"]),
    )
    markup = InlineKeyboardMarkup(
        [
            [Button("✏️ Update profile", callback_data="p:edit")],
            [Button("⬅️ Back", callback_data="c:home")],
        ]
    )
    await ui.render(query, text, markup)
