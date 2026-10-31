"""Shopping cart stored in the cart_items table."""
from __future__ import annotations

from .. import db

MAX_LINES = 10      # different meals in one cart
MAX_QUANTITY = 10   # of one meal


async def add_item(user_id: int, meal_id: int, note: str | None = None) -> str:
    """Add one portion. Returns 'ok', 'full' (too many different meals) or 'max' (too many of one meal)."""
    existing = await db.fetch_one(
        "SELECT quantity FROM cart_items WHERE user_id = %s AND meal_id = %s", (user_id, meal_id)
    )
    if existing is None:
        count = await db.fetch_one("SELECT count(*) AS n FROM cart_items WHERE user_id = %s", (user_id,))
        if count["n"] >= MAX_LINES:
            return "full"
    elif existing["quantity"] >= MAX_QUANTITY:
        return "max"
    await db.execute(
        """
        INSERT INTO cart_items (user_id, meal_id, quantity, note) VALUES (%s, %s, 1, %s)
        ON CONFLICT (user_id, meal_id) DO UPDATE SET
            quantity = cart_items.quantity + 1,
            note = COALESCE(EXCLUDED.note, cart_items.note)
        """,
        (user_id, meal_id, note),
    )
    return "ok"


async def decrease_item(user_id: int, meal_id: int) -> None:
    await db.execute(
        "UPDATE cart_items SET quantity = quantity - 1 WHERE user_id = %s AND meal_id = %s",
        (user_id, meal_id),
    )
    await db.execute(
        "DELETE FROM cart_items WHERE user_id = %s AND meal_id = %s AND quantity <= 0",
        (user_id, meal_id),
    )


async def remove_item(user_id: int, meal_id: int) -> None:
    await db.execute("DELETE FROM cart_items WHERE user_id = %s AND meal_id = %s", (user_id, meal_id))


async def set_note(user_id: int, meal_id: int, note: str | None) -> None:
    await db.execute(
        "UPDATE cart_items SET note = %s WHERE user_id = %s AND meal_id = %s", (note, user_id, meal_id)
    )


async def clear(user_id: int) -> None:
    await db.execute("DELETE FROM cart_items WHERE user_id = %s", (user_id,))


async def list_items(user_id: int) -> list[dict]:
    return await db.fetch_all(
        """
        SELECT ci.meal_id, ci.quantity, ci.note,
               m.meal_code, m.name, m.price_etb, m.is_active, m.sold_out_on
        FROM cart_items ci JOIN meals m ON m.id = ci.meal_id
        WHERE ci.user_id = %s
        ORDER BY m.meal_code
        """,
        (user_id,),
    )


async def ingredients_for(meal_ids: list[int]) -> dict[int, list[dict]]:
    """Ingredient names and allergen tags per meal (used for allergy warnings)."""
    if not meal_ids:
        return {}
    rows = await db.fetch_all(
        """
        SELECT mi.meal_id, i.name, i.allergen
        FROM meal_ingredients mi JOIN ingredients i ON i.id = mi.ingredient_id
        WHERE mi.meal_id = ANY(%s)
        """,
        (meal_ids,),
    )
    grouped: dict[int, list[dict]] = {}
    for r in rows:
        grouped.setdefault(r["meal_id"], []).append({"name": r["name"], "allergen": r["allergen"]})
    return grouped
