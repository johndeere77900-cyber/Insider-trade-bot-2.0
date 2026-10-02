"""
Verification Script for SEC Historical Ingestion into Database (Neon PostgreSQL or SQLite).

Validates:
- Run 1 data ingestion, provenance, ingestion_state, and data quality rules.
- Run 2 database idempotency and duplicate protection.
- Temporary ZIP cleanup.
- Formats final TASK 10 summary output.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Add repository root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.environment import load_environment
from database.connection import connect, is_postgresql_url
from storage.repository import _row_value


def get_field(row: Any, key: str) -> Any:
    """Safely retrieve a column by name from sqlite3.Row, dict, or psycopg tuple/row."""
    if row is None:
        return None
    if hasattr(row, "keys"):
        try:
            return row[key]
        except (IndexError, KeyError):
            pass
    if isinstance(row, dict):
        return row.get(key)
    return None


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
    """Execute query and fetch single row."""
    cursor = conn.execute(sql, params)
    return cursor.fetchone()


def query_all(conn: Any, db_url: str, sql: str, params: tuple = ()) -> list:
    """Execute query and fetch all rows."""
    cursor = conn.execute(sql, params)
    return cursor.fetchall()


def check_temp_files_cleaned(period: str) -> bool:
    """Check that temporary SEC zip files for period do not exist in temp directory."""
    temp_dir = tempfile.gettempdir()
    pattern = os.path.join(temp_dir, f"sec_{period}_*.zip")
    matches = glob.glob(pattern)
    if matches:
        print(f"ERROR: Temporary ZIP file(s) found after run: {matches}", file=sys.stderr)
        return False
    return True


def verify_run1(period: str, state_file: str) -> int:
    """Perform Run 1 database verification and data quality checks."""
    db_url = get_db_url()
    print(f"Running Run 1 verification for period {period} on database...")

    with connect(db_url) as conn:
        # A. insider_transactions checks
        row = query_one(conn, db_url, "SELECT COUNT(*) AS c FROM insider_transactions")
        tx_count = int(get_field(row, "c") if get_field(row, "c") is not None else row[0])

        if tx_count == 0:
            print("ERROR: insider_transactions has 0 rows after first ingestion.", file=sys.stderr)
            sys.exit(1)

        row = query_one(
            conn,
            db_url,
            "SELECT MIN(transaction_date) AS min_d, MAX(transaction_date) AS max_d FROM insider_transactions WHERE transaction_date IS NOT NULL AND transaction_date != ''"
        )
        earliest_date = get_field(row, "min_d") if get_field(row, "min_d") is not None else row[0]
        latest_date = get_field(row, "max_d") if get_field(row, "max_d") is not None else row[1]

        row = query_one(conn, db_url, "SELECT COUNT(DISTINCT accession_number) AS c FROM insider_transactions")
        distinct_accessions = int(get_field(row, "c") if get_field(row, "c") is not None else row[0])

        row = query_one(conn, db_url, "SELECT COUNT(DISTINCT record_hash) AS c FROM insider_transactions")
        distinct_hashes = int(get_field(row, "c") if get_field(row, "c") is not None else row[0])

        print(f"insider_transactions count: {tx_count}")
        print(f"Earliest transaction date: {earliest_date}")
        print(f"Latest transaction date: {latest_date}")
        print(f"Distinct accession numbers: {distinct_accessions}")
        print(f"Distinct record hashes: {distinct_hashes}")

        # B. provenance checks
        row = query_one(
            conn,
            db_url,
            "SELECT * FROM provenance WHERE record_type = %s AND record_id = %s AND source = %s"
            if is_postgresql_url(db_url) else
            "SELECT * FROM provenance WHERE record_type = ? AND record_id = ? AND source = ?",
            ("dataset_period", period, "SEC")
        )

        if not row:
            print(f"ERROR: Missing provenance record for dataset_period {period}.", file=sys.stderr)
            sys.exit(1)

        prov_source = get_field(row, "source")
        prov_ref = get_field(row, "source_reference")
        prov_checksum = get_field(row, "checksum")
        prov_status = get_field(row, "validation_status")

        if prov_source != "SEC":
            print(f"ERROR: Provenance source is '{prov_source}', expected 'SEC'.", file=sys.stderr)
            sys.exit(1)

        if not prov_ref or "2006q1_form345.zip" not in prov_ref:
            print(f"ERROR: Provenance source_reference '{prov_ref}' is invalid.", file=sys.stderr)
            sys.exit(1)

        if not prov_checksum:
            print("ERROR: Provenance checksum is missing.", file=sys.stderr)
            sys.exit(1)

        if prov_status != "validated":
            print(f"ERROR: Provenance status is '{prov_status}', expected 'validated'.", file=sys.stderr)
            sys.exit(1)

        row = query_one(conn, db_url, "SELECT COUNT(*) AS c FROM provenance")
        total_prov_count = int(get_field(row, "c") if get_field(row, "c") is not None else row[0])

        # C. ingestion_state checks
        row = query_one(
            conn,
            db_url,
            "SELECT * FROM ingestion_state WHERE period = %s"
            if is_postgresql_url(db_url) else
            "SELECT * FROM ingestion_state WHERE period = ?",
            (period,)
        )

        if not row:
            print(f"ERROR: Missing ingestion_state record for period {period}.", file=sys.stderr)
            sys.exit(1)

        status = get_field(row, "status")
        records_parsed = int(get_field(row, "records_parsed") or 0)
        records_inserted = int(get_field(row, "records_inserted") or 0)
        duplicates_count = int(get_field(row, "duplicates_count") or 0)
        invalid_count = int(get_field(row, "invalid_count") or 0)
        failures_count = int(get_field(row, "failures_count") or 0)

        if status != "COMPLETED":
            print(f"ERROR: Ingestion status is '{status}', expected 'COMPLETED'.", file=sys.stderr)
            sys.exit(1)

        if failures_count != 0:
            print(f"ERROR: Ingestion state reports failures_count = {failures_count}.", file=sys.stderr)
            sys.exit(1)

        if records_inserted == 0:
            print("ERROR: Ingestion state reports records_inserted = 0.", file=sys.stderr)
            sys.exit(1)

        # D. Data quality checks
        rows = query_all(conn, db_url, "SELECT * FROM insider_transactions LIMIT 50")
        dq_pass = True

        multi_owner_tested = False
        amendment_tested = False

        for r in rows:
            acc = get_field(r, "accession_number")
            cik = get_field(r, "issuer_cik")
            rec_hash = get_field(r, "record_hash")
            source = get_field(r, "source")
            raw_str = get_field(r, "raw_payload")

            if not acc or not cik or not rec_hash or source != "SEC" or not raw_str:
                print(f"ERROR: Record failed required field check: acc={acc}, cik={cik}, hash={rec_hash}, source={source}", file=sys.stderr)
                dq_pass = False
                break

            try:
                raw_obj = json.loads(raw_str) if isinstance(raw_str, str) else raw_str
            except Exception:
                print(f"ERROR: Raw payload JSON unparseable for record {acc}", file=sys.stderr)
                dq_pass = False
                break

            all_owners = raw_obj.get("all_owners", [])
            insider_name = get_field(r, "insider_name")
            insider_cik = get_field(r, "insider_cik")

            if len(all_owners) > 1:
                multi_owner_tested = True
                if insider_name is not None or insider_cik is not None:
                    print(f"ERROR: Multi-owner filing {acc} assigned specific owner_cik/name when all_owners has length {len(all_owners)}", file=sys.stderr)
                    dq_pass = False
                    break

            doc_type = raw_obj.get("submission", {}).get("DOCUMENT_TYPE", "")
            date_orig = raw_obj.get("submission", {}).get("DATE_OF_ORIG_SUB", "")
            if doc_type.endswith("/A") or date_orig:
                amendment_tested = True

        if not dq_pass:
            print("ERROR: Data quality checks failed.", file=sys.stderr)
            sys.exit(1)

        temp_cleaned = check_temp_files_cleaned(period)
        if not temp_cleaned:
            sys.exit(1)

        # Save run 1 state for run 2 verification
        run1_data = {
            "period": period,
            "records_parsed": records_parsed,
            "records_inserted": records_inserted,
            "duplicates_count": duplicates_count,
            "invalid_count": invalid_count,
            "failures_count": failures_count,
            "tx_count": tx_count,
            "provenance_count": total_prov_count,
            "status": status,
            "earliest_date": earliest_date,
            "latest_date": latest_date,
            "multi_owner_tested": multi_owner_tested,
            "amendment_tested": amendment_tested,
        }

        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(run1_data, f, indent=2)

        print(f"Run 1 verification PASSED. Saved state to {state_file}.")
        return 0


def verify_run2(period: str, state_file: str) -> int:
    """Perform Run 2 database verification, idempotency checks, and output summary report."""
    db_url = get_db_url()
    print(f"Running Run 2 (Idempotency) verification for period {period} on database...")

    if not os.path.exists(state_file):
        print(f"ERROR: State file {state_file} from Run 1 not found.", file=sys.stderr)
        sys.exit(1)

    with open(state_file, "r", encoding="utf-8") as f:
        run1 = json.load(f)

    with connect(db_url) as conn:
        # insider_transactions total count check
        row = query_one(conn, db_url, "SELECT COUNT(*) AS c FROM insider_transactions")
        tx_count_run2 = int(get_field(row, "c") if get_field(row, "c") is not None else row[0])

        # provenance count check
        row = query_one(conn, db_url, "SELECT COUNT(*) AS c FROM provenance")
        prov_count_run2 = int(get_field(row, "c") if get_field(row, "c") is not None else row[0])

        # ingestion_state check
        row = query_one(
            conn,
            db_url,
            "SELECT * FROM ingestion_state WHERE period = %s"
            if is_postgresql_url(db_url) else
            "SELECT * FROM ingestion_state WHERE period = ?",
            (period,)
        )

        if not row:
            print(f"ERROR: Missing ingestion_state record for period {period} on run 2.", file=sys.stderr)
            sys.exit(1)

        status_run2 = get_field(row, "status")
        run2_parsed = int(get_field(row, "records_parsed") or 0)
        run2_inserted = int(get_field(row, "records_inserted") or 0)
        run2_duplicates = int(get_field(row, "duplicates_count") or 0)
        run2_invalid = int(get_field(row, "invalid_count") or 0)
        run2_failures = int(get_field(row, "failures_count") or 0)

        idempotency_pass = True
        idempotency_errors = []

        # 1. Total insider transactions count must NOT increase
        if tx_count_run2 != run1["tx_count"]:
            idempotency_pass = False
            idempotency_errors.append(
                f"insider_transactions count changed from {run1['tx_count']} to {tx_count_run2}"
            )

        # 2. Provenance count must not increase unexpectedly
        if prov_count_run2 != run1["provenance_count"]:
            idempotency_pass = False
            idempotency_errors.append(
                f"provenance count changed from {run1['provenance_count']} to {prov_count_run2}"
            )

        # 3. Status must remain COMPLETED
        if status_run2 != "COMPLETED":
            idempotency_pass = False
            idempotency_errors.append(f"ingestion_state status is '{status_run2}', expected 'COMPLETED'")

        # 4. Failures must remain 0
        if run2_failures != 0:
            idempotency_pass = False
            idempotency_errors.append(f"ingestion_state failures_count is {run2_failures}")

        temp_cleaned = check_temp_files_cleaned(period)

        data_quality_pass = run1.get("tx_count", 0) > 0 and status_run2 == "COMPLETED"
        temp_cleanup_pass = temp_cleaned
        overall_pass = idempotency_pass and data_quality_pass and temp_cleanup_pass

        print("\n" + "=" * 60)
        print("SEC DATASET:")
        print(f"{period}\n")

        print("FIRST RUN:")
        print(f"- records parsed: {run1['records_parsed']}")
        print(f"- records inserted: {run1['records_inserted']}")
        print(f"- duplicates: {run1['duplicates_count']}")
        print(f"- invalid: {run1['invalid_count']}")
        print(f"- failures: {run1['failures_count']}\n")

        print("NEON:")
        print(f"- insider_transactions count: {tx_count_run2}")
        print(f"- provenance count: {prov_count_run2}")
        print(f"- ingestion_state status: {status_run2}")
        print(f"- earliest transaction date: {run1['earliest_date']}")
        print(f"- latest transaction date: {run1['latest_date']}\n")

        print("SECOND RUN:")
        print(f"- records parsed: {run2_parsed}")
        print(f"- records inserted: {run2_inserted}")
        print(f"- duplicates: {run2_duplicates}")
        print(f"- invalid: {run2_invalid}")
        print(f"- failures: {run2_failures}\n")

        print("IDEMPOTENCY:")
        print("PASS" if idempotency_pass else "FAIL")
        if idempotency_errors:
            for err in idempotency_errors:
                print(f"  Reason: {err}")
        print()

        print("DATA QUALITY:")
        print("PASS" if data_quality_pass else "FAIL")
        print()

        print("TEMP FILE CLEANUP:")
        print("PASS" if temp_cleanup_pass else "FAIL")
        print()

        print("OVERALL:")
        print("PASS" if overall_pass else "FAIL")
        print("=" * 60 + "\n")

        if not overall_pass:
            print("ERROR: Smoke test validation failed.", file=sys.stderr)
            sys.exit(1)

        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify SEC historical ingestion.")
    parser.add_argument("--run", type=int, choices=[1, 2], required=True, help="Run number to verify (1 or 2)")
    parser.add_argument("--period", default="2006-Q1", help="Target SEC dataset period")
    parser.add_argument("--state-file", default="/tmp/sec_run1_stats.json", help="Path to JSON state file between runs")

    args = parser.parse_args()

    if args.run == 1:
        return verify_run1(args.period, args.state_file)
    else:
        return verify_run2(args.period, args.state_file)


if __name__ == "__main__":
    sys.exit(main())
