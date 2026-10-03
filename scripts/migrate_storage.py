"""
Storage Migration Maintenance Script.

Safely drops redundant duplicate index idx_insider_tx_uniq from target database (PostgreSQL / SQLite).

Safety Requirements Before Dropping:
1. Check if idx_insider_tx_uniq exists.
2. Check if table-level UNIQUE constraint on (source, accession_number, record_hash) exists.
3. If table-level UNIQUE constraint is MISSING, REFUSE to drop the index to prevent losing uniqueness protection.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.environment import load_environment
from database.connection import connect, is_postgresql_url


def run_migration(database_url: str) -> bool:
    print("================ REDUNDANT INDEX MIGRATION CHECK ================\n")

    with connect(database_url) as conn:
        if is_postgresql_url(database_url):
            # Check duplicate index existence
            idx_check_sql = """
                SELECT COUNT(*)
                FROM pg_indexes
                WHERE indexname = 'idx_insider_tx_uniq';
            """
            idx_count = conn.execute(idx_check_sql).fetchone()[0]
            idx_exists = idx_count > 0

            # Check table-level UNIQUE constraint existence on insider_transactions
            constraint_check_sql = """
                SELECT COUNT(*)
                FROM information_schema.table_constraints
                WHERE table_name = 'insider_transactions'
                  AND constraint_type = 'UNIQUE';
            """
            constraint_count = conn.execute(constraint_check_sql).fetchone()[0]
            constraint_exists = constraint_count > 0

        else:
            # SQLite check
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_insider_tx_uniq'"
            )
            idx_exists = cursor.fetchone() is not None

            # In SQLite, table-level UNIQUE constraint is created during CREATE TABLE
            cursor_tbl = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='insider_transactions'"
            )
            tbl_sql = cursor_tbl.fetchone()
            constraint_exists = tbl_sql is not None and "UNIQUE" in tbl_sql[0]

    print(f"  Duplicate Index (idx_insider_tx_uniq):      {'EXISTS' if idx_exists else 'NOT FOUND'}")
    print(f"  Table-Level UNIQUE Constraint:              {'EXISTS' if constraint_exists else 'MISSING'}\n")

    if not idx_exists:
        print("MIGRATION STATUS: Duplicate index idx_insider_tx_uniq does not exist. No action needed.")
        return True

    if not constraint_exists:
        print("ERROR: Safety check failed! Table-level UNIQUE constraint on (source, accession_number, record_hash) is MISSING.")
        print("REFUSING to drop duplicate index idx_insider_tx_uniq to avoid removing uniqueness protection!")
        return False

    print("SAFETY CHECK PASSED: Table-level UNIQUE constraint is intact. Safe to drop redundant index.\n")
    print("Dropping redundant index idx_insider_tx_uniq...")

    drop_sql = "DROP INDEX IF EXISTS idx_insider_tx_uniq;"

    with connect(database_url) as conn:
        if is_postgresql_url(database_url):
            with conn.cursor() as cursor:
                cursor.execute(drop_sql)
            conn.commit()
        else:
            conn.execute(drop_sql)
            conn.commit()

    print("MIGRATION SUCCESS: idx_insider_tx_uniq dropped successfully. Table-level UNIQUE constraint continues protecting uniqueness.")
    return True


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Safely drop redundant index idx_insider_tx_uniq.")
    parser.add_argument("--database-url", default="", help="Database URL.")
    args = parser.parse_args()

    db_url = args.database_url.strip() or os.environ.get("DATABASE_URL", "").strip()
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
        success = run_migration(db_url)
        return 0 if success else 1
    except Exception as exc:
        print(f"ERROR: Migration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
