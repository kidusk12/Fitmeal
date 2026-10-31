"""Creates the tables and loads the sample data.

Run from the project folder:
    python -m bot.setup_db            create tables and load sample data (safe to repeat)
    python -m bot.setup_db --reset    DELETE EVERYTHING first (development only)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    load_dotenv(ROOT / ".env")
    dsn = os.getenv("DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("DATABASE_URL is missing in .env")

    reset = "--reset" in sys.argv
    if reset:
        answer = input("This will DELETE ALL DATA in the database. Type YES to continue: ")
        if answer.strip() != "YES":
            raise SystemExit("Cancelled.")

    with psycopg.connect(dsn, autocommit=True) as conn:
        if reset:
            conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
            print("Database reset.")
        for name in ("schema.sql", "seed.sql"):
            conn.execute((ROOT / name).read_text(encoding="utf-8"))
            print(f"Applied {name}")
    print("Done.")


if __name__ == "__main__":
    main()
