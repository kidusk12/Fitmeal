"""Kitchen actions on orders (SRS FR-K2 to FR-K11).

Every change is one atomic statement or transaction that only succeeds from the expected
status, so two staff members tapping at the same moment can never both win.
"""
from __future__ import annotations

from datetime import date, datetime

from .. import db
from . import flow

_QUEUES = {
    "review": ("o.status = 'payment_review'", "o.review_started_at"),
    "overdue": (
        "o.status = 'payment_review' AND o.review_started_at + make_interval(mins => %(rm)s::int) <= now()",
        "o.review_started_at",
    ),
    "cook": ("o.status IN ('confirmed', 'preparing', 'ready')", "o.delivery_time NULLS LAST, o.id"),
    "delivery": ("o.status = 'out_for_delivery'", "o.delivery_time NULLS LAST, o.id"),
    "refunds": ("o.status = 'refund_needed'", "o.updated_at"),
}
QUEUE_NAMES = tuple(_QUEUES)


async def queue_counts(review_min: int) -> dict:
    row = await db.fetch_one(
        """
        SELECT count(*) FILTER (WHERE status = 'payment_review') AS review,
               count(*) FILTER (WHERE status = 'payment_review'
                                  AND review_started_at + make_interval(mins => %s::int) <= now()) AS overdue,
               count(*) FILTER (WHERE status IN ('confirmed', 'preparing', 'ready')) AS cook,
               count(*) FILTER (WHERE status = 'out_for_delivery') AS delivery,
               count(*) FILTER (WHERE status = 'refund_needed') AS refunds
        FROM orders
        WHERE status IN ('payment_review', 'confirmed', 'preparing', 'ready', 'out_for_delivery', 'refund_needed')
        """,
        (review_min,),
    )
    return dict(row)


async def queue_list(queue: str, review_min: int, limit: int = 15) -> list[dict]:
    where, order = _QUEUES[queue]
    return await db.fetch_all(
        "SELECT o.id, o.order_code, o.status, o.total_etb, o.delivery_time, u.full_name "
        "FROM orders o JOIN users u ON u.id = o.customer_id "
        "WHERE " + where + " ORDER BY " + order + " LIMIT %(lim)s",
        {"rm": review_min, "lim": limit},
    )


async def get_order(order_id: int) -> dict | None:
    return await db.fetch_one(
        """
        SELECT o.id, o.order_code, o.status, o.subtotal_etb, o.delivery_fee_etb, o.total_etb,
               o.dest_text, o.dest_latitude, o.dest_longitude, o.dest_maps_url,
               o.receiver_name, o.receiver_phone, o.delivery_time, o.created_at,
               o.review_started_at, o.cancel_reason,
               u.tg_user_id, u.full_name, u.phone
        FROM orders o JOIN users u ON u.id = o.customer_id
        WHERE o.id = %s
        """,
        (order_id,),
    )


async def latest_payment(order_id: int) -> dict | None:
    return await db.fetch_one(
        "SELECT id, telegram_file_id, status, reason FROM payments WHERE order_id = %s ORDER BY id DESC LIMIT 1",
        (order_id,),
    )


async def _event(conn, order_id: int, status: str, staff_id: int, note: str) -> None:
    await conn.execute(
        "INSERT INTO order_events (order_id, status, actor_type, actor_tg_id, note) VALUES (%s, %s, 'staff', %s, %s)",
        (order_id, status, staff_id, note),
    )


async def approve(order_id: int, staff_id: int, delivery_time: datetime) -> bool:
    """Payment Review -> Confirmed, with the delivery time the customer will see (FR-K4)."""
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            UPDATE orders SET status = 'confirmed', delivery_time = %s, updated_at = now()
            WHERE id = %s AND status = 'payment_review' RETURNING id
            """,
            (delivery_time, order_id),
        )
        if await cur.fetchone() is None:
            return False
        await conn.execute(
            """
            UPDATE payments SET status = 'approved', reviewed_by = %s, reviewed_at = now()
            WHERE id = (SELECT max(id) FROM payments WHERE order_id = %s)
            """,
            (staff_id, order_id),
        )
        await _event(conn, order_id, "confirmed", staff_id, "Payment approved")
    return True


async def deny(order_id: int, staff_id: int, reason: str, allow_resend: bool) -> bool:
    """Payment Review -> Payment Denied, with a reason the customer sees (FR-K5, FR-P5)."""
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            UPDATE orders SET status = 'payment_denied', updated_at = now()
            WHERE id = %s AND status = 'payment_review' RETURNING id
            """,
            (order_id,),
        )
        if await cur.fetchone() is None:
            return False
        await conn.execute(
            """
            UPDATE payments SET status = 'denied', reason = %s, allow_resend = %s,
                                reviewed_by = %s, reviewed_at = now()
            WHERE id = (SELECT max(id) FROM payments WHERE order_id = %s)
            """,
            (reason, allow_resend, staff_id, order_id),
        )
        await _event(conn, order_id, "payment_denied", staff_id, "Payment denied: " + reason)
    return True


async def advance(order_id: int, staff_id: int, new_status: str) -> bool:
    """Move exactly one step forward, e.g. Confirmed -> Preparing (FR-K6)."""
    previous = flow.previous_status(new_status)
    if previous is None:
        return False
    async with db.transaction() as conn:
        cur = await conn.execute(
            "UPDATE orders SET status = %s, updated_at = now() WHERE id = %s AND status = %s RETURNING id",
            (new_status, order_id, previous),
        )
        if await cur.fetchone() is None:
            return False
        await _event(conn, order_id, new_status, staff_id, "Status set by kitchen")
    return True


async def cancel_for_refund(order_id: int, staff_id: int, reason: str) -> bool:
    """The kitchen cannot fulfil a paid order: Refund Needed (FR-K9)."""
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            UPDATE orders SET status = 'refund_needed', cancel_reason = %s, updated_at = now()
            WHERE id = %s AND status = ANY(%s) RETURNING id
            """,
            (reason, order_id, list(flow.CANCELLABLE_BY_KITCHEN)),
        )
        if await cur.fetchone() is None:
            return False
        await _event(conn, order_id, "refund_needed", staff_id, "Cancelled by kitchen: " + reason)
    return True


async def mark_refunded(order_id: int, staff_id: int, method: str, reference: str | None) -> dict | None:
    """Refund Needed -> Refunded, and write the refund log entry (FR-K9). Money is sent by hand."""
    async with db.transaction() as conn:
        cur = await conn.execute(
            "UPDATE orders SET status = 'refunded', updated_at = now() WHERE id = %s AND status = 'refund_needed' RETURNING total_etb",
            (order_id,),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        await conn.execute(
            "INSERT INTO refunds (order_id, amount_etb, method, reference, logged_by) VALUES (%s, %s, %s, %s, %s)",
            (order_id, row["total_etb"], method, reference, staff_id),
        )
        await _event(conn, order_id, "refunded", staff_id, "Refund sent via " + method + (" " + reference if reference else ""))
    return {"total": row["total_etb"]}


async def recipes_for(order_id: int) -> list[dict]:
    """Recipes of the meals in an order. Kitchen only; shown on request (FR-K7)."""
    return await db.fetch_all(
        """
        SELECT DISTINCT oi.meal_code, oi.meal_name, m.recipe
        FROM order_items oi JOIN meals m ON m.id = oi.meal_id
        WHERE oi.order_id = %s ORDER BY oi.meal_code
        """,
        (order_id,),
    )


async def meals_for_toggle() -> list[dict]:
    return await db.fetch_all(
        "SELECT id, meal_code, name, sold_out_on FROM meals WHERE is_active ORDER BY meal_code"
    )


async def toggle_sold_out(meal_id: int, today: date) -> None:
    """Mark a meal sold out for today, or put it back on sale (FR-K11)."""
    await db.execute(
        """
        UPDATE meals SET sold_out_on = CASE WHEN sold_out_on = %s THEN NULL ELSE %s END, updated_at = now()
        WHERE id = %s
        """,
        (today, today, meal_id),
    )
