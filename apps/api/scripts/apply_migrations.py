"""Applies SQL migrations from packages/db/migrations/ to DATABASE_URL.

Tracks state in a public._migrations table so each file runs at most once.

Usage:
    cd apps/api
    DATABASE_URL=... uv run python scripts/apply_migrations.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = REPO_ROOT / "packages" / "db" / "migrations"

CREATE_LEDGER = """
create table if not exists public._migrations (
  filename text primary key,
  applied_at timestamptz not null default now()
);
"""


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is required.", file=sys.stderr)
        return 2

    if not MIGRATIONS_DIR.is_dir():
        print(f"Migrations dir not found: {MIGRATIONS_DIR}", file=sys.stderr)
        return 2

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        print("No .sql files to apply.")
        return 0

    with psycopg.connect(database_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_LEDGER)
            conn.commit()

            cur.execute("select filename from public._migrations")
            applied = {row[0] for row in cur.fetchall()}

        for path in files:
            name = path.name
            if name in applied:
                print(f"skip   {name}")
                continue
            print(f"apply  {name}")
            sql = path.read_text(encoding="utf-8")
            try:
                with conn.cursor() as cur:
                    cur.execute(sql)
                    cur.execute(
                        "insert into public._migrations (filename) values (%s)",
                        (name,),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
