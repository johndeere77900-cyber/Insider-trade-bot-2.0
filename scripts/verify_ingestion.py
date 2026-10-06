"""
Verification Script for SEC Historical Ingestion into Database (Neon PostgreSQL or SQLite).

Validates:
- Run 1 data ingestion, provenance, ingestion_state, and data quality rules strictly scoped to period.
- Multi-owner handling and amendment preservation (PASS / FAIL / NOT TESTABLE) without self-comparison.
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
from data.acquisition_state import AcquisitionStateManager
from database.connection import connect, is_postgresql_url
from storage.repository import _row_value


from typing import Sequence

def json_safe_value(value: Any) -> Any:
    """Return ISO formatted string if value is date/datetime or has isoformat attribute."""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def get_field(row: Any, key: str, columns: Optional[Sequence[str]] = None) -> Any:
    """Safely retrieve a column by name from dict, sqlite3.Row, or tuple/row."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, "keys"):
        try:
            return row[key]
        except (IndexError, KeyError, TypeError):
            pass
    if isinstance(row, (tuple, list)):
        if columns is not None and key in columns:
            idx = columns.index(key)
            if idx < len(row):
                return row[idx]
        if len(row) == 1:
            return row[0]
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
    """Execute query, fetch single row, and normalize to dict using cursor.description if available."""
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
    """Execute query, fetch all rows, and normalize each to dict using cursor.description if available."""
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
    """Perform Run 1 database verification strictly scoped to period."""
    db_url = get_db_url()
    print(f"Running Run 1 verification for period {period} on database...")

    start_date, end_date = get_period_date_bounds(period)

    with connect(db_url) as conn:
        # 1. Total database records
        row = query_one(conn, db_url, "SELECT COUNT(*) AS c FROM insider_transactions")
        total_tx_count = int(get_field(row, "c", ["c"]))

        # 2. Strict Period records count (WHERE filing_date BETWEEN start_date AND end_date)
        period_count_sql = (
            "SELECT COUNT(*) AS c FROM insider_transactions WHERE filing_date >= %s AND filing_date <= %s"
            if is_postgresql_url(db_url) else
            "SELECT COUNT(*) AS c FROM insider_transactions WHERE filing_date >= ? AND filing_date <= ?"
        )
        row = query_one(conn, db_url, period_count_sql, (start_date, end_date))
        period_tx_count = int(get_field(row, "c", ["c"]))

        if period_tx_count == 0:
            print(f"ERROR: 0 records found for period {period} (filing_date between {start_date} and {end_date}).", file=sys.stderr)
            sys.exit(1)

        # Period transaction date range
        date_range_cols = ["min_d", "max_d"]
        date_range_sql = (
            "SELECT MIN(transaction_date) AS min_d, MAX(transaction_date) AS max_d "
            "FROM insider_transactions WHERE filing_date >= %s AND filing_date <= %s "
            "AND transaction_date IS NOT NULL"
            if is_postgresql_url(db_url) else
            "SELECT MIN(transaction_date) AS min_d, MAX(transaction_date) AS max_d "
            "FROM insider_transactions WHERE filing_date >= ? AND filing_date <= ? "
            "AND transaction_date IS NOT NULL AND transaction_date != ''"
        )
        row = query_one(conn, db_url, date_range_sql, (start_date, end_date))
        earliest_date = get_field(row, "min_d", date_range_cols)
        latest_date = get_field(row, "max_d", date_range_cols)

        # Period distinct accession numbers
        period_acc_sql = (
            "SELECT COUNT(DISTINCT accession_number) AS c FROM insider_transactions WHERE filing_date >= %s AND filing_date <= %s"
            if is_postgresql_url(db_url) else
            "SELECT COUNT(DISTINCT accession_number) AS c FROM insider_transactions WHERE filing_date >= ? AND filing_date <= ?"
        )
        row = query_one(conn, db_url, period_acc_sql, (start_date, end_date))
        distinct_accessions = int(get_field(row, "c", ["c"]))

        # Period distinct record hashes
        period_hash_sql = (
            "SELECT COUNT(DISTINCT record_hash) AS c FROM insider_transactions WHERE filing_date >= %s AND filing_date <= %s"
            if is_postgresql_url(db_url) else
            "SELECT COUNT(DISTINCT record_hash) AS c FROM insider_transactions WHERE filing_date >= ? AND filing_date <= ?"
        )
        row = query_one(conn, db_url, period_hash_sql, (start_date, end_date))
        distinct_hashes = int(get_field(row, "c", ["c"]))

        print(f"Total database count: {total_tx_count}")
        print(f"Period {period} record count: {period_tx_count}")
        print(f"Period earliest transaction date: {earliest_date}")
        print(f"Period latest transaction date: {latest_date}")
        print(f"Period distinct accession numbers: {distinct_accessions}")
        print(f"Period distinct record hashes: {distinct_hashes}")

        # Provenance checks
        prov_cols = ["record_type", "record_id", "source", "source_reference", "retrieved_at", "checksum", "validation_status"]
        prov_sql = (
            f"SELECT {', '.join(prov_cols)} FROM provenance WHERE record_type = %s AND record_id = %s AND source = %s"
            if is_postgresql_url(db_url) else
            f"SELECT {', '.join(prov_cols)} FROM provenance WHERE record_type = ? AND record_id = ? AND source = ?"
        )
        row = query_one(conn, db_url, prov_sql, ("dataset_period", period, "SEC"))

        if not row:
            print(f"ERROR: Missing provenance record for dataset_period {period}.", file=sys.stderr)
            sys.exit(1)

        prov_source = get_field(row, "source", prov_cols)
        prov_ref = get_field(row, "source_reference", prov_cols)
        prov_checksum = get_field(row, "checksum", prov_cols)
        prov_status = get_field(row, "validation_status", prov_cols)

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
        total_prov_count = int(get_field(row, "c", ["c"]))

        # Ingestion_state checks
        ingest_cols = ["period", "status", "records_parsed", "records_inserted", "duplicates_count", "invalid_count", "failures_count", "completed_at"]
        ingest_sql = (
            f"SELECT {', '.join(ingest_cols)} FROM ingestion_state WHERE period = %s"
            if is_postgresql_url(db_url) else
            f"SELECT {', '.join(ingest_cols)} FROM ingestion_state WHERE period = ?"
        )
        row = query_one(conn, db_url, ingest_sql, (period,))

        if not row:
            print(f"ERROR: Missing ingestion_state record for period {period}.", file=sys.stderr)
            sys.exit(1)

        status = get_field(row, "status", ingest_cols)
        records_parsed = int(get_field(row, "records_parsed", ingest_cols) or 0)
        records_inserted = int(get_field(row, "records_inserted", ingest_cols) or 0)
        duplicates_count = int(get_field(row, "duplicates_count", ingest_cols) or 0)
        invalid_count = int(get_field(row, "invalid_count", ingest_cols) or 0)
        failures_count = int(get_field(row, "failures_count", ingest_cols) or 0)

        if status != "COMPLETED":
            print(f"ERROR: Ingestion status is '{status}', expected 'COMPLETED'.", file=sys.stderr)
            sys.exit(1)

        if failures_count != 0:
            print(f"ERROR: Ingestion state reports failures_count = {failures_count}.", file=sys.stderr)
            sys.exit(1)

        if records_inserted == 0:
            print("ERROR: Ingestion state reports records_inserted = 0.", file=sys.stderr)
            sys.exit(1)

        # Strict Period-Scoped Data Quality: Multi-Owner and Amendment checks
        period_tx_cols = [
            "accession_number", "issuer_cik", "record_hash", "source",
            "insider_name", "insider_cik", "form_type", "filing_date",
            "is_amendment", "date_of_orig_submission", "raw_payload"
        ]
        period_sql = (
            f"SELECT {', '.join(period_tx_cols)} "
            "FROM insider_transactions WHERE filing_date >= %s AND filing_date <= %s"
            if is_postgresql_url(db_url) else
            f"SELECT {', '.join(period_tx_cols)} "
            "FROM insider_transactions WHERE filing_date >= ? AND filing_date <= ?"
        )
        period_rows = query_all(conn, db_url, period_sql, (start_date, end_date))

        # Check if archive-backed raw details are needed (lean storage mode where raw_payload is NULL in Neon)
        archive_raw_by_hash = {}
        archive_genuinely_absent = False
        if any(get_field(r, "raw_payload", period_tx_cols) is None for r in period_rows):
            from archive import ArchiveError, ArchiveNotFoundError, get_archive_backend
            from data.sec_dataset_pipeline import parse_dataset_zip
            settings = load_environment()
            archive_kwargs = {}
            if settings.sec_archive_bucket:
                archive_kwargs["bucket"] = settings.sec_archive_bucket
            if settings.sec_archive_endpoint_url:
                archive_kwargs["endpoint_url"] = settings.sec_archive_endpoint_url

            archive_backend = get_archive_backend(
                backend_type=settings.sec_archive_backend,
                archive_path=settings.sec_archive_path,
                **archive_kwargs,
            )

            if archive_backend.exists(period):
                zip_bytes = archive_backend.get(period)
                for rec in parse_dataset_zip(zip_bytes):
                    h = rec.get("record_hash")
                    if h:
                        archive_raw_by_hash[h] = rec.get("raw", {})
            else:
                archive_genuinely_absent = True

        dq_pass = True

        multi_owner_found = False
        multi_owner_valid = True

        amendment_rows = []
        original_rows_by_acc: Dict[str, list] = {}
        all_period_hashes = set()

        for r in period_rows:
            acc = get_field(r, "accession_number", period_tx_cols)
            cik = get_field(r, "issuer_cik", period_tx_cols)
            rec_hash = get_field(r, "record_hash", period_tx_cols)
            source = get_field(r, "source", period_tx_cols)
            raw_str = get_field(r, "raw_payload", period_tx_cols)

            if not acc or not cik or not rec_hash or source != "SEC":
                print(f"ERROR: Record failed required field check: acc={acc}, cik={cik}, hash={rec_hash}, source={source}", file=sys.stderr)
                dq_pass = False
                break

            all_period_hashes.add(rec_hash)

            raw_obj = None
            if raw_str is not None:
                try:
                    raw_obj = json.loads(raw_str) if isinstance(raw_str, str) else raw_str
                except Exception:
                    print(f"ERROR: Raw payload JSON unparseable for record {acc}", file=sys.stderr)
                    dq_pass = False
                    break
            else:
                raw_obj = archive_raw_by_hash.get(rec_hash)

            # Multi-owner evaluation
            insider_name = get_field(r, "insider_name", period_tx_cols)
            insider_cik = get_field(r, "insider_cik", period_tx_cols)

            if raw_obj is not None:
                all_owners = raw_obj.get("all_owners", []) if isinstance(raw_obj, dict) else []
                if len(all_owners) > 1:
                    multi_owner_found = True
                    if insider_name is not None or insider_cik is not None:
                        print(f"ERROR: Multi-owner filing {acc} incorrectly assigned top-level insider_name={insider_name}, insider_cik={insider_cik}", file=sys.stderr)
                        multi_owner_valid = False

            # Amendment evaluation
            form_t = str(get_field(r, "form_type", period_tx_cols) or "")
            is_amend_db = get_field(r, "is_amendment", period_tx_cols)
            date_orig_db = get_field(r, "date_of_orig_submission", period_tx_cols)

            doc_type = ""
            date_orig = date_orig_db or ""
            if raw_obj is not None:
                sub_info = raw_obj.get("submission", {}) if isinstance(raw_obj, dict) else {}
                doc_type = str(sub_info.get("DOCUMENT_TYPE", ""))
                if not date_orig:
                    date_orig = str(sub_info.get("DATE_OF_ORIG_SUB", ""))

            is_amend = bool(is_amend_db) or doc_type.endswith("/A") or form_t.endswith("/A") or bool(date_orig and str(date_orig).strip())

            if is_amend:
                amendment_rows.append((acc, rec_hash, date_orig, doc_type, raw_obj))
            else:
                if acc not in original_rows_by_acc:
                    original_rows_by_acc[acc] = []
                original_rows_by_acc[acc].append((rec_hash, r))

        # Strict Amendment Preservation Verification
        amendment_result = "NOT TESTABLE"
        if amendment_rows:
            distinct_amendment_proven = False
            amendment_failed = False

            for acc, rec_hash, date_orig, doc_type, raw_obj in amendment_rows:
                if not acc or not rec_hash or rec_hash not in all_period_hashes:
                    amendment_failed = True
                    break

                sub_info = raw_obj.get("submission", {}) if isinstance(raw_obj, dict) else {}
                orig_acc = sub_info.get("ACCESSION_NUMBER") or acc

                # Check if a separate original filing record exists in original_rows_by_acc
                matching_origs = original_rows_by_acc.get(orig_acc) or original_rows_by_acc.get(acc)
                if matching_origs:
                    for orig_hash, orig_r in matching_origs:
                        if orig_hash != rec_hash:
                            distinct_amendment_proven = True
                            break

            if amendment_failed:
                amendment_result = "FAIL"
            elif distinct_amendment_proven:
                amendment_result = "PASS"
            else:
                amendment_result = "NOT TESTABLE"

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
            "total_tx_count": total_tx_count,
            "period_tx_count": period_tx_count,
            "provenance_count": total_prov_count,
            "status": status,
            "earliest_date": json_safe_value(earliest_date),
            "latest_date": json_safe_value(latest_date),
            "multi_owner_result": multi_owner_result,
            "amendment_result": amendment_result,
        }

        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(run1_data, f, indent=2)

        print(f"Run 1 verification PASSED. Total DB Records: {total_tx_count}, Period {period} Records: {period_tx_count}. Multi-Owner: {multi_owner_result}, Amendment: {amendment_result}. Saved state to {state_file}.")
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

    start_date, end_date = get_period_date_bounds(period)

    with connect(db_url) as conn:
        # Total insider_transactions count check
        row = query_one(conn, db_url, "SELECT COUNT(*) AS c FROM insider_transactions")
        total_tx_count_run2 = int(get_field(row, "c", ["c"]))

        # Period-specific insider_transactions count check
        period_count_sql = (
            "SELECT COUNT(*) AS c FROM insider_transactions WHERE filing_date >= %s AND filing_date <= %s"
            if is_postgresql_url(db_url) else
            "SELECT COUNT(*) AS c FROM insider_transactions WHERE filing_date >= ? AND filing_date <= ?"
        )
        row = query_one(conn, db_url, period_count_sql, (start_date, end_date))
        period_tx_count_run2 = int(get_field(row, "c", ["c"]))

        # Provenance count check
        row = query_one(conn, db_url, "SELECT COUNT(*) AS c FROM provenance")
        prov_count_run2 = int(get_field(row, "c", ["c"]))

        # Ingestion_state check
        ingest_cols = ["period", "status", "records_parsed", "records_inserted", "duplicates_count", "invalid_count", "failures_count", "completed_at"]
        ingest_sql = (
            f"SELECT {', '.join(ingest_cols)} FROM ingestion_state WHERE period = %s"
            if is_postgresql_url(db_url) else
            f"SELECT {', '.join(ingest_cols)} FROM ingestion_state WHERE period = ?"
        )
        row = query_one(conn, db_url, ingest_sql, (period,))

        if not row:
            print(f"ERROR: Missing ingestion_state record for period {period} on run 2.", file=sys.stderr)
            sys.exit(1)

        status_run2 = get_field(row, "status", ingest_cols)
        run2_parsed = int(get_field(row, "records_parsed", ingest_cols) or 0)
        run2_inserted = int(get_field(row, "records_inserted", ingest_cols) or 0)
        run2_duplicates = int(get_field(row, "duplicates_count", ingest_cols) or 0)
        run2_invalid = int(get_field(row, "invalid_count", ingest_cols) or 0)
        run2_failures = int(get_field(row, "failures_count", ingest_cols) or 0)

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
        if total_tx_count_run2 != run1["total_tx_count"]:
            idempotency_pass = False
            idempotency_errors.append(
                f"Total insider_transactions count changed from {run1['total_tx_count']} to {total_tx_count_run2}"
            )

        # 5. Period insider transactions count must NOT increase
        if period_tx_count_run2 != run1["period_tx_count"]:
            idempotency_pass = False
            idempotency_errors.append(
                f"Period {period} insider_transactions count changed from {run1['period_tx_count']} to {period_tx_count_run2}"
            )

        # 6. Provenance count must not increase unexpectedly
        if prov_count_run2 != run1["provenance_count"]:
            idempotency_pass = False
            idempotency_errors.append(
                f"provenance count changed from {run1['provenance_count']} to {prov_count_run2}"
            )

        # 7. Status must remain COMPLETED
        if status_run2 != "COMPLETED":
            idempotency_pass = False
            idempotency_errors.append(f"ingestion_state status is '{status_run2}', expected 'COMPLETED'")

        # 8. Failures must remain 0
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
        print(f"- total insider_transactions count: {total_tx_count_run2}")
        print(f"- period {period} insider_transactions count: {period_tx_count_run2}")
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


def verify_range(start_period: str, end_period: str) -> int:
    """Verify a historical period range and output summary report."""
    db_url = get_db_url()
    state_mgr = AcquisitionStateManager(db_url)
    period_range = state_mgr.parse_period_range(start_period, end_period)

    requested_periods = [p_str for _, _, p_str in period_range]
    periods_requested_count = len(requested_periods)

    with connect(db_url) as conn:
        # Get ingestion states for all requested periods
        ingest_cols = ["period", "status", "records_parsed", "records_inserted", "duplicates_count", "invalid_count", "failures_count"]
        placeholders = ", ".join("%s" if is_postgresql_url(db_url) else "?" for _ in requested_periods)
        ingest_sql = f"SELECT {', '.join(ingest_cols)} FROM ingestion_state WHERE period IN ({placeholders})"
        ingest_rows = query_all(conn, db_url, ingest_sql, tuple(requested_periods))

        state_by_period = {get_field(r, "period", ingest_cols): r for r in ingest_rows}

        periods_completed = 0
        periods_failed = 0
        total_parsed = 0
        total_inserted = 0
        total_duplicates = 0
        total_invalid = 0

        for p_str in requested_periods:
            st_row = state_by_period.get(p_str)
            if not st_row:
                periods_failed += 1
                continue

            status = get_field(st_row, "status", ingest_cols)
            parsed = int(get_field(st_row, "records_parsed", ingest_cols) or 0)
            inserted = int(get_field(st_row, "records_inserted", ingest_cols) or 0)
            dups = int(get_field(st_row, "duplicates_count", ingest_cols) or 0)
            invalids = int(get_field(st_row, "invalid_count", ingest_cols) or 0)

            total_parsed += parsed
            total_inserted += inserted
            total_duplicates += dups
            total_invalid += invalids

            if status == "COMPLETED":
                periods_completed += 1
            else:
                periods_failed += 1

        # Count provenance records strictly scoped to requested periods
        prov_placeholders = ", ".join("%s" if is_postgresql_url(db_url) else "?" for _ in requested_periods)
        prov_sql = (
            f"SELECT COUNT(*) AS c FROM provenance WHERE record_type = 'dataset_period' AND source = 'SEC' AND record_id IN ({prov_placeholders})"
        )
        row = query_one(conn, db_url, prov_sql, tuple(requested_periods))
        provenance_records = int(get_field(row, "c", ["c"])) if row else 0

        # Count ingestion_state records strictly scoped to requested periods
        ingest_count_placeholders = ", ".join("%s" if is_postgresql_url(db_url) else "?" for _ in requested_periods)
        ingest_count_sql = f"SELECT COUNT(*) AS c FROM ingestion_state WHERE period IN ({ingest_count_placeholders})"
        row = query_one(conn, db_url, ingest_count_sql, tuple(requested_periods))
        ingestion_states = int(get_field(row, "c", ["c"])) if row else 0

        # Calculate transaction date range scoped to requested periods
        min_start_date, _ = get_period_date_bounds(requested_periods[0])
        _, max_end_date = get_period_date_bounds(requested_periods[-1])

        tx_date_cols = ["min_d", "max_d"]
        tx_date_sql = (
            "SELECT MIN(transaction_date) AS min_d, MAX(transaction_date) AS max_d "
            "FROM insider_transactions WHERE filing_date >= %s AND filing_date <= %s "
            "AND transaction_date IS NOT NULL"
            if is_postgresql_url(db_url) else
            "SELECT MIN(transaction_date) AS min_d, MAX(transaction_date) AS max_d "
            "FROM insider_transactions WHERE filing_date >= ? AND filing_date <= ? "
            "AND transaction_date IS NOT NULL AND transaction_date != ''"
        )
        row = query_one(conn, db_url, tx_date_sql, (min_start_date, max_end_date))
        earliest_tx = get_field(row, "min_d", tx_date_cols) if row else None
        latest_tx = get_field(row, "max_d", tx_date_cols) if row else None

    overall_pass = (periods_failed == 0) and (periods_completed == periods_requested_count)

    print("\nHISTORICAL SEC BACKFILL\n")
    print("Requested range:")
    print(f"{start_period} → {end_period}\n")
    print(f"Periods requested:     {periods_requested_count}")
    print(f"Periods completed:     {periods_completed}")
    print(f"Periods failed:        {periods_failed}\n")
    print(f"Records parsed:        {total_parsed}")
    print(f"Records inserted:      {total_inserted}")
    print(f"Duplicates:            {total_duplicates}")
    print(f"Invalid:               {total_invalid}\n")
    print(f"Provenance records:    {provenance_records}")
    print(f"Ingestion states:      {ingestion_states}\n")
    print(f"Earliest transaction:  {earliest_tx}")
    print(f"Latest transaction:    {latest_tx}\n")
    print(f"OVERALL: {'PASS' if overall_pass else 'FAIL'}\n")

    if not overall_pass:
        print("ERROR: Historical backfill range verification failed.", file=sys.stderr)
        return 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify SEC historical ingestion.")
    parser.add_argument("--run", type=int, choices=[1, 2], help="Run number to verify (1 or 2)")
    parser.add_argument("--period", default="2006-Q1", help="Target SEC dataset period")
    parser.add_argument("--state-file", default="/tmp/sec_run1_stats.json", help="Path to JSON state file between runs")
    parser.add_argument("--verify-range", action="store_true", help="Verify range of historical periods")
    parser.add_argument("--start", default="2006-Q1", help="Start period for range verification")
    parser.add_argument("--end", default="2010-Q4", help="End period for range verification")

    args = parser.parse_args()

    if args.verify_range:
        return verify_range(args.start, args.end)

    if args.run == 1:
        return verify_run1(args.period, args.state_file)
    elif args.run == 2:
        return verify_run2(args.period, args.state_file)
    else:
        parser.error("Either --run {1,2} or --verify-range must be provided.")


if __name__ == "__main__":
    sys.exit(main())
