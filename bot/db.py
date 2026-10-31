"""PostgreSQL access through an async connection pool (works locally and on Neon)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Iterable

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

_pool: AsyncConnectionPool | None = None


async def open_pool(dsn: str) -> None:
    global _pool
    _pool = AsyncConnectionPool(
        conninfo=dsn,
        min_size=1,
        max_size=5,
        open=False,
        kwargs={"row_factory": dict_row, "autocommit": True},
        check=AsyncConnectionPool.check_connection,  # drops dead connections (Neon sleeps when idle)
        max_idle=240,
        max_lifetime=1800,
    )
    await _pool.open(wait=True, timeout=30)


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _get_pool() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("Database pool is not open")
    return _pool


async def fetch_all(query: str, params: Iterable[Any] | None = None) -> list[dict]:
    async with _get_pool().connection() as conn:
        cur = await conn.execute(query, params)
        return await cur.fetchall()


async def fetch_one(query: str, params: Iterable[Any] | None = None) -> dict | None:
    async with _get_pool().connection() as conn:
        cur = await conn.execute(query, params)
        return await cur.fetchone()


async def execute(query: str, params: Iterable[Any] | None = None) -> None:
    async with _get_pool().connection() as conn:
        await conn.execute(query, params)


@asynccontextmanager
async def transaction() -> AsyncIterator[Any]:
    """Several statements that succeed or fail together.

        async with db.transaction() as conn:
            cur = await conn.execute("...", params)
            row = await cur.fetchone()

    Leaving the block normally commits; an exception rolls everything back.
    """
    async with _get_pool().connection() as conn:
        async with conn.transaction():
            yield conn


async def get_setting(key: str, default: str | None = None) -> str | None:
    row = await fetch_one("SELECT value FROM settings WHERE key = %s", (key,))
    return row["value"] if row else default


async def get_setting_int(key: str, default: int) -> int:
    value = await get_setting(key)
    try:
        return int(value) if value is not None else default
    except ValueError:
        return default


async def ensure_owners(owner_ids: Iterable[int]) -> None:
    """Make sure every ID listed in ADMIN_IDS exists in the staff table as an active owner."""
    for tg_id in owner_ids:
        await execute(
            """
            INSERT INTO staff (tg_user_id, name, role) VALUES (%s, 'Owner', 'owner')
            ON CONFLICT (tg_user_id) DO UPDATE SET role = 'owner', is_active = TRUE
            """,
            (tg_id,),
        )
