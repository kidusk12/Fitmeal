"""Database actions for the owner tools (SRS FR-A1 to FR-A5).

Staff, settings, payment accounts, the meal catalogue, broadcast audiences and reports.
Every function does one job; the handlers decide who is allowed to call them.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterable

from .. import db
from . import owner_rules

# ---------- staff (FR-A1) ----------


async def list_staff() -> list[dict]:
    return await db.fetch_all(
        "SELECT tg_user_id, name, role, is_active FROM staff ORDER BY role DESC, added_at, tg_user_id"
    )


async def add_staff(tg_user_id: int, name: str) -> str:
    """Returns 'added', 'reactivated', 'exists' or 'owner' (an owner is never changed here)."""
    row = await db.fetch_one("SELECT role, is_active FROM staff WHERE tg_user_id = %s", (tg_user_id,))
    if row is None:
        await db.execute(
            "INSERT INTO staff (tg_user_id, name, role) VALUES (%s, %s, 'kitchen') ON CONFLICT DO NOTHING",
            (tg_user_id, name),
        )
        return "added"
    if row["role"] == "owner":
        return "owner"
    if row["is_active"]:
        return "exists"
    await db.execute(
        "UPDATE staff SET is_active = TRUE, name = %s, added_at = now() WHERE tg_user_id = %s",
        (name, tg_user_id),
    )
    return "reactivated"


async def remove_staff(tg_user_id: int) -> bool:
    """Switch a kitchen staff member off. Owners cannot be removed. The row stays for the audit trail."""
    row = await db.fetch_one(
        "UPDATE staff SET is_active = FALSE WHERE tg_user_id = %s AND role = 'kitchen' AND is_active RETURNING tg_user_id",
        (tg_user_id,),
    )
    return row is not None


async def get_staff(tg_user_id: int) -> dict | None:
    return await db.fetch_one(
        "SELECT tg_user_id, name, role, is_active FROM staff WHERE tg_user_id = %s", (tg_user_id,)
    )


# ---------- settings (FR-A3) ----------


async def all_settings() -> dict[str, str]:
    rows = await db.fetch_all("SELECT key, value FROM settings")
    return {r["key"]: r["value"] for r in rows}


async def set_setting(key: str, value: str) -> None:
    if key not in owner_rules.SETTINGS:
        raise ValueError(f"Setting not editable: {key}")
    await db.execute(
        """
        INSERT INTO settings (key, value) VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """,
        (key, value),
    )


# ---------- payment accounts (FR-A3) ----------

_ACCOUNT_FIELDS = {"label", "account_number", "holder_name"}


async def list_accounts() -> list[dict]:
    return await db.fetch_all(
        "SELECT id, label, account_number, holder_name, is_active FROM payment_accounts ORDER BY sort_order, id"
    )


async def get_account(account_id: int) -> dict | None:
    return await db.fetch_one(
        "SELECT id, label, account_number, holder_name, is_active FROM payment_accounts WHERE id = %s",
        (account_id,),
    )


async def add_account(label: str, number: str, holder: str) -> int:
    row = await db.fetch_one(
        """
        INSERT INTO payment_accounts (label, account_number, holder_name, sort_order)
        VALUES (%s, %s, %s, COALESCE((SELECT max(sort_order) FROM payment_accounts), 0) + 1)
        RETURNING id
        """,
        (label, number, holder),
    )
    return row["id"]


async def update_account(account_id: int, field: str, value: str) -> bool:
    if field not in _ACCOUNT_FIELDS:
        raise ValueError(f"Account field not editable: {field}")
    row = await db.fetch_one(
        f"UPDATE payment_accounts SET {field} = %s WHERE id = %s RETURNING id", (value, account_id)
    )
    return row is not None


async def _other_active_accounts(conn, account_id: int) -> int:
    cur = await conn.execute(
        "SELECT count(*) AS n FROM payment_accounts WHERE is_active AND id <> %s", (account_id,)
    )
    return (await cur.fetchone())["n"]


async def toggle_account(account_id: int) -> str:
    """Hide or show an account. Returns 'hidden', 'shown', 'last' (cannot hide the last visible one) or 'missing'."""
    async with db.transaction() as conn:
        cur = await conn.execute(
            "SELECT is_active FROM payment_accounts WHERE id = %s FOR UPDATE", (account_id,)
        )
        row = await cur.fetchone()
        if row is None:
            return "missing"
        if row["is_active"]:
            if await _other_active_accounts(conn, account_id) == 0:
                return "last"
            await conn.execute("UPDATE payment_accounts SET is_active = FALSE WHERE id = %s", (account_id,))
            return "hidden"
        await conn.execute("UPDATE payment_accounts SET is_active = TRUE WHERE id = %s", (account_id,))
        return "shown"


async def delete_account(account_id: int) -> str:
    """Returns 'deleted', 'last' or 'missing'. The last visible account can never be removed."""
    async with db.transaction() as conn:
        cur = await conn.execute(
            "SELECT is_active FROM payment_accounts WHERE id = %s FOR UPDATE", (account_id,)
        )
        row = await cur.fetchone()
        if row is None:
            return "missing"
        if row["is_active"] and await _other_active_accounts(conn, account_id) == 0:
            return "last"
        await conn.execute("DELETE FROM payment_accounts WHERE id = %s", (account_id,))
        return "deleted"


# ---------- meals (FR-A2) ----------

MEALS_PER_PAGE = 8
_MEAL_FIELDS = {"name", "category_id", "price_etb", "description", "recipe", "photo_file_id"}


async def categories() -> list[dict]:
    return await db.fetch_all("SELECT id, name FROM categories ORDER BY sort_order, name")


async def get_or_create_category(name: str) -> int:
    row = await db.fetch_one("SELECT id FROM categories WHERE lower(name) = lower(%s)", (name,))
    if row:
        return row["id"]
    row = await db.fetch_one(
        """
        INSERT INTO categories (name, sort_order)
        VALUES (%s, COALESCE((SELECT max(sort_order) FROM categories), 0) + 1)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (name,),
    )
    return row["id"]


async def count_meals() -> int:
    return (await db.fetch_one("SELECT count(*) AS n FROM meals"))["n"]


async def list_meals(page: int) -> list[dict]:
    return await db.fetch_all(
        """
        SELECT id, meal_code, name, price_etb, is_active, sold_out_on
        FROM meals ORDER BY meal_code LIMIT %s OFFSET %s
        """,
        (MEALS_PER_PAGE, page * MEALS_PER_PAGE),
    )


async def get_meal(meal_id: int) -> dict | None:
    return await db.fetch_one(
        """
        SELECT m.id, m.meal_code, m.name, m.category_id, c.name AS category, m.price_etb, m.calories,
               m.protein_g, m.carbs_g, m.fat_g, m.description, m.recipe, m.photo_file_id,
               m.is_active, m.sold_out_on
        FROM meals m JOIN categories c ON c.id = m.category_id
        WHERE m.id = %s
        """,
        (meal_id,),
    )


async def meal_ingredients(meal_id: int) -> list[dict]:
    return await db.fetch_all(
        """
        SELECT i.name, i.unit, i.allergen, mi.quantity
        FROM meal_ingredients mi JOIN ingredients i ON i.id = mi.ingredient_id
        WHERE mi.meal_id = %s ORDER BY i.name
        """,
        (meal_id,),
    )


async def unknown_ingredients(names: Iterable[str]) -> list[str]:
    """Names (as typed) that are not in the ingredients table yet. Case does not matter."""
    names = list(names)
    if not names:
        return []
    rows = await db.fetch_all(
        "SELECT lower(name) AS n FROM ingredients WHERE lower(name) = ANY(%s)", ([n.lower() for n in names],)
    )
    known = {r["n"] for r in rows}
    return [n for n in names if n.lower() not in known]


async def _save_ingredients(conn, meal_id: int, items: list[tuple[str, Decimal, str | None]], allergens: dict) -> None:
    """Replace the ingredient list of a meal. New ingredients are created with the allergen the owner chose."""
    await conn.execute("DELETE FROM meal_ingredients WHERE meal_id = %s", (meal_id,))
    for name, qty, unit in items:
        cur = await conn.execute("SELECT id FROM ingredients WHERE lower(name) = lower(%s)", (name,))
        row = await cur.fetchone()
        if row is None:
            cur = await conn.execute(
                "INSERT INTO ingredients (name, unit, allergen) VALUES (%s, %s, %s) RETURNING id",
                (name, unit or "g", allergens.get(name.lower())),
            )
            row = await cur.fetchone()
        await conn.execute(
            "INSERT INTO meal_ingredients (meal_id, ingredient_id, quantity) VALUES (%s, %s, %s)",
            (meal_id, row["id"], qty),
        )


async def create_meal(data: dict, items: list[tuple[str, Decimal, str | None]], allergens: dict) -> dict:
    """Add a meal with an automatic meal code (FR-A2). Everything is saved together or not at all."""
    async with db.transaction() as conn:
        await conn.execute("SELECT pg_advisory_xact_lock(60061)")  # two owners adding at once get different codes
        cur = await conn.execute(
            "SELECT COALESCE(max(substring(meal_code from 3)::int), 0) AS top FROM meals WHERE meal_code ~ '^M-[0-9]+$'"
        )
        code = owner_rules.next_meal_code((await cur.fetchone())["top"])
        cur = await conn.execute(
            """
            INSERT INTO meals (meal_code, name, category_id, price_etb, calories, protein_g, carbs_g, fat_g,
                               description, recipe, photo_file_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, meal_code
            """,
            (
                code, data["name"], data["category_id"], data["price"], data["calories"],
                data["protein"], data["carbs"], data["fat"],
                data.get("description") or None, data.get("recipe") or None, data.get("photo"),
            ),
        )
        meal = await cur.fetchone()
        await _save_ingredients(conn, meal["id"], items, allergens)
    return dict(meal)


async def update_meal_field(meal_id: int, field: str, value) -> bool:
    if field not in _MEAL_FIELDS:
        raise ValueError(f"Meal field not editable: {field}")
    row = await db.fetch_one(
        f"UPDATE meals SET {field} = %s, updated_at = now() WHERE id = %s RETURNING id", (value, meal_id)
    )
    return row is not None


async def update_meal_macros(meal_id: int, calories: int, protein, carbs, fat) -> bool:
    row = await db.fetch_one(
        """
        UPDATE meals SET calories = %s, protein_g = %s, carbs_g = %s, fat_g = %s, updated_at = now()
        WHERE id = %s RETURNING id
        """,
        (calories, protein, carbs, fat, meal_id),
    )
    return row is not None


async def replace_meal_ingredients(meal_id: int, items: list[tuple[str, Decimal, str | None]], allergens: dict) -> bool:
    async with db.transaction() as conn:
        cur = await conn.execute("SELECT id FROM meals WHERE id = %s FOR UPDATE", (meal_id,))
        if await cur.fetchone() is None:
            return False
        await _save_ingredients(conn, meal_id, items, allergens)
        await conn.execute("UPDATE meals SET updated_at = now() WHERE id = %s", (meal_id,))
    return True


async def toggle_meal_active(meal_id: int) -> bool | None:
    """Hide a meal from customers, or show it again. Returns the new is_active value."""
    row = await db.fetch_one(
        "UPDATE meals SET is_active = NOT is_active, updated_at = now() WHERE id = %s RETURNING is_active",
        (meal_id,),
    )
    return None if row is None else row["is_active"]


# ---------- broadcasts (FR-A4) ----------


async def audience_counts() -> dict:
    row = await db.fetch_one(
        """
        SELECT count(*) AS everyone,
               count(*) FILTER (WHERE EXISTS (
                   SELECT 1 FROM orders o
                   WHERE o.customer_id = u.id AND o.created_at >= now() - interval '30 days'
                     AND o.status NOT IN ('expired', 'cancelled'))) AS active
        FROM users u WHERE u.signup_complete
        """
    )
    return dict(row)


async def audience(kind: str, phones: list[str] | None = None) -> list[int]:
    """Telegram IDs of the customers who should get a broadcast."""
    if kind == "all":
        rows = await db.fetch_all("SELECT tg_user_id FROM users WHERE signup_complete ORDER BY id")
    elif kind == "active":
        rows = await db.fetch_all(
            """
            SELECT u.tg_user_id FROM users u
            WHERE u.signup_complete AND EXISTS (
                SELECT 1 FROM orders o
                WHERE o.customer_id = u.id AND o.created_at >= now() - interval '30 days'
                  AND o.status NOT IN ('expired', 'cancelled'))
            ORDER BY u.id
            """
        )
    elif kind == "some":
        rows = await db.fetch_all(
            "SELECT tg_user_id FROM users WHERE signup_complete AND phone = ANY(%s) ORDER BY id", (phones or [],)
        )
    else:
        rows = []
    return [r["tg_user_id"] for r in rows]


async def matched_phones(phones: list[str]) -> set[str]:
    rows = await db.fetch_all(
        "SELECT phone FROM users WHERE signup_complete AND phone = ANY(%s)", (phones,)
    )
    return {r["phone"] for r in rows}


async def log_broadcast(sent_by: int, text: str | None, photo: str | None, delivered: int) -> None:
    await db.execute(
        "INSERT INTO broadcasts (sent_by, text, photo_file_id, recipient_count) VALUES (%s, %s, %s, %s)",
        (sent_by, text, photo, delivered),
    )


# ---------- reports (FR-A5) ----------


async def report(start: datetime, end: datetime) -> dict:
    """Numbers for one period. Orders belong to the day they were placed (Addis Ababa time).

    Revenue counts only orders whose payment was approved and that were not refunded.
    """
    confirmed = list(owner_rules.CONFIRMED_STATUSES)
    params = {"s": start, "e": end, "ok": confirmed}
    totals = await db.fetch_one(
        """
        SELECT count(*) AS placed,
               count(*) FILTER (WHERE status = ANY(%(ok)s)) AS confirmed,
               COALESCE(sum(total_etb) FILTER (WHERE status = ANY(%(ok)s)), 0) AS revenue,
               COALESCE(sum(delivery_fee_etb) FILTER (WHERE status = ANY(%(ok)s)), 0) AS fees,
               count(*) FILTER (WHERE status = 'delivered') AS delivered,
               count(*) FILTER (WHERE status = 'refunded') AS refunded,
               COALESCE(sum(total_etb) FILTER (WHERE status = 'refunded'), 0) AS refunded_etb,
               count(*) FILTER (WHERE status = 'refund_needed') AS refund_waiting,
               count(*) FILTER (WHERE status IN ('expired', 'cancelled')) AS closed_unpaid,
               count(DISTINCT customer_id) FILTER (WHERE status = ANY(%(ok)s)) AS customers
        FROM orders WHERE created_at >= %(s)s AND created_at < %(e)s
        """,
        params,
    )
    denied = await db.fetch_one(
        """
        SELECT count(*) AS n FROM payments p JOIN orders o ON o.id = p.order_id
        WHERE p.status = 'denied' AND o.created_at >= %(s)s AND o.created_at < %(e)s
        """,
        params,
    )
    top = await db.fetch_all(
        """
        SELECT oi.meal_code, oi.meal_name, sum(oi.quantity)::int AS qty
        FROM order_items oi JOIN orders o ON o.id = oi.order_id
        WHERE o.created_at >= %(s)s AND o.created_at < %(e)s AND o.status = ANY(%(ok)s)
        GROUP BY oi.meal_code, oi.meal_name
        ORDER BY qty DESC, oi.meal_code LIMIT 5
        """,
        params,
    )
    result = dict(totals)
    result["denied"] = denied["n"]
    result["top"] = top
    return result
