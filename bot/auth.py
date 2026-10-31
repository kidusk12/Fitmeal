"""Who is this Telegram user? owner, kitchen, or customer."""
from __future__ import annotations

from typing import Iterable

from . import db


async def get_role(tg_user_id: int, owner_ids: Iterable[int]) -> str:
    if tg_user_id in owner_ids:
        return "owner"
    row = await db.fetch_one(
        "SELECT role FROM staff WHERE tg_user_id = %s AND is_active", (tg_user_id,)
    )
    return row["role"] if row else "customer"


def is_staff(role: str) -> bool:
    return role in ("owner", "kitchen")
