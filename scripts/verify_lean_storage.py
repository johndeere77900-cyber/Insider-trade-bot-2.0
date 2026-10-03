"""
Lean Storage Validation Script for Insider Trade Bot 2.0.

Validates that ingestion under lean storage mode (SEC_STORE_RAW_PAYLOAD=false):
- Persists normalized transactions without storing raw_payload (raw_payload is strictly NULL).
- Populates record_hash for all transactions.
- Prevents duplicate transaction identities (source, accession_number, record_hash).
- Tracks dataset-level provenance while creating ZERO transaction-level provenance records.
- Records valid ingestion_state.
- Maintains database idempotency on re-processing without increasing transaction counts.
- Runs read-only storage audit and outputs a GitHub Actions step summary.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Add repository root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.environment import load_environment
from database.connection import connect, is_postgresql_url
from scripts.storage_audit import run_storage_audit


def get_db_url() -> str:
    """Load DATABASE_URL from environment."""
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        try:
            env = load_environment()
            db_url = env.database_url
        except Exception:
            pass
    if not db_url:
        print("ERROR: DATABASE_URL environment variable is missing or empty.", file=sys.stderr)
        sys.exit(1)
    return db_url


def query_one(conn: Any, db_url: str, sql: str, params: tuple = ()) -> Any:
    """Execute query and fetch single row normalized to dict."""
    cursor = conn.execute(sql, params)
    row = cursor.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    if getattr(cursor, "description", None):
        cols = [desc[0] for desc in cursor.description]
        if hasattr(row, "keys"):
            return {c: row[c] for c in cols}
        if isinstance(row, (tuple, list)):
            return dict(zip(cols, row))
    return row


def query_all(conn: Any, db_url: str, sql: str, params: tuple = ()) -> list:
    """Execute query and fetch all rows normalized to dict."""
    cursor = conn.execute(sql, params)
    rows = cursor.fetchall()
    if not rows:
        return []
    if getattr(cursor, "description", None):
        cols = [desc[0] for desc in cursor.description]
        normalized = []
        for r in rows:
            if isinstance(r, dict):
                normalized.append(r)
            elif hasattr(r, "keys"):
                normalized.append({c: r[c] for c in cols})
            elif isinstance(r, (tuple, list)):
                normalized.append(dict(zip(cols, r)))
            else:
                normalized.append(r)
        return normalized
    return rows


def get_field(row: Any, key: str) -> Any:
    """Safely retrieve a field value from dict or row."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, "keys"):
        try:
            return row[key]
        except (IndexError, KeyError, TypeError):
            pass
    return None


def format_bytes(num_bytes: int | float) -> str:
    """Format bytes as readable MB and exact byte count."""
    mb = num_bytes / (1024 * 1024)
    return f"{mb:.2f} MB ({int(num_bytes):,} bytes)"


def check_lean_env_var() -> None:
    """Strictly enforce that SEC_STORE_RAW_PAYLOAD is set to 'false'."""
    raw_setting = os.environ.get("SEC_STORE_RAW_PAYLOAD", "").strip().lower()
    if raw_setting != "false":
        print(
            f"ERROR: SEC_STORE_RAW_PAYLOAD must be explicitly set to 'false' in workflow environment. Got: {raw_setting!r}",
            file=sys.stderr,
        )
        sys.exit(1)


def verify_lean_run1(period: str, state_file: str) -> Dict[str, Any]:
    """Perform post-ingestion verification after Run 1 in lean storage mode."""
    check_lean_env_var()
    db_url = get_db_url()
    print(f"Executing Run 1 Lean Storage Verification for period {period}...")

    with connect(db_url) as conn:
        # A. Transactions
        row = query_one(conn, db_url, "SELECT COUNT(*) AS c FROM insider_transactions")
        total_tx_count = int(get_field(row, "c") or 0)

        if total_tx_count == 0:
            print("ERROR: insider_transactions table is empty (0 transactions).", file=sys.stderr)
            sys.exit(1)

        # Record hash checks
        row = query_one(
            conn,
            db_url,
            "SELECT COUNT(*) AS c FROM insider_transactions WHERE record_hash IS NULL OR record_hash = ''",
        )
        missing_record_hash_count = int(get_field(row, "c") or 0)

        row = query_one(
            conn,
            db_url,
            "SELECT COUNT(*) AS c FROM insider_transactions WHERE record_hash IS NOT NULL AND record_hash != ''",
        )
        populated_record_hash_count = int(get_field(row, "c") or 0)

        if missing_record_hash_count > 0:
            print(f"ERROR: {missing_record_hash_count} transactions have missing or empty record_hash.", file=sys.stderr)
            sys.exit(1)

        # Check required normalized fields are populated
        row = query_one(
            conn,
            db_url,
            """
            SELECT COUNT(*) AS c FROM insider_transactions
            WHERE accession_number IS NULL OR accession_number = ''
               OR issuer_cik IS NULL OR issuer_cik = ''
               OR source IS NULL OR source = ''
               OR created_at IS NULL OR created_at = ''
            """,
        )
        unpopulated_normalized_count = int(get_field(row, "c") or 0)
        if unpopulated_normalized_count > 0:
            print(f"ERROR: {unpopulated_normalized_count} transactions have unpopulated required normalized fields.", file=sys.stderr)
            sys.exit(1)

        # B. Raw Payload
        row = query_one(
            conn,
            db_url,
            "SELECT COUNT(*) AS c FROM insider_transactions WHERE raw_payload IS NULL OR raw_payload = ''",
        )
        raw_null_count = int(get_field(row, "c") or 0)

        row = query_one(
            conn,
            db_url,
            "SELECT COUNT(*) AS c FROM insider_transactions WHERE raw_payload IS NOT NULL AND raw_payload != ''",
        )
        raw_non_null_count = int(get_field(row, "c") or 0)

        if raw_non_null_count > 0:
            print(
                f"ERROR: Lean storage violation! Found {raw_non_null_count} transaction(s) with raw_payload populated.",
                file=sys.stderr,
            )
            sys.exit(1)

        if raw_null_count != total_tx_count:
            print(
                f"ERROR: Mismatch in raw_payload NULL count ({raw_null_count}) vs total transaction count ({total_tx_count}).",
                file=sys.stderr,
            )
            sys.exit(1)

        # C. Uniqueness
        dup_query = """
            SELECT source, accession_number, record_hash, COUNT(*) AS c
            FROM insider_transactions
            GROUP BY source, accession_number, record_hash
            HAVING COUNT(*) > 1
        """
        duplicates = query_all(conn, db_url, dup_query)
        duplicate_identities_count = len(duplicates)

        if duplicate_identities_count > 0:
            print(f"ERROR: Found {duplicate_identities_count} duplicate transaction identity groups.", file=sys.stderr)
            sys.exit(1)

        # D. Provenance
        prov_ds_sql = (
            "SELECT COUNT(*) AS c FROM provenance WHERE record_type = %s AND record_id = %s AND source = %s"
            if is_postgresql_url(db_url)
            else "SELECT COUNT(*) AS c FROM provenance WHERE record_type = ? AND record_id = ? AND source = ?"
        )
        row = query_one(conn, db_url, prov_ds_sql, ("dataset_period", period, "SEC"))
        ds_prov_count = int(get_field(row, "c") or 0)

        if ds_prov_count == 0:
            print(f"ERROR: Missing dataset-period provenance record for {period}.", file=sys.stderr)
            sys.exit(1)

        prov_tx_sql = "SELECT COUNT(*) AS c FROM provenance WHERE record_type = 'insider_transaction'"
        row = query_one(conn, db_url, prov_tx_sql)
        tx_prov_count = int(get_field(row, "c") or 0)

        if tx_prov_count > 0:
            print(
                f"ERROR: Ingestion created {tx_prov_count} transaction-level provenance rows! "
                "Expected ZERO transaction-level provenance in lean storage mode.",
                file=sys.stderr,
            )
            sys.exit(1)

        # E. Ingestion State
        ingest_sql = (
            "SELECT period, status, records_parsed, records_inserted, duplicates_count, invalid_count, failures_count "
            "FROM ingestion_state WHERE period = %s"
            if is_postgresql_url(db_url)
            else "SELECT period, status, records_parsed, records_inserted, duplicates_count, invalid_count, failures_count "
            "FROM ingestion_state WHERE period = ?"
        )
        ingest_row = query_one(conn, db_url, ingest_sql, (period,))

        if not ingest_row:
            print(f"ERROR: Missing ingestion_state record for period {period}.", file=sys.stderr)
            sys.exit(1)

        status = str(get_field(ingest_row, "status") or "").upper()
        records_parsed = int(get_field(ingest_row, "records_parsed") or 0)
        records_inserted = int(get_field(ingest_row, "records_inserted") or 0)
        failures_count = int(get_field(ingest_row, "failures_count") or 0)

        if status != "COMPLETED":
            print(f"ERROR: ingestion_state status is '{status}', expected 'COMPLETED'.", file=sys.stderr)
            sys.exit(1)

        if records_parsed <= 0:
            print(f"ERROR: ingestion_state records_parsed is {records_parsed}, expected > 0.", file=sys.stderr)
            sys.exit(1)

        if records_inserted <= 0:
            print(f"ERROR: ingestion_state records_inserted is {records_inserted}, expected > 0.", file=sys.stderr)
            sys.exit(1)

        if failures_count != 0:
            print(f"ERROR: ingestion_state failures_count is {failures_count}, expected 0.", file=sys.stderr)
            sys.exit(1)

    run1_data = {
        "period": period,
        "total_tx_count": total_tx_count,
        "populated_record_hash_count": populated_record_hash_count,
        "missing_record_hash_count": missing_record_hash_count,
        "raw_null_count": raw_null_count,
        "raw_non_null_count": raw_non_null_count,
        "ds_prov_count": ds_prov_count,
        "tx_prov_count": tx_prov_count,
        "status": status,
        "records_parsed": records_parsed,
        "records_inserted": records_inserted,
        "failures_count": failures_count,
    }

    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(run1_data, f, indent=2)

    print(f"Run 1 Lean Storage Verification PASSED for {period}. Stats saved to {state_file}.")
    return run1_data


def verify_lean_run2_and_summary(period: str, state_file: str) -> None:
    """Perform Run 2 idempotency verification, run storage audit, and write GitHub Actions summary."""
    check_lean_env_var()
    db_url = get_db_url()
    print(f"Executing Run 2 Lean Storage & Idempotency Verification for period {period}...")

    if not os.path.exists(state_file):
        print(f"ERROR: State file {state_file} from Run 1 not found.", file=sys.stderr)
        sys.exit(1)

    with open(state_file, "r", encoding="utf-8") as f:
        run1 = json.load(f)

    # Re-run full check on current database state
    run2_check = verify_lean_run1(period, state_file + ".run2.tmp")

    first_count = run1["total_tx_count"]
    second_count = run2_check["total_tx_count"]
    count_diff = second_count - first_count

    if count_diff != 0:
        print(
            f"ERROR: Idempotency failure! First run count = {first_count}, Second run count = {second_count}, difference = {count_diff}.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Run Storage Audit
    print("Executing Read-Only Storage Audit...")
    audit_data = run_storage_audit(db_url)

    db_size_bytes = audit_data.get("database_size_bytes", 0)
    it_table_bytes = audit_data.get("insider_transactions_table_bytes", 0)
    it_index_bytes = audit_data.get("insider_transactions_index_bytes", 0)
    prov_size_bytes = audit_data.get("provenance_size_bytes", 0)

    table_stats = audit_data.get("table_stats", {})
    prov_stats = table_stats.get("provenance", {})
    prov_table_bytes = prov_stats.get("table_bytes", prov_size_bytes)
    prov_index_bytes = prov_stats.get("index_bytes", 0)

    obs_bytes_per_tx = audit_data.get("obs_total_bytes_per_tx", 0.0)

    tx_count = run2_check["total_tx_count"]
    raw_null_count = run2_check["raw_null_count"]
    raw_non_null_count = run2_check["raw_non_null_count"]
    populated_hash_count = run2_check["populated_record_hash_count"]
    missing_hash_count = run2_check["missing_record_hash_count"]
    ds_prov_count = run2_check["ds_prov_count"]
    tx_prov_count = run2_check["tx_prov_count"]
    ingest_status = run2_check["status"].lower()
    parsed_count = run2_check["records_parsed"]
    inserted_count = run2_check["records_inserted"]
    failures_count = run2_check["failures_count"]

    summary_content = f"""LEAN STORAGE VALIDATION
=======================

Database:
fresh Neon database

SEC period:
{period}

SEC_STORE_RAW_PAYLOAD:
false

Transactions:
{tx_count:,}

Raw payload:
NULL rows: {raw_null_count:,}
Non-NULL rows: {raw_non_null_count:,}

Record hash:
populated: {populated_hash_count:,}
missing: {missing_hash_count:,}

Provenance:
dataset-period rows: {ds_prov_count:,}
transaction-level rows created by this run: {tx_prov_count:,}

Ingestion:
status: {ingest_status}
records parsed: {parsed_count:,}
records inserted: {inserted_count:,}
failures: {failures_count:,}

Storage:
database size: {format_bytes(db_size_bytes)}
transactions table: {format_bytes(it_table_bytes)}
transaction indexes: {format_bytes(it_index_bytes)}
provenance: {format_bytes(prov_table_bytes)}
provenance indexes: {format_bytes(prov_index_bytes)}
bytes/transaction: {obs_bytes_per_tx:.1f} bytes/tx

Idempotency:
first count: {first_count:,}
second count: {second_count:,}
difference: {count_diff:,}

FINAL RESULT:
PASS
"""

    print("\n" + summary_content)

    github_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if github_summary_path:
        try:
            with open(github_summary_path, "a", encoding="utf-8") as f:
                f.write("```\n" + summary_content + "```\n")
            print(f"Successfully wrote summary to $GITHUB_STEP_SUMMARY ({github_summary_path}).")
        except Exception as exc:
            print(f"WARNING: Failed to write to GITHUB_STEP_SUMMARY: {exc}", file=sys.stderr)

    # Clean up temp run2 state file
    tmp_run2 = state_file + ".run2.tmp"
    if os.path.exists(tmp_run2):
        os.remove(tmp_run2)

    print("Lean storage validation completed successfully with FINAL RESULT: PASS.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Lean Storage Validation for SEC Historical Ingestion.")
    parser.add_argument("--run", type=int, choices=[1, 2], required=True, help="Run number to verify (1 or 2)")
    parser.add_argument("--period", default="2006-Q1", help="Target SEC dataset period (default: 2006-Q1)")
    parser.add_argument("--state-file", default="/tmp/lean_storage_run1.json", help="Path to JSON state file")

    args = parser.parse_args()

    if args.period != "2006-Q1":
        print(f"WARNING: Lean storage validation is configured for 2006-Q1. Running period: {args.period}")

    if args.run == 1:
        verify_lean_run1(args.period, args.state_file)
        return 0
    elif args.run == 2:
        verify_lean_run2_and_summary(args.period, args.state_file)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
