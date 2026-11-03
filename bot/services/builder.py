"""Meal builder data: which ingredients can be picked and which meals contain them."""
from __future__ import annotations

from .. import db


async def pickable_ingredients() -> list[dict]:
    """Ingredients used by at least one active meal, A to Z."""
    return await db.fetch_all(
        """
        SELECT DISTINCT i.id, i.name
        FROM ingredients i
        JOIN meal_ingredients mi ON mi.ingredient_id = i.id
        JOIN meals m ON m.id = mi.meal_id AND m.is_active
        ORDER BY i.name
        """
    )


async def menu_for_matching() -> list[dict]:
    """Every active meal that has ingredients, with its ingredient list (biggest quantity first)."""
    rows = await db.fetch_all(
        """
        SELECT m.id, m.meal_code, m.name, m.price_etb, m.sold_out_on,
               i.id AS ing_id, i.name AS ing_name, i.allergen
        FROM meals m
        JOIN meal_ingredients mi ON mi.meal_id = m.id
        JOIN ingredients i ON i.id = mi.ingredient_id
        WHERE m.is_active
        ORDER BY m.id, mi.quantity DESC, i.name
        """
    )
    meals: dict[int, dict] = {}
    for r in rows:
        meal = meals.setdefault(
            r["id"],
            {
                "id": r["id"], "meal_code": r["meal_code"], "name": r["name"],
                "price_etb": r["price_etb"], "sold_out_on": r["sold_out_on"], "ingredients": [],
            },
        )
        meal["ingredients"].append({"id": r["ing_id"], "name": r["ing_name"], "allergen": r["allergen"]})
    return list(meals.values())
