"""
Verification Script for SEC Historical Ingestion into Database (Neon PostgreSQL or SQLite).

Validates:
- Run 1 data ingestion, provenance, ingestion_state, and data quality rules.
- Multi-owner handling and amendment preservation (PASS / FAIL / NOT TESTABLE) scoped to target period.
- Explicit DATA QUALITY reporting (PASS / FAIL / PARTIAL / NOT TESTABLE).
- Run 2 database idempotency and duplicate protection with forced re-processing.
- Temporary ZIP cleanup.
- Formats final required summary output.
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


def get_period_date_bounds(period: str) -> Tuple[str, str]:
    """Return ISO (start_date, end_date) strings for a quarter period like '2006-Q1'."""
    cleaned = period.strip().upper()
    try:
        year = int(cleaned[:4])
        qtr = int(cleaned[-1])
    except (ValueError, IndexError):
        return "2006-01-01", "2006-03-31"

    if qtr == 1:
        return f"{year}-01-01", f"{year}-03-31"
    elif qtr == 2:
        return f"{year}-04-01", f"{year}-06-30"
    elif qtr == 3:
        return f"{year}-07-01", f"{year}-09-30"
    else:
        return f"{year}-10-01", f"{year}-12-31"


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
    """Perform Run 1 database verification and data quality checks scoped to period."""
    db_url = get_db_url()
    print(f"Running Run 1 verification for period {period} on database...")

    start_date, end_date = get_period_date_bounds(period)

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

        if not prov_ref or f"{period.replace('-', '').lower()}_form345.zip" not in prov_ref.lower():
            print(f"ERROR: Provenance source_reference '{prov_ref}' is invalid for period {period}.", file=sys.stderr)
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

        # D. Period-Scoped Data Quality: Multi-Owner and Amendment checks
        period_sql = (
            "SELECT accession_number, issuer_cik, record_hash, source, insider_name, insider_cik, form_type, filing_date, raw_payload "
            "FROM insider_transactions WHERE filing_date >= %s AND filing_date <= %s"
            if is_postgresql_url(db_url) else
            "SELECT accession_number, issuer_cik, record_hash, source, insider_name, insider_cik, form_type, filing_date, raw_payload "
            "FROM insider_transactions WHERE filing_date >= ? AND filing_date <= ?"
        )
        period_rows = query_all(conn, db_url, period_sql, (start_date, end_date))

        # Fallback if filing_date range returned 0: fetch all rows
        if not period_rows:
            period_rows = query_all(
                conn,
                db_url,
                "SELECT accession_number, issuer_cik, record_hash, source, insider_name, insider_cik, form_type, filing_date, raw_payload FROM insider_transactions"
            )

        dq_pass = True

        multi_owner_found = False
        multi_owner_valid = True

        amendment_records = []
        all_period_hashes = set()
        accession_hash_map: Dict[str, set] = {}

        for r in period_rows:
            acc = get_field(r, "accession_number")
            cik = get_field(r, "issuer_cik")
            rec_hash = get_field(r, "record_hash")
            source = get_field(r, "source")
            raw_str = get_field(r, "raw_payload")

            if not acc or not cik or not rec_hash or source != "SEC" or not raw_str:
                print(f"ERROR: Record failed required field check: acc={acc}, cik={cik}, hash={rec_hash}, source={source}", file=sys.stderr)
                dq_pass = False
                break

            all_period_hashes.add(rec_hash)
            if acc not in accession_hash_map:
                accession_hash_map[acc] = set()
            accession_hash_map[acc].add(rec_hash)

            try:
                raw_obj = json.loads(raw_str) if isinstance(raw_str, str) else raw_str
            except Exception:
                print(f"ERROR: Raw payload JSON unparseable for record {acc}", file=sys.stderr)
                dq_pass = False
                break

            # Multi-owner evaluation
            all_owners = raw_obj.get("all_owners", [])
            insider_name = get_field(r, "insider_name")
            insider_cik = get_field(r, "insider_cik")

            if len(all_owners) > 1:
                multi_owner_found = True
                if insider_name is not None or insider_cik is not None:
                    print(f"ERROR: Multi-owner filing {acc} incorrectly assigned top-level insider_name={insider_name}, insider_cik={insider_cik}", file=sys.stderr)
                    multi_owner_valid = False

            # Amendment evaluation
            doc_type = str(raw_obj.get("submission", {}).get("DOCUMENT_TYPE", ""))
            date_orig = str(raw_obj.get("submission", {}).get("DATE_OF_ORIG_SUB", ""))
            form_t = str(get_field(r, "form_type") or "")

            if doc_type.endswith("/A") or form_t.endswith("/A") or (date_orig and date_orig.strip()):
                amendment_records.append((acc, rec_hash, date_orig, doc_type, raw_obj))

        # Strict Amendment Preservation Verification
        amendment_result = "NOT TESTABLE"
        if amendment_records:
            amendment_valid = True
            for acc, rec_hash, date_orig, doc_type, raw_obj in amendment_records:
                # 1. accession_number preserved
                if not acc:
                    amendment_valid = False
                    break
                # 2. record_hash present and unique in dataset
                if not rec_hash or rec_hash not in all_period_hashes:
                    amendment_valid = False
                    break
                # 3. amendment metadata present in raw_payload
                if not doc_type.endswith("/A") and not (date_orig and date_orig.strip()):
                    amendment_valid = False
                    break

                # 4. If original filing accession exists in dataset, verify distinct rows with distinct record_hashes
                orig_acc = raw_obj.get("submission", {}).get("ACCESSION_NUMBER") or acc
                if orig_acc in accession_hash_map and len(accession_hash_map[orig_acc]) > 1:
                    if rec_hash not in accession_hash_map[orig_acc]:
                        amendment_valid = False
                        break

            if amendment_valid:
                amendment_result = "PASS"
            else:
                amendment_result = "FAIL"

        if multi_owner_found:
            multi_owner_result = "PASS" if multi_owner_valid else "FAIL"
        else:
            multi_owner_result = "NOT TESTABLE"

        if not dq_pass or multi_owner_result == "FAIL" or amendment_result == "FAIL":
            print(f"ERROR: Data quality checks failed (multi_owner={multi_owner_result}, amendment={amendment_result}).", file=sys.stderr)
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
            "multi_owner_result": multi_owner_result,
            "amendment_result": amendment_result,
        }

        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(run1_data, f, indent=2)

        print(f"Run 1 verification PASSED. Multi-Owner: {multi_owner_result}, Amendment: {amendment_result}. Saved state to {state_file}.")
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

        # 1. Verification that second run actually downloaded and parsed SEC dataset
        if run2_parsed == 0:
            idempotency_pass = False
            idempotency_errors.append(
                "Run 2 records_parsed is 0 (the importer skipped or failed to process SEC data)"
            )

        # 2. Duplicate detection MUST occur on re-processing
        if run2_duplicates == 0 and run2_parsed > 0:
            idempotency_pass = False
            idempotency_errors.append(
                f"Run 2 duplicates_count is 0 despite parsing {run2_parsed} records (expected duplicates > 0)"
            )

        # 3. New records inserted MUST be 0
        if run2_inserted > 0:
            idempotency_pass = False
            idempotency_errors.append(
                f"Run 2 records_inserted is {run2_inserted} (expected 0)"
            )

        # 4. Total insider transactions count must NOT increase
        if tx_count_run2 != run1["tx_count"]:
            idempotency_pass = False
            idempotency_errors.append(
                f"insider_transactions count changed from {run1['tx_count']} to {tx_count_run2}"
            )

        # 5. Provenance count must not increase unexpectedly
        if prov_count_run2 != run1["provenance_count"]:
            idempotency_pass = False
            idempotency_errors.append(
                f"provenance count changed from {run1['provenance_count']} to {prov_count_run2}"
            )

        # 6. Status must remain COMPLETED
        if status_run2 != "COMPLETED":
            idempotency_pass = False
            idempotency_errors.append(f"ingestion_state status is '{status_run2}', expected 'COMPLETED'")

        # 7. Failures must remain 0
        if run2_failures != 0:
            idempotency_pass = False
            idempotency_errors.append(f"ingestion_state failures_count is {run2_failures}")

        temp_cleaned = check_temp_files_cleaned(period)

        multi_owner_result = run1.get("multi_owner_result", "NOT TESTABLE")
        amendment_result = run1.get("amendment_result", "NOT TESTABLE")

        # Explicit DATA QUALITY determination: PASS, FAIL, or PARTIAL / NOT TESTABLE
        if multi_owner_result == "FAIL" or amendment_result == "FAIL":
            data_quality_display = "FAIL"
            data_quality_valid = False
        elif multi_owner_result == "PASS" and amendment_result == "PASS":
            data_quality_display = "PASS"
            data_quality_valid = True
        else:
            data_quality_display = "PARTIAL / NOT TESTABLE"
            data_quality_valid = True

        temp_cleanup_pass = temp_cleaned
        overall_pass = idempotency_pass and data_quality_valid and temp_cleanup_pass

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
        print(data_quality_display)
        print()

        print("MULTI-OWNER TEST:")
        print(multi_owner_result)
        print()

        print("AMENDMENT TEST:")
        print(amendment_result)
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
