"""
Storage Migration Maintenance Script.

Safely drops redundant duplicate index idx_insider_tx_uniq from target database (PostgreSQL / SQLite).
Table uniqueness remains enforced by UNIQUE (source, accession_number, record_hash).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.environment import load_environment
from database.connection import connect, is_postgresql_url


def run_migration(database_url: str) -> None:
    print(f"Connecting to database to remove duplicate index idx_insider_tx_uniq...")
    sql = "DROP INDEX IF EXISTS idx_insider_tx_uniq;"

    with connect(database_url) as conn:
        if is_postgresql_url(database_url):
            with conn.cursor() as cursor:
                cursor.execute(sql)
            conn.commit()
        else:
            conn.execute(sql)
            conn.commit()

    print("Migration complete: idx_insider_tx_uniq dropped successfully (if existed).")


def main() -> int:
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        try:
            env = load_environment()
            db_url = env.database_url
        except Exception:
            pass

    if not db_url:
        print("ERROR: DATABASE_URL environment variable is missing or empty.", file=sys.stderr)
        return 1

    try:
        run_migration(db_url)
        return 0
    except Exception as exc:
        print(f"ERROR: Migration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
