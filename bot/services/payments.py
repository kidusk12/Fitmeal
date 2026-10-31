"""Payment screenshots, expiry and kitchen-review timers (SRS FR-P1 to FR-P6).

Every timer is computed from timestamps stored in the database, never from memory, so a
restart cannot lose or reset a countdown (NFR-3).
"""
from __future__ import annotations

from .. import db


async def accounts() -> list[dict]:
    return await db.fetch_all(
        """
        SELECT label, account_number, holder_name FROM payment_accounts
        WHERE is_active ORDER BY sort_order, id
        """
    )


async def candidates(user_id: int) -> list[dict]:
    """Orders that can receive a screenshot right now: still inside the payment window, or
    denied with a resend allowed."""
    return await db.fetch_all(
        """
        SELECT o.id, o.order_code, o.total_etb, o.status
        FROM orders o
        WHERE o.customer_id = %s AND (
            (o.status = 'awaiting_payment' AND o.payment_deadline_at > now())
            OR (o.status = 'payment_denied' AND EXISTS (
                SELECT 1 FROM payments p
                WHERE p.order_id = o.id AND p.status = 'denied' AND p.allow_resend
                  AND p.id = (SELECT max(id) FROM payments WHERE order_id = o.id)
            ))
        )
        ORDER BY o.id
        """,
        (user_id,),
    )


async def has_in_review(user_id: int) -> bool:
    row = await db.fetch_one(
        "SELECT 1 AS x FROM orders WHERE customer_id = %s AND status = 'payment_review' LIMIT 1", (user_id,)
    )
    return row is not None


async def submit_screenshot(order_id: int, user_id: int, file_id: str) -> dict | None:
    """Attach a screenshot and move the order to Payment Review (FR-P2).

    Returns the order with customer contact details, or None if the order can no longer
    take a payment (expired, cancelled, already submitted...). Row-locked, so a late
    screenshot and the expiry job can never both win.
    """
    async with db.transaction() as conn:
        cur = await conn.execute(
            """
            SELECT o.id, o.order_code, o.status, o.total_etb,
                   (o.payment_deadline_at > now()) AS in_time,
                   EXISTS (
                       SELECT 1 FROM payments p
                       WHERE p.order_id = o.id AND p.status = 'denied' AND p.allow_resend
                         AND p.id = (SELECT max(id) FROM payments WHERE order_id = o.id)
                   ) AS can_resend,
                   u.full_name, u.phone
            FROM orders o JOIN users u ON u.id = o.customer_id
            WHERE o.id = %s AND o.customer_id = %s
            FOR UPDATE OF o
            """,
            (order_id, user_id),
        )
        order = await cur.fetchone()
        if order is None:
            return None
        ok = (order["status"] == "awaiting_payment" and order["in_time"]) or (
            order["status"] == "payment_denied" and order["can_resend"]
        )
        if not ok:
            return None
        await conn.execute(
            "INSERT INTO payments (order_id, telegram_file_id) VALUES (%s, %s)", (order_id, file_id)
        )
        # A fresh 30-minute kitchen clock starts now (also after a resend).
        await conn.execute(
            """
            UPDATE orders SET status = 'payment_review', review_started_at = now(),
                              last_alert_at = NULL, updated_at = now()
            WHERE id = %s
            """,
            (order_id,),
        )
        await conn.execute(
            """
            INSERT INTO order_events (order_id, status, actor_type, note)
            VALUES (%s, 'payment_review', 'customer', 'Payment screenshot submitted')
            """,
            (order_id,),
        )
    return order


async def expire_due() -> list[dict]:
    """Close orders whose payment window ran out (FR-P3). One atomic statement."""
    return await db.fetch_all(
        """
        WITH expired AS (
            UPDATE orders SET status = 'expired', updated_at = now()
            WHERE status = 'awaiting_payment'
              AND payment_deadline_at IS NOT NULL AND payment_deadline_at <= now()
            RETURNING id, order_code, customer_id
        ),
        ev AS (
            INSERT INTO order_events (order_id, status, actor_type, note)
            SELECT id, 'expired', 'system', 'No payment screenshot within the payment window' FROM expired
        )
        SELECT e.id, e.order_code, u.tg_user_id
        FROM expired e JOIN users u ON u.id = e.customer_id
        """
    )


async def claim_due_alerts(repeat_min: int) -> list[dict]:
    """Orders in Payment Review that are due another staff alert (FR-P4, FR-K10).

    Claiming sets last_alert_at in the same statement, so each alert is sent exactly once.
    First alert comes `repeat_min` minutes after the screenshot, then every `repeat_min`.
    """
    return await db.fetch_all(
        """
        WITH due AS (
            UPDATE orders SET last_alert_at = now()
            WHERE status = 'payment_review' AND review_started_at IS NOT NULL
              AND now() >= COALESCE(last_alert_at, review_started_at) + make_interval(mins => %s::int)
            RETURNING id, order_code, total_etb, customer_id, review_started_at
        )
        SELECT d.id, d.order_code, d.total_etb,
               EXTRACT(EPOCH FROM (now() - d.review_started_at)) / 60 AS elapsed_min,
               u.tg_user_id, u.full_name, u.phone,
               EXISTS (
                   SELECT 1 FROM order_events ev WHERE ev.order_id = d.id AND ev.note = 'Overdue'
               ) AS already_overdue
        FROM due d JOIN users u ON u.id = d.customer_id
        """,
        (repeat_min,),
    )


async def release_alert(order_id: int) -> None:
    """An alert could not be delivered to anyone: let the next tick try again."""
    await db.execute(
        "UPDATE orders SET last_alert_at = NULL WHERE id = %s AND status = 'payment_review'", (order_id,)
    )


async def mark_overdue(order_id: int) -> None:
    await db.execute(
        """
        INSERT INTO order_events (order_id, status, actor_type, note)
        VALUES (%s, 'payment_review', 'system', 'Overdue')
        """,
        (order_id,),
    )


async def request_refund(order_id: int, user_id: int, tg_user_id: int, review_min: int) -> dict | None:
    """Customer asks for a refund after the kitchen missed its review window (FR-P4)."""
    return await db.fetch_one(
        """
        WITH r AS (
            UPDATE orders SET status = 'refund_needed',
                              cancel_reason = 'Customer requested a refund (payment review overdue)',
                              updated_at = now()
            WHERE id = %s AND customer_id = %s AND status = 'payment_review'
              AND review_started_at + make_interval(mins => %s::int) <= now()
            RETURNING id, order_code, total_etb
        ),
        ev AS (
            INSERT INTO order_events (order_id, status, actor_type, actor_tg_id, note)
            SELECT id, 'refund_needed', 'customer', %s, 'Customer requested a refund after an overdue review' FROM r
        )
        SELECT * FROM r
        """,
        (order_id, user_id, review_min, tg_user_id),
    )


async def order_contact(order_id: int) -> dict | None:
    """Order total and customer contact, for staff alerts."""
    return await db.fetch_one(
        """
        SELECT o.order_code, o.total_etb, u.full_name, u.phone
        FROM orders o JOIN users u ON u.id = o.customer_id WHERE o.id = %s
        """,
        (order_id,),
    )


async def order_view(order_id: int, user_id: int) -> dict | None:
    """Everything the Track screen needs, including the latest payment (FR-T1)."""
    return await db.fetch_one(
        """
        SELECT o.id, o.order_code, o.status, o.subtotal_etb, o.delivery_fee_etb, o.total_etb,
               o.dest_text, o.dest_latitude, o.delivery_time, o.payment_deadline_at, o.review_started_at,
               p.status AS pay_status, p.reason AS pay_reason, p.allow_resend
        FROM orders o
        LEFT JOIN LATERAL (
            SELECT status, reason, allow_resend FROM payments
            WHERE order_id = o.id ORDER BY id DESC LIMIT 1
        ) p ON TRUE
        WHERE o.id = %s AND o.customer_id = %s
        """,
        (order_id, user_id),
    )
