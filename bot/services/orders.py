"""Creating and cancelling orders (SRS FR-O1 to FR-O7)."""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from .. import db, texts
from . import cart, rules

DEFAULT_OPEN = time(8, 0)
DEFAULT_CLOSE = time(21, 0)
OPEN_STATUSES_FOR_CANCEL = ("awaiting_payment",)  # Phase 4 extends this to payment_review


class OrderRefused(Exception):
    """The order cannot be placed. `message` is safe to show to the customer."""

    def __init__(self, reason: str, message: str):
        super().__init__(reason)
        self.reason = reason
        self.message = message


async def count_today(tz: ZoneInfo) -> int:
    """Orders placed today (Addis Ababa day) that still count toward the daily limit."""
    start, end = rules.day_bounds(datetime.now(tz))
    row = await db.fetch_one(
        """
        SELECT count(*) AS n FROM orders
        WHERE created_at >= %s AND created_at < %s AND status NOT IN ('expired', 'cancelled')
        """,
        (start, end),
    )
    return row["n"]


async def closed_message(tz: ZoneInfo) -> str | None:
    """None if we can take orders right now, otherwise the message to show (FR-O5)."""
    opens = rules.parse_hhmm(await db.get_setting("opening_time"), DEFAULT_OPEN)
    closes = rules.parse_hhmm(await db.get_setting("closing_time"), DEFAULT_CLOSE)
    if not rules.is_open(datetime.now(tz).time(), opens, closes):
        return texts.CLOSED.format(opens=opens.strftime("%H:%M"), closes=closes.strftime("%H:%M"))
    limit = await db.get_setting_int("daily_order_limit", 100)
    if await count_today(tz) >= limit:
        return texts.LIMIT_REACHED
    return None


async def quote(user_id: int, tz: ZoneInfo) -> dict:
    """Cart lines, subtotal, flat delivery fee and total (FR-O1)."""
    items = await cart.list_items(user_id)
    today = datetime.now(tz).date()
    fee = await db.get_setting_int("delivery_fee_etb", 50)
    unavailable = [i for i in items if not (i["is_active"] and i["sold_out_on"] != today)]
    subtotal = sum(i["price_etb"] * i["quantity"] for i in items)
    return {
        "items": items,
        "unavailable": unavailable,
        "subtotal": subtotal,
        "fee": fee,
        "total": subtotal + fee,
    }


async def place_order(
    user_id: int,
    dest: dict,
    receiver: dict,
    tz: ZoneInfo,
    expected_total: int,
) -> dict:
    """Turn the cart into an order. Everything happens in one transaction, so a double tap
    or a crash can never produce half an order or two orders from one cart.

    dest:     {"lat", "lng", "text", "maps_url"}  (lat/lng or text may be None, not both)
    receiver: {"name", "phone"}
    Raises OrderRefused with a customer-safe message when the order cannot go through.
    """
    problem = await closed_message(tz)
    if problem:
        raise OrderRefused("closed", problem)

    fee = await db.get_setting_int("delivery_fee_etb", 50)
    limit = await db.get_setting_int("daily_order_limit", 100)
    now = datetime.now(tz)
    today = now.date()
    day_start, day_end = rules.day_bounds(now)

    async with db.transaction() as conn:
        # Lock this customer's cart rows: a second tap waits here, then finds an empty cart.
        cur = await conn.execute(
            """
            SELECT ci.meal_id, ci.quantity, m.meal_code, m.price_etb, m.is_active, m.sold_out_on
            FROM cart_items ci JOIN meals m ON m.id = ci.meal_id
            WHERE ci.user_id = %s
            FOR UPDATE OF ci
            """,
            (user_id,),
        )
        items = await cur.fetchall()
        if not items:
            raise OrderRefused("empty", texts.CHECKOUT_EMPTY)

        bad = [i["meal_code"] for i in items if not (i["is_active"] and i["sold_out_on"] != today)]
        if bad:
            raise OrderRefused("unavailable", texts.CHECKOUT_UNAVAILABLE.format(names=", ".join(bad)))

        subtotal = sum(i["price_etb"] * i["quantity"] for i in items)
        total = subtotal + fee
        if total != expected_total:
            raise OrderRefused("price_changed", texts.PRICE_CHANGED)

        # The counter row is locked until commit, so two customers can never get the same
        # number, and the daily-limit count below cannot be beaten by a simultaneous order.
        cur = await conn.execute(
            """
            INSERT INTO order_counters (day, last_number) VALUES (%s, 1)
            ON CONFLICT (day) DO UPDATE SET last_number = order_counters.last_number + 1
            RETURNING last_number
            """,
            (today,),
        )
        number = (await cur.fetchone())["last_number"]

        cur = await conn.execute(
            """
            SELECT count(*) AS n FROM orders
            WHERE created_at >= %s AND created_at < %s AND status NOT IN ('expired', 'cancelled')
            """,
            (day_start, day_end),
        )
        if (await cur.fetchone())["n"] >= limit:
            raise OrderRefused("limit", texts.LIMIT_REACHED)

        code = rules.order_code(today, number)
        cur = await conn.execute(
            """
            INSERT INTO orders (
                order_code, customer_id, subtotal_etb, delivery_fee_etb, total_etb,
                dest_latitude, dest_longitude, dest_text, dest_maps_url,
                receiver_name, receiver_phone
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, order_code, status, total_etb
            """,
            (
                code, user_id, subtotal, fee, total,
                dest.get("lat"), dest.get("lng"), dest.get("text"), dest.get("maps_url"),
                receiver["name"], receiver["phone"],
            ),
        )
        order = await cur.fetchone()

        # Snapshot meal code, name and price so later menu edits never change old orders.
        await conn.execute(
            """
            INSERT INTO order_items (order_id, meal_id, meal_code, meal_name, quantity, unit_price_etb, note)
            SELECT %s, ci.meal_id, m.meal_code, m.name, ci.quantity, m.price_etb, ci.note
            FROM cart_items ci JOIN meals m ON m.id = ci.meal_id
            WHERE ci.user_id = %s
            """,
            (order["id"], user_id),
        )
        await conn.execute(
            """
            INSERT INTO order_events (order_id, status, actor_type, note)
            VALUES (%s, 'awaiting_payment', 'customer', 'Order placed')
            """,
            (order["id"],),
        )
        await conn.execute("DELETE FROM cart_items WHERE user_id = %s", (user_id,))

    return order


async def order_lines(order_id: int) -> list[dict]:
    return await db.fetch_all(
        """
        SELECT meal_code, meal_name, quantity, unit_price_etb, note
        FROM order_items WHERE order_id = %s ORDER BY id
        """,
        (order_id,),
    )


async def cancel_order(order_id: int, user_id: int, tg_user_id: int) -> str | None:
    """Cancel the customer's own order while payment is not approved (FR-O7).

    Returns the Order ID, or None if the order could not be cancelled (wrong owner or
    already past the point where the customer can cancel).
    """
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            UPDATE orders SET status = 'cancelled', cancel_reason = 'Cancelled by customer', updated_at = now()
            WHERE id = %s AND customer_id = %s AND status = ANY(%s)
            RETURNING order_code
            """,
            (order_id, user_id, list(OPEN_STATUSES_FOR_CANCEL)),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        await conn.execute(
            """
            INSERT INTO order_events (order_id, status, actor_type, actor_tg_id, note)
            VALUES (%s, 'cancelled', 'customer', %s, 'Cancelled by customer')
            """,
            (order_id, tg_user_id),
        )
    return row["order_code"]
