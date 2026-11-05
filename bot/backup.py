"""Backups (Phase 8): writes the whole database to one .sql file.

    python -m bot.backup            make a backup in the backups folder
    python -m bot.backup --send     also send it to the owner(s) on Telegram

The file holds INSERT statements, so it needs no pg_dump and works on any PostgreSQL. Restore it
with:  python -m bot.restore <file>.   Every backup contains customer data: keep the folder private.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg
from psycopg import sql

from .services import opsrules

log = logging.getLogger("fitmeal.backup")

ROOT = Path(__file__).resolve().parent.parent
HEADER = "-- FITMEAL-BACKUP v1"


def default_folder() -> Path:
    return Path(os.getenv("BACKUP_DIR", "").strip() or ROOT / "backups")


def _literal(conn, value) -> str:
    return sql.Literal(value).as_string(conn)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def dump_sql(dsn: str, now: datetime | None = None) -> tuple[str, dict[str, int]]:
    """Reads every table in one consistent snapshot. Returns (file text, rows per table)."""
    now = now or datetime.now().astimezone()
    with psycopg.connect(dsn) as conn:
        conn.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        conn.read_only = True
        tables = [r[0] for r in conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()]
        fks = [(r[0], r[1]) for r in conn.execute(
            """
            SELECT c.relname, p.relname
            FROM pg_constraint k
            JOIN pg_class c ON c.oid = k.conrelid
            JOIN pg_class p ON p.oid = k.confrelid
            WHERE k.contype = 'f' AND c.relnamespace = 'public'::regnamespace
            """).fetchall()]
        ordered = opsrules.order_tables(tables, fks)

        out = [HEADER, "-- Created: " + now.isoformat(timespec="seconds"),
               "-- Tables: " + ", ".join(ordered), "BEGIN;"]
        if ordered:
            out.append("TRUNCATE TABLE " + ", ".join(_quote(t) for t in ordered) + " RESTART IDENTITY CASCADE;")
        counts: dict[str, int] = {}
        counters: list[str] = []
        for table in ordered:
            cur = conn.execute(sql.SQL("SELECT * FROM {}").format(sql.Identifier(table)))
            columns = [d.name for d in cur.description]
            rows = cur.fetchall()
            counts[table] = len(rows)
            column_list = ", ".join(_quote(c) for c in columns)
            for row in rows:
                values = ", ".join(_literal(conn, v) for v in row)
                out.append("INSERT INTO {} ({}) OVERRIDING SYSTEM VALUE VALUES ({});".format(_quote(table), column_list, values))
            for (column,) in conn.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                  AND (is_identity = 'YES' OR column_default LIKE 'nextval%%')
                """, (table,)).fetchall():
                counters.append(
                    "SELECT setval(pg_get_serial_sequence('{t}', '{raw}'), COALESCE(max({c}), 1), max({c}) IS NOT NULL) FROM {t};".format(
                        t=_quote(table), c=_quote(column), raw=column.replace("'", "''")))
        out.extend(counters)
        out.append("COMMIT;")
    return "\n".join(out) + "\n", counts


def make_backup(dsn: str, folder: Path | None = None, keep: int = 14, tz=None) -> tuple[Path, dict[str, int]]:
    folder = Path(folder or default_folder())
    folder.mkdir(parents=True, exist_ok=True)
    now = datetime.now(tz) if tz else datetime.now().astimezone()
    text, counts = dump_sql(dsn, now)
    path = folder / now.strftime("fitmeal-%Y%m%d-%H%M%S.sql")
    path.write_text(text, encoding="utf-8")
    for name in opsrules.files_to_delete([p.name for p in folder.iterdir()], keep):
        try:
            (folder / name).unlink()
        except OSError as exc:
            log.warning("Could not delete old backup %s: %s", name, exc)
    log.info("Backup written: %s (%s rows)", path.name, sum(counts.values()))
    return path, counts


async def make_backup_async(dsn: str, folder: Path | None = None, keep: int = 14, tz=None):
    return await asyncio.to_thread(make_backup, dsn, folder, keep, tz)


def latest_backup(folder: Path | None = None) -> Path | None:
    folder = Path(folder or default_folder())
    if not folder.is_dir():
        return None
    names = sorted(n for n in os.listdir(folder) if n.startswith("fitmeal-") and n.endswith(".sql"))
    return folder / names[-1] if names else None


async def _send(cfg, path: Path, counts: dict[str, int]) -> None:
    from telegram import Bot

    async with Bot(cfg.bot_token) as bot:
        for owner_id in cfg.owner_ids:
            with open(path, "rb") as handle:
                await bot.send_document(owner_id, handle, filename=path.name,
                                        caption="FitMeal backup, {} rows.".format(sum(counts.values())))


def main() -> None:
    from .config import load_config

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cfg = load_config()
    path, counts = make_backup(cfg.database_url, keep=int(os.getenv("BACKUP_KEEP", "14") or 14), tz=cfg.timezone)
    print("Backup saved to " + str(path))
    for table, number in counts.items():
        print("  {}: {}".format(table, number))
    if "--send" in sys.argv:
        asyncio.run(_send(cfg, path, counts))
        print("Sent to the owner(s) on Telegram.")


if __name__ == "__main__":
    main()
