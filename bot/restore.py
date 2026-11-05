"""Restore a backup made by bot.backup (Phase 8).

    python -m bot.restore backups\\fitmeal-20261104-030000.sql
    python -m bot.restore backups\\fitmeal-20261104-030000.sql --url postgresql://user:pass@host/dbname

Without --url it restores into the database in .env (DATABASE_URL). It REPLACES everything in the
target database, so try it on an empty scratch database first. Stop the bot before restoring.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg.conninfo import conninfo_to_dict

from .backup import HEADER

ROOT = Path(__file__).resolve().parent.parent


def check_header(text: str) -> bool:
    return text.startswith(HEADER)


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m bot.restore")
    parser.add_argument("file", help="backup file made by bot.backup")
    parser.add_argument("--url", default="", help="database to restore into (default: DATABASE_URL in .env)")
    options = parser.parse_args()
    path = Path(options.file)
    if not path.is_file():
        raise SystemExit("File not found: " + str(path))
    text = path.read_text(encoding="utf-8")
    if not check_header(text):
        raise SystemExit("This does not look like a FitMeal backup file.")

    load_dotenv(ROOT / ".env")
    dsn = options.url.strip() or os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("No database: set DATABASE_URL in .env or pass --url")

    info = conninfo_to_dict(dsn)
    print("Backup file : " + path.name)
    print("Restore into: database '{}' on host '{}'".format(info.get("dbname", "?"), info.get("host", "?")))
    print("This REPLACES ALL DATA in that database. The bot must be stopped.")
    if input("Type YES to continue: ").strip() != "YES":
        raise SystemExit("Cancelled.")

    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute((ROOT / "schema.sql").read_text(encoding="utf-8"))   # makes the tables if the database is empty
        conn.execute(text)                                                # one transaction: all or nothing
        for table in ("users", "orders", "meals", "payments", "refunds"):
            try:
                count = conn.execute("SELECT count(*) FROM " + table).fetchone()[0]
                print("  {}: {} rows".format(table, count))
            except psycopg.Error:
                pass
    print("Restore finished.")


if __name__ == "__main__":
    main()
