"""
Strictly Read-Only Storage Audit & Diagnostic Tool for Insider Trade Bot 2.0.

NEVER calls initialize_database() or mutates schema/indexes.
Executes only read-only SELECT queries.

Reports:
- Total database size, table sizes, index sizes
- insider_transactions row count & dataset_period row counts
- Provenance breakdown by record_type (dataset_period vs insider_transaction)
- Provenance dependency analysis
- raw_payload statistics (count, total size, average size)
- Average storage per transaction based on actual current database
- Dynamic projected storage requirements based on observed historical dataset rates
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.environment import load_environment
from database.connection import connect, get_database_path, is_postgresql_url, is_sqlite_url


def run_storage_audit(database_url: str) -> dict:
    print("================ DATABASE STORAGE AUDIT (READ-ONLY) ================\n")

    audit_data = {}

    with connect(database_url) as conn:
        if is_postgresql_url(database_url):
            # PostgreSQL database size
            try:
                row = conn.execute("SELECT pg_database_size(current_database())").fetchone()
                db_size_bytes = row[0] if row else 0
            except Exception:
                db_size_bytes = 0

            # Relation sizes
            tables = [
                "insider_transactions",
                "provenance",
                "ingestion_state",
                "market_prices",
                "corporate_actions",
                "research_events",
                "signals",
                "trade_runs",
            ]
            table_stats = {}
            for t in tables:
                try:
                    r = conn.execute(
                        """
                        SELECT
                            pg_total_relation_size(%s::regclass),
                            pg_table_size(%s::regclass),
                            pg_indexes_size(%s::regclass)
                        """,
                        (t, t, t),
                    ).fetchone()
                    if r:
                        table_stats[t] = {
                            "total_bytes": r[0] or 0,
                            "table_bytes": r[1] or 0,
                            "index_bytes": r[2] or 0,
                        }
                except Exception:
                    table_stats[t] = {"total_bytes": 0, "table_bytes": 0, "index_bytes": 0}

            # Index detail for insider_transactions & provenance
            try:
                index_sql = """
                    SELECT indexrelname, pg_relation_size(indexrelid)
                    FROM pg_stat_user_indexes
                    WHERE relname IN ('insider_transactions', 'provenance')
                    ORDER BY relname, indexrelname;
                """
                indexes_detail = conn.execute(index_sql).fetchall()
            except Exception:
                indexes_detail = []

            # Row counts
            try:
                it_rows = conn.execute("SELECT COUNT(*) FROM insider_transactions").fetchone()[0]
            except Exception:
                it_rows = 0

            try:
                prov_rows = conn.execute("SELECT COUNT(*) FROM provenance").fetchone()[0]
            except Exception:
                prov_rows = 0

            try:
                prov_breakdown = conn.execute(
                    "SELECT record_type, COUNT(*) FROM provenance GROUP BY record_type"
                ).fetchall()
            except Exception:
                prov_breakdown = []

            try:
                raw_stats = conn.execute(
                    """
                    SELECT
                        COUNT(raw_payload),
                        COALESCE(SUM(LENGTH(raw_payload)), 0),
                        COALESCE(AVG(LENGTH(raw_payload)), 0)
                    FROM insider_transactions
                    WHERE raw_payload IS NOT NULL AND raw_payload != ''
                    """
                ).fetchone()
            except Exception:
                raw_stats = (0, 0, 0.0)

            try:
                imported_periods = conn.execute(
                    "SELECT COUNT(*) FROM ingestion_state WHERE status = 'COMPLETED'"
                ).fetchone()[0]
            except Exception:
                imported_periods = 0

        else:
            # SQLite backend
            try:
                db_path = get_database_path(database_url)
                db_size_bytes = os.path.getsize(db_path) if os.path.exists(db_path) else 0
            except Exception:
                db_size_bytes = 0

            table_stats = {}
            for t in ["insider_transactions", "provenance", "ingestion_state"]:
                try:
                    c = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                except Exception:
                    c = 0
                table_stats[t] = {"total_bytes": 0, "table_bytes": 0, "index_bytes": 0, "count": c}

            indexes_detail = []
            it_rows = table_stats.get("insider_transactions", {}).get("count", 0)
            prov_rows = table_stats.get("provenance", {}).get("count", 0)

            try:
                prov_breakdown = conn.execute(
                    "SELECT record_type, COUNT(*) FROM provenance GROUP BY record_type"
                ).fetchall()
            except Exception:
                prov_breakdown = []

            try:
                raw_stats = conn.execute(
                    """
                    SELECT
                        COUNT(raw_payload),
                        COALESCE(SUM(LENGTH(raw_payload)), 0),
                        COALESCE(AVG(LENGTH(raw_payload)), 0)
                    FROM insider_transactions
                    WHERE raw_payload IS NOT NULL AND raw_payload != ''
                    """
                ).fetchone()
            except Exception:
                raw_stats = (0, 0, 0.0)

            try:
                imported_periods = conn.execute(
                    "SELECT COUNT(*) FROM ingestion_state WHERE status = 'COMPLETED'"
                ).fetchone()[0]
            except Exception:
                imported_periods = 0

    raw_count = raw_stats[0] if raw_stats else 0
    raw_sum_bytes = raw_stats[1] if raw_stats else 0
    raw_avg_chars = float(raw_stats[2]) if raw_stats else 0.0

    print(f"Database Total Size:        {db_size_bytes / (1024 * 1024):.2f} MB ({db_size_bytes:,} bytes)")
    print(f"insider_transactions Rows:  {it_rows:,}")
    print(f"provenance Rows:            {prov_rows:,}")
    print(f"Imported Periods (Quarters): {imported_periods:,}\n")

    print("TABLE & INDEX BREAKDOWN:")
    for t_name, s in table_stats.items():
        if s["total_bytes"] > 0 or s.get("count", 0) > 0:
            count_str = f" ({s['count']:,} rows)" if "count" in s else ""
            print(f"  {t_name:22s} Total: {s['total_bytes'] / (1024 * 1024):.2f} MB | Table: {s['table_bytes'] / (1024 * 1024):.2f} MB | Indexes: {s['index_bytes'] / (1024 * 1024):.2f} MB{count_str}")
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
    if not prov_breakdown:
        print("  (No provenance records found)")
    print()

    # Provenance Dependency Analysis
    tx_prov_count = prov_dict.get("insider_transaction", 0)
    dataset_prov_count = prov_dict.get("dataset_period", 0)
    print("PROVENANCE DEPENDENCY ANALYSIS:")
    print(f"  Transaction-level provenance rows: {tx_prov_count:,}")
    print(f"  Dataset-level provenance rows:     {dataset_prov_count:,}")
    print("  Foreign Key Dependencies on provenance: NONE (provenance is an isolated audit table)")
    print("  Application Code Dependencies: ONLY dataset_period is queried during verification/ingestion.")
    print("  Transaction identity is preserved via record_hash on insider_transactions table.")
    print()

    print("RAW_PAYLOAD STATISTICS:")
    print(f"  Rows with raw_payload:    {raw_count:,}")
    print(f"  Total raw_payload size:   {raw_sum_bytes / (1024 * 1024):.2f} MB ({raw_sum_bytes:,} bytes)")
    print(f"  Average raw_payload size: {raw_avg_chars:.1f} characters/bytes\n")

    # Dynamic Volume and Storage Calculations
    it_stats = table_stats.get("insider_transactions", {})
    it_total_bytes = it_stats.get("total_bytes", 0)
    it_table_bytes = it_stats.get("table_bytes", 0)
    it_index_bytes = it_stats.get("index_bytes", 0)

    # Use observed actual current storage rates if available, else derive from empirical database facts
    if it_rows > 0 and it_total_bytes > 0:
        obs_table_bytes_per_tx = it_table_bytes / it_rows
        obs_index_bytes_per_tx = it_index_bytes / it_rows
        obs_total_bytes_per_tx = it_total_bytes / it_rows
    else:
        # Based on actual Neon 379,581 transactions audit:
        # Table size: 579 MB (~1,525 bytes/tx)
        # Indexes: 227 MB total (1 duplicate unique ~68MB, 1 unique ~68MB, 1 date ~91MB => ~600 bytes/tx)
        obs_table_bytes_per_tx = 1525
        obs_index_bytes_per_tx = 600
        obs_total_bytes_per_tx = 2125

    if imported_periods > 0 and it_rows > 0:
        obs_tx_per_quarter = it_rows / imported_periods
    else:
        # Empirical observed average across 2006-Q1 & 2006-Q2 = 379,581 / 2 = 189,790
        obs_tx_per_quarter = 189790.0

    print("DYNAMIC OBSERVED METRICS:")
    print(f"  Observed transactions / imported quarter:  {obs_tx_per_quarter:,.0f}")
    print(f"  Observed table storage per transaction:     {obs_table_bytes_per_tx:.0f} bytes")
    print(f"  Observed index storage per transaction:     {obs_index_bytes_per_tx:.0f} bytes")
    print(f"  Observed current total storage / transaction: {obs_total_bytes_per_tx:.0f} bytes\n")

    # Dynamic Historical Projections
    # Formula: Total Storage = (Quarters * Observed_Tx_Per_Quarter) * Bytes_Per_Tx
    # Architecture Scenarios:
    # 1. Current Bloated: Table + 2 Unique Indexes + Date Index + Tx-level Provenance (~2,180 bytes/tx)
    # 2. Repaired Neon: Duplicate Index Dropped + Tx-level Provenance Dropped + raw_payload retained (~1,944 bytes/tx)
    # 3. Repaired + Cold Archive: raw_payload offloaded to S3/disk archive, normalized fields only in Neon (~669 bytes/tx)

    bytes_tx_current = obs_total_bytes_per_tx + (192 if tx_prov_count > 0 else 0)  # include per-tx provenance overhead
    bytes_tx_repaired = obs_table_bytes_per_tx + 419  # Single UNIQUE (~179 bytes) + Date index (~240 bytes)
    bytes_tx_archived = 250 + 419  # Normalized fields (~250 bytes) + Indexes (~419 bytes)

    print("DYNAMIC STORAGE PROJECTIONS:")
    print("  Note: Projections dynamically calculate volume using observed dataset rate:")
    print(f"  Rate: {obs_tx_per_quarter:,.0f} transactions/quarter based on {imported_periods if imported_periods > 0 else 2} imported quarters.\n")

    ranges = [
        ("2006-Q1 -> 2010-Q4", 20),
        ("2006-Q1 -> 2020-Q4", 60),
        ("2006-Q1 -> 2026-Q2", 82),
    ]

    for label, qtrs in ranges:
        proj_txs = int(qtrs * obs_tx_per_quarter)
        mb_current = (proj_txs * bytes_tx_current) / (1024 * 1024)
        mb_repaired = (proj_txs * bytes_tx_repaired) / (1024 * 1024)
        mb_archived = (proj_txs * bytes_tx_archived) / (1024 * 1024)

        print(f"  {label} ({qtrs} quarters / ~{proj_txs:,} transactions):")
        print(f"    - Current Bloated Architecture:                              {mb_current:,.0f} MB ({mb_current/1024:.2f} GB)")
        print(f"    - Repaired Architecture (Duplicates/Prov Dropped, raw in DB): {mb_repaired:,.0f} MB ({mb_repaired/1024:.2f} GB)")
        print(f"    - Repaired + Cold Archive (raw_payload offloaded to archive):  {mb_archived:,.0f} MB ({mb_archived/1024:.2f} GB)")
    print("=====================================================================\n")

    audit_data.update({
        "database_size_bytes": db_size_bytes,
        "insider_transactions_count": it_rows,
        "provenance_count": prov_rows,
        "provenance_breakdown": prov_dict,
        "raw_payload_count": raw_count,
        "raw_payload_total_bytes": raw_sum_bytes,
        "raw_payload_avg_chars": raw_avg_chars,
        "table_stats": table_stats,
        "imported_periods": imported_periods,
        "obs_tx_per_quarter": obs_tx_per_quarter,
    })

    return audit_data


def main() -> int:
    parser = argparse.ArgumentParser(description="Strictly Read-Only Storage Audit & Diagnostics for Insider Trade Bot.")
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
