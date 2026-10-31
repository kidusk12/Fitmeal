"""Customer rows in the users table."""
from __future__ import annotations

from telegram import Update

from .. import db

_EDITABLE = {"full_name", "phone", "allergies", "fitness_goal", "location_hint"}


async def ensure_user(update: Update) -> dict:
    """Create the user row on first contact and return it."""
    u = update.effective_user
    return await db.fetch_one(
        """
        INSERT INTO users (tg_user_id, username, full_name) VALUES (%s, %s, %s)
        ON CONFLICT (tg_user_id) DO UPDATE SET
            username = EXCLUDED.username,
            full_name = CASE WHEN users.signup_complete THEN users.full_name ELSE EXCLUDED.full_name END,
            updated_at = now()
        RETURNING *
        """,
        (u.id, u.username, u.full_name),
    )


async def set_field(tg_user_id: int, column: str, value: str) -> None:
    if column not in _EDITABLE:
        raise ValueError(f"Column not editable: {column}")
    await db.execute(
        f"UPDATE users SET {column} = %s, updated_at = now() WHERE tg_user_id = %s",
        (value, tg_user_id),
    )


async def mark_signup_complete(tg_user_id: int) -> None:
    await db.execute(
        "UPDATE users SET signup_complete = TRUE, updated_at = now() WHERE tg_user_id = %s",
        (tg_user_id,),
    )
