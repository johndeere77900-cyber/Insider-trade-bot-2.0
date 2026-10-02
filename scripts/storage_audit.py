"""
Storage Audit & Diagnostic Tool for Insider Trade Bot 2.0.

Reports:
- Database total size
- Table sizes & index sizes
- Row counts
- Provenance breakdown by record_type
- raw_payload statistics (count, sum, average character length)
- Estimated storage per transaction (current vs optimized)
- Projected storage requirements for historical ranges:
    * 2006-Q1 -> 2010-Q4 (20 quarters)
    * 2006-Q1 -> 2020-Q4 (60 quarters)
    * 2006-Q1 -> current (81 quarters)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.environment import load_environment
from database.connection import connect, get_database_path, initialize_database, is_postgresql_url, is_sqlite_url


def run_storage_audit(database_url: str) -> dict:
    initialize_database(database_url)
    print("================ DATABASE STORAGE AUDIT ================\n")

    audit_data = {}

    with connect(database_url) as conn:
        if is_postgresql_url(database_url):
            # PostgreSQL database size
            row = conn.execute("SELECT pg_database_size(current_database())").fetchone()
            db_size_bytes = row[0] if row else 0

            # Relation sizes
            tables = ["insider_transactions", "provenance", "ingestion_state", "market_prices", "corporate_actions", "research_events", "signals", "trade_runs"]
            table_stats = {}
            for t in tables:
                r = conn.execute(
                    "SELECT pg_total_relation_size(%s), pg_table_size(%s), pg_indexes_size(%s)", (t, t, t)
                ).fetchone()
                if r:
                    table_stats[t] = {
                        "total_bytes": r[0],
                        "table_bytes": r[1],
                        "index_bytes": r[2],
                    }

            # Index detail for insider_transactions & provenance
            index_sql = """
                SELECT indexrelname, pg_relation_size(indexrelid)
                FROM pg_stat_user_indexes
                WHERE relname IN ('insider_transactions', 'provenance')
                ORDER BY relname, indexrelname;
            """
            indexes_detail = conn.execute(index_sql).fetchall()

            # Row counts
            it_rows = conn.execute("SELECT COUNT(*) FROM insider_transactions").fetchone()[0]
            prov_rows = conn.execute("SELECT COUNT(*) FROM provenance").fetchone()[0]

            # Provenance breakdown
            prov_breakdown = conn.execute(
                "SELECT record_type, COUNT(*) FROM provenance GROUP BY record_type"
            ).fetchall()

            # raw_payload statistics
            raw_stats = conn.execute(
                """
                SELECT COUNT(raw_payload), COALESCE(SUM(LENGTH(raw_payload)), 0), COALESCE(AVG(LENGTH(raw_payload)), 0)
                FROM insider_transactions
                WHERE raw_payload IS NOT NULL AND raw_payload != ''
                """
            ).fetchone()

        else:
            # SQLite fallback
            db_path = get_database_path(database_url)
            db_size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0

            table_stats = {}
            for t in ["insider_transactions", "provenance", "ingestion_state"]:
                c = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                table_stats[t] = {"total_bytes": 0, "table_bytes": 0, "index_bytes": 0, "count": c}

            indexes_detail = []
            it_rows = table_stats["insider_transactions"]["count"]
            prov_rows = table_stats["provenance"]["count"]

            prov_breakdown = conn.execute(
                "SELECT record_type, COUNT(*) FROM provenance GROUP BY record_type"
            ).fetchall()

            raw_stats = conn.execute(
                """
                SELECT COUNT(raw_payload), COALESCE(SUM(LENGTH(raw_payload)), 0), COALESCE(AVG(LENGTH(raw_payload)), 0)
                FROM insider_transactions
                WHERE raw_payload IS NOT NULL AND raw_payload != ''
                """
            ).fetchone()

    raw_count = raw_stats[0] if raw_stats else 0
    raw_sum_bytes = raw_stats[1] if raw_stats else 0
    raw_avg_chars = float(raw_stats[2]) if raw_stats else 0.0

    print(f"Database Total Size: {db_size_bytes / (1024 * 1024):.2f} MB ({db_size_bytes:,} bytes)")
    print(f"insider_transactions Rows: {it_rows:,}")
    print(f"provenance Rows: {prov_rows:,}\n")

    print("TABLE & INDEX BREAKDOWN:")
    for t_name, s in table_stats.items():
        if s["total_bytes"] > 0:
            print(f"  {t_name:22s} Total: {s['total_bytes'] / (1024 * 1024):.2f} MB | Table: {s['table_bytes'] / (1024 * 1024):.2f} MB | Indexes: {s['index_bytes'] / (1024 * 1024):.2f} MB")
    print()

    if indexes_detail:
        print("INDEX DETAILS:")
        for idx_name, idx_size in indexes_detail:
            print(f"  {idx_name:55s} {idx_size / (1024 * 1024):.2f} MB ({idx_size:,} bytes)")
        print()

    print("PROVENANCE BREAKDOWN BY RECORD TYPE:")
    prov_dict = {}
    for r_type, count in prov_breakdown:
        prov_dict[r_type] = count
        print(f"  {r_type:25s}: {count:,} rows")
    print()

    print("RAW_PAYLOAD STATISTICS:")
    print(f"  Rows with raw_payload:    {raw_count:,}")
    print(f"  Total raw_payload size:   {raw_sum_bytes / (1024 * 1024):.2f} MB ({raw_sum_bytes:,} bytes)")
    print(f"  Average raw_payload size: {raw_avg_chars:.1f} characters/bytes\n")

    # Metrics & Projections
    # Calculate empirical per-transaction storage using current database findings:
    # 379,581 transactions in 2 quarters (2006-Q1 & 2006-Q2) = ~189,790 transactions / quarter.
    # Total Current Storage in Neon for 379,581 rows:
    # - insider_transactions table: 579 MB
    # - duplicate unique index (idx_insider_tx_uniq): 68 MB
    # - primary unique index: 68 MB
    # - date index: 91 MB
    # - per-transaction provenance table: 124 MB
    # - per-transaction provenance index: 68 MB
    # Total current per transaction = ~2,180 bytes/tx.

    # Optimized per transaction (after storage repair):
    # - insider_transactions table (with normalized fields + raw_payload): ~1,525 bytes/tx
    # - single UNIQUE index: ~179 bytes/tx
    # - date index: ~240 bytes/tx
    # - dataset-level provenance (negligible, ~1 row per quarter)
    # Total optimized per transaction = ~1,944 bytes/tx (~1.9 KB / transaction).
    #
    # If raw_payload is decoupled / archived out of Neon:
    # - insider_transactions table (without raw_payload): ~250 bytes/tx
    # - single UNIQUE index: ~179 bytes/tx
    # - date index: ~240 bytes/tx
    # Total archived per transaction = ~669 bytes/tx (~0.67 KB / transaction).

    tx_per_quarter = 189790

    # Current rate (with redundant index & per-tx provenance): ~2.18 KB/tx
    # Optimized Neon rate (duplicate index removed, no per-tx provenance, raw_payload retained): ~1.94 KB/tx
    # Archived rate (raw_payload offloaded to cold storage, normalized only in Neon): ~0.67 KB/tx

    bytes_per_tx_current = 2180
    bytes_per_tx_repaired = 1944
    bytes_per_tx_archived = 669

    print("STORAGE PROJECTIONS (Based on empirical ~189,790 txs / quarter):")
    ranges = [
        ("2006-Q1 -> 2010-Q4 (20 quarters / ~3.8M txs)", 20),
        ("2006-Q1 -> 2020-Q4 (60 quarters / ~11.4M txs)", 60),
        ("2006-Q1 -> 2026-Q2 (82 quarters / ~15.5M txs)", 82),
    ]

    for label, qtrs in ranges:
        total_txs = qtrs * tx_per_quarter
        mb_current = (total_txs * bytes_per_tx_current) / (1024 * 1024)
        mb_repaired = (total_txs * bytes_per_tx_repaired) / (1024 * 1024)
        mb_archived = (total_txs * bytes_per_tx_archived) / (1024 * 1024)
        print(f"  {label}:")
        print(f"    - Current Bloated Architecture: {mb_current:,.0f} MB ({mb_current/1024:.2f} GB)")
        print(f"    - Repaired (Duplicates/Prov Removed, raw_payload in Neon): {mb_repaired:,.0f} MB ({mb_repaired/1024:.2f} GB)")
        print(f"    - Repaired + Cold Archive (raw_payload in S3/disk):       {mb_archived:,.0f} MB ({mb_archived/1024:.2f} GB)")
    print("========================================================\n")

    audit_data.update({
        "database_size_bytes": db_size_bytes,
        "insider_transactions_count": it_rows,
        "provenance_count": prov_rows,
        "provenance_breakdown": prov_dict,
        "raw_payload_count": raw_count,
        "raw_payload_total_bytes": raw_sum_bytes,
        "raw_payload_avg_chars": raw_avg_chars,
        "table_stats": table_stats,
    })

    return audit_data


def main() -> int:
    parser = argparse.ArgumentParser(description="Storage Audit & Diagnostics for Insider Trade Bot.")
    parser.add_argument("--database-url", default="", help="Database URL to audit.")
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
        run_storage_audit(db_url)
        return 0
    except Exception as exc:
        print(f"ERROR: Storage audit failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
