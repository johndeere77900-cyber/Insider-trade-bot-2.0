"""
Storage Migration Maintenance Script.

Safely drops redundant duplicate index idx_insider_tx_uniq from target database (PostgreSQL / SQLite).

Safety Requirements Before Dropping:
1. Check if idx_insider_tx_uniq exists.
2. Check if an EXACT table-level UNIQUE constraint or index on (source, accession_number, record_hash) exists.
3. If the EXACT uniqueness protection on (source, accession_number, record_hash) is MISSING, REFUSE to drop the index to prevent losing uniqueness protection.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.environment import load_environment
from database.connection import connect, is_postgresql_url


def verify_exact_unique_constraint(conn, database_url: str) -> bool:
    """
    Verify that an explicit UNIQUE constraint or index exists on insider_transactions
    covering the EXACT column combination: ('source', 'accession_number', 'record_hash').
    Does NOT accept unrelated UNIQUE constraints (e.g. on accession_number or ticker alone).
    """
    target_columns = {"source", "accession_number", "record_hash"}

    if is_postgresql_url(database_url):
        # PostgreSQL check: query table_constraints joined with key_column_usage
        sql = """
            SELECT
                tc.constraint_name,
                ARRAY_AGG(kcu.column_name::text ORDER BY kcu.ordinal_position) AS cols
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_name = 'insider_transactions'
              AND tc.constraint_type = 'UNIQUE'
              AND tc.constraint_name != 'idx_insider_tx_uniq'
            GROUP BY tc.constraint_name;
        """
        try:
            rows = conn.execute(sql).fetchall()
            for constraint_name, cols in rows:
                if set(cols) == target_columns:
                    return True
        except Exception:
            pass

        # Fallback check via pg_index / pg_attribute
        pg_sql = """
            SELECT
                i.relname AS index_name,
                ARRAY_AGG(a.attname::text) AS cols
            FROM pg_class t
            JOIN pg_index ix ON t.oid = ix.indrelid
            JOIN pg_class i ON i.oid = ix.indexrelid
            JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
            WHERE t.relname = 'insider_transactions'
              AND ix.indisunique = true
              AND i.relname != 'idx_insider_tx_uniq'
            GROUP BY i.relname;
        """
        try:
            rows = conn.execute(pg_sql).fetchall()
            for index_name, cols in rows:
                if set(cols) == target_columns:
                    return True
        except Exception:
            pass

        return False

    else:
        # SQLite check
        # Method 1: Check sqlite_master table SQL definition for UNIQUE (source, accession_number, record_hash)
        try:
            cursor_tbl = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='insider_transactions'"
            )
            tbl_row = cursor_tbl.fetchone()
            if tbl_row and tbl_row[0]:
                tbl_sql = tbl_row[0].lower().replace("\n", " ").replace("  ", " ")
                if "unique" in tbl_sql:
                    # Parse contents inside UNIQUE (...)
                    # e.g. "unique ( source, accession_number, record_hash )"
                    import re
                    matches = re.findall(r"unique\s*\(([^)]+)\)", tbl_sql)
                    for m in matches:
                        cols = {c.strip().strip('"').strip('`').strip("'") for c in m.split(",")}
                        if cols == target_columns:
                            return True
        except Exception:
            pass

        # Method 2: Check PRAGMA index_list & PRAGMA index_info
        try:
            idx_list = conn.execute("PRAGMA index_list('insider_transactions')").fetchall()
            for idx in idx_list:
                idx_name = idx[1]
                is_unique = idx[2]
                if is_unique and idx_name != "idx_insider_tx_uniq":
                    info_rows = conn.execute(f"PRAGMA index_info('{idx_name}')").fetchall()
                    cols = {info[2] for info in info_rows}
                    if cols == target_columns:
                        return True
        except Exception:
            pass

        return False


def run_migration(database_url: str) -> bool:
    print("================ REDUNDANT INDEX MIGRATION CHECK ================\n")

    with connect(database_url) as conn:
        if is_postgresql_url(database_url):
            idx_check_sql = "SELECT COUNT(*) FROM pg_indexes WHERE indexname = 'idx_insider_tx_uniq';"
            idx_count = conn.execute(idx_check_sql).fetchone()[0]
            idx_exists = idx_count > 0
        else:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_insider_tx_uniq'"
            )
            idx_exists = cursor.fetchone() is not None

        exact_constraint_exists = verify_exact_unique_constraint(conn, database_url)

    print(f"  Duplicate Index (idx_insider_tx_uniq):                    {'EXISTS' if idx_exists else 'NOT FOUND'}")
    print(f"  Exact UNIQUE(source, accession_number, record_hash) Protection: {'EXISTS' if exact_constraint_exists else 'MISSING'}\n")

    if not idx_exists:
        print("MIGRATION STATUS: Duplicate index idx_insider_tx_uniq does not exist. No action needed.")
        return True

    if not exact_constraint_exists:
        print("ERROR: Safety check failed! Exact UNIQUE constraint on (source, accession_number, record_hash) is MISSING.")
        print("REFUSING to drop duplicate index idx_insider_tx_uniq to avoid removing uniqueness protection!")
        return False

    print("SAFETY CHECK PASSED: Exact UNIQUE(source, accession_number, record_hash) protection confirmed. Safe to drop redundant index.\n")
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

    print("MIGRATION SUCCESS: idx_insider_tx_uniq dropped successfully. Exact UNIQUE constraint continues protecting transaction uniqueness.")
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
