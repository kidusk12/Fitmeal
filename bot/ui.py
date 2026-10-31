"""Small helper for showing a screen by editing the current message (or replacing it when photos are involved)."""
from __future__ import annotations

from telegram import CallbackQuery, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest


async def render(
    query: CallbackQuery,
    text: str,
    markup: InlineKeyboardMarkup | None = None,
    photo: str | None = None,
) -> None:
    message = query.message
    if photo or message.photo:
        # A photo message cannot be turned into a text message (or the reverse), so replace it.
        chat = message.chat
        try:
            await message.delete()
        except BadRequest:
            pass
        if photo:
            await chat.send_photo(photo, caption=text, parse_mode=ParseMode.HTML, reply_markup=markup)
        else:
            await chat.send_message(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        return
    try:
        await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
    except BadRequest as exc:
        if "not modified" not in str(exc).lower():
            raise
