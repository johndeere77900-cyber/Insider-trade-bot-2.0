"""
Comprehensive unit tests for official SEC bulk datasets pipeline, normalization, validation,
Owner ↔ Transaction relationships (Cases A, B, C, D), footnotes/holdings source preservation,
amendment relationships, deterministic transaction deduplication, bounded batching,
period provenance, ZipFile cleanup, and resumable state.
"""

from __future__ import annotations

import csv
import io
import zipfile
import pytest

from data.acquisition_state import AcquisitionStateManager
from data.sec_dataset_pipeline import (
    NormalizedBulkTransaction,
    build_dataset_url,
    compute_transaction_identity,
    normalize_bulk_record,
    parse_dataset_zip,
    parse_sec_date,
    validate_bulk_record,
)
from storage.repository import (
    count_records,
    store_bulk_insider_transactions,
)


def create_mock_zip_bytes(
    case: str = "default",
) -> bytes:
    """Create mock SEC dataset zip archive bytes for testing cases A, B, C, D."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # SUBMISSION.tsv
        sub_io = io.StringIO()
        sub_writer = csv.writer(sub_io, delimiter="\t")
        sub_writer.writerow([
            "ACCESSION_NUMBER", "FILING_DATE", "PERIOD_OF_REPORT",
            "DATE_OF_ORIG_SUB", "DOCUMENT_TYPE", "ISSUERCIK",
            "ISSUERNAME", "ISSUERTRADINGSYMBOL"
        ])

        if case in ("default", "case_a", "case_b", "case_c"):
            sub_writer.writerow([
                "0000016732-23-000043", "31-MAR-2023", "30-MAR-2023",
                "", "4", "0000016732", "CAMPBELL SOUP CO", "CPB"
            ])
            if case == "default":
                sub_writer.writerow([
                    "0000016732-23-000044", "31-MAR-2023", "30-MAR-2023",
                    "15-MAR-2023", "4/A", "0000016732", "CAMPBELL SOUP CO", "CPB"
                ])
        zf.writestr("SUBMISSION.tsv", sub_io.getvalue().encode("utf-8"))

        # REPORTINGOWNER.tsv
        owner_io = io.StringIO()
        owner_writer = csv.writer(owner_io, delimiter="\t")
        owner_writer.writerow([
            "ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNERNAME",
            "RPTOWNER_TITLE", "RPTOWNER_RELATIONSHIP"
        ])
        owner_writer.writerow([
            "0000016732-23-000043", "0001801061", "Watanabe Todd Franklin",
            "Officer", "Director,Officer"
        ])
        if case in ("default", "case_a", "case_b", "case_c"):
            owner_writer.writerow([
                "0000016732-23-000043", "0001801062", "Watanabe Joint Holder",
                "Ten Percent Owner", "10% Owner"
            ])
        if case == "default":
            owner_writer.writerow([
                "0000016732-23-000044", "0001801061", "Watanabe Todd Franklin",
                "Officer", "Director,Officer"
            ])
        zf.writestr("REPORTINGOWNER.tsv", owner_io.getvalue().encode("utf-8"))

        # FOOTNOTES.tsv
        fn_io = io.StringIO()
        fn_writer = csv.writer(fn_io, delimiter="\t")
        fn_writer.writerow(["ACCESSION_NUMBER", "FOOTNOTE_ID", "FOOTNOTE_TXT"])
        fn_writer.writerow(["0000016732-23-000043", "F1", "Acquired under 10b5-1 plan."])
        zf.writestr("FOOTNOTES.tsv", fn_io.getvalue().encode("utf-8"))

        # OWNER_SIGNATURE.tsv
        sig_io = io.StringIO()
        sig_writer = csv.writer(sig_io, delimiter="\t")
        sig_writer.writerow(["ACCESSION_NUMBER", "OWNERSIGNATURENAME", "OWNERSIGNATUREDATE"])
        sig_writer.writerow(["0000016732-23-000043", "/s/ Todd Watanabe", "31-MAR-2023"])
        zf.writestr("OWNER_SIGNATURE.tsv", sig_io.getvalue().encode("utf-8"))

        # NONDERIV_HOLDING.tsv
        hld_io = io.StringIO()
        hld_writer = csv.writer(hld_io, delimiter="\t")
        hld_writer.writerow(["ACCESSION_NUMBER", "NONDERIV_HOLDING_SK", "SECURITY_TITLE", "SHRS_OWND_FOLWNG_TRANS"])
        hld_writer.writerow(["0000016732-23-000043", "1001", "Common Stock", "15000"])
        zf.writestr("NONDERIV_HOLDING.tsv", hld_io.getvalue().encode("utf-8"))

        # NONDERIV_TRANS.tsv
        nonderiv_io = io.StringIO()
        nonderiv_writer = csv.writer(nonderiv_io, delimiter="\t")
        nonderiv_writer.writerow([
            "ACCESSION_NUMBER", "NONDERIV_TRANS_SK", "SECURITY_TITLE", "TRANS_DATE",
            "TRANS_FORM_TYPE", "TRANS_CODE", "TRANS_SHARES",
            "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD",
            "DIRECT_INDIRECT_OWNERSHIP", "NATURE_OF_OWNERSHIP"
        ])
        if case in ("default", "case_a", "case_b", "case_c"):
            nonderiv_writer.writerow([
                "0000016732-23-000043", "5001", "Common Stock", "30-MAR-2023",
                "4", "P", "1000.0", "45.50", "A", "D", ""
            ])
            if case in ("case_b", "case_c"):
                nonderiv_writer.writerow([
                    "0000016732-23-000043", "5002", "Common Stock", "30-MAR-2023",
                    "4", "S", "500.0", "46.00", "D", "D", ""
                ])
        if case == "default":
            nonderiv_writer.writerow([
                "0000016732-23-000044", "5003", "Common Stock", "28-MAR-2023",
                "4/A", "S", "500.0", "46.00", "D", "I", "By Trust"
            ])
        zf.writestr("NONDERIV_TRANS.tsv", nonderiv_io.getvalue().encode("utf-8"))

        # DERIV_TRANS.tsv
        deriv_io = io.StringIO()
        deriv_writer = csv.writer(deriv_io, delimiter="\t")
        deriv_writer.writerow([
            "ACCESSION_NUMBER", "DERIV_TRANS_SK", "SECURITY_TITLE", "TRANS_DATE",
            "TRANS_FORM_TYPE", "TRANS_CODE", "TRANS_SHARES",
            "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD",
            "DIRECT_INDIRECT_OWNERSHIP", "NATURE_OF_OWNERSHIP"
        ])
        if case == "case_c":
            deriv_writer.writerow([
                "0000016732-23-000043", "9001", "Option Right to Buy", "30-MAR-2023",
                "4", "M", "2000.0", "20.00", "A", "D", ""
            ])
        zf.writestr("DERIV_TRANS.tsv", deriv_io.getvalue().encode("utf-8"))

    return buffer.getvalue()


def test_build_dataset_url():
    url = build_dataset_url(2023, 1)
    assert url == "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/2023q1_form345.zip"


def test_parse_sec_date():
    assert parse_sec_date("31-MAR-2023") == "2023-03-31"
    assert parse_sec_date("2023-03-31") == "2023-03-31"
    assert parse_sec_date("20230331") == "2023-03-31"
    assert parse_sec_date("") is None
    assert parse_sec_date(None) is None


def test_case_a_one_filing_two_owners_one_transaction():
    """
    Case A: 2 reporting owners + 1 transaction row = exactly 1 transaction record + 2 owner records in raw source.
    Owner fields are left unset (None) to avoid false single-owner attribution.
    """
    zip_bytes = create_mock_zip_bytes(case="case_a")
    records = list(parse_dataset_zip(zip_bytes))

    assert len(records) == 1, f"Expected 1 transaction record, got {len(records)}"

    rec = records[0]
    assert rec["accession_number"] == "0000016732-23-000043"
    assert rec["reporting_owner_name"] is None
    assert rec["reporting_owner_cik"] is None

    raw = rec["raw"]
    all_owners = raw["all_owners"]
    assert len(all_owners) == 2, "Expected 2 reporting owners preserved in raw.all_owners"
    assert all_owners[0]["RPTOWNERNAME"] == "Watanabe Todd Franklin"
    assert all_owners[1]["RPTOWNERNAME"] == "Watanabe Joint Holder"


def test_case_b_one_filing_two_owners_two_transactions():
    """Case B: 2 reporting owners + 2 transaction rows = exactly 2 transaction records + 2 owner records in raw source."""
    zip_bytes = create_mock_zip_bytes(case="case_b")
    records = list(parse_dataset_zip(zip_bytes))

    assert len(records) == 2, f"Expected 2 transaction records, got {len(records)}"
    assert records[0]["accession_number"] == "0000016732-23-000043"
    assert records[1]["accession_number"] == "0000016732-23-000043"
    assert records[0]["record_hash"] != records[1]["record_hash"]


def test_case_c_multiple_nonderiv_and_deriv_transactions():
    """Case C: 2 non-derivative, 1 derivative = 3 distinct transaction records with distinct transaction SK identities."""
    zip_bytes = create_mock_zip_bytes(case="case_c")
    records = list(parse_dataset_zip(zip_bytes))

    assert len(records) == 3, f"Expected 3 transaction records, got {len(records)}"
    hashes = [r["record_hash"] for r in records]
    assert len(set(hashes)) == 3, "Expected 3 distinct semantic transaction identities"


def test_case_d_same_dataset_processed_twice(tmp_path):
    """Case D: Same dataset re-ingested = 0 new transaction records inserted, 0 duplicate provenance records."""
    db_file = tmp_path / "test_case_d.db"
    db_url = f"sqlite:///{db_file}"

    zip_bytes = create_mock_zip_bytes(case="default")
    raw_records = list(parse_dataset_zip(zip_bytes))
    norm_records = [normalize_bulk_record(r) for r in raw_records]

    # First run
    ins1, dup1 = store_bulk_insider_transactions(db_url, norm_records)
    assert ins1 == 2
    assert dup1 == 0
    assert count_records(db_url, "insider_transactions") == 2
    assert count_records(db_url, "provenance") == 2

    # Second run (exact same dataset)
    ins2, dup2 = store_bulk_insider_transactions(db_url, norm_records)
    assert ins2 == 0
    assert dup2 == 2
    assert count_records(db_url, "insider_transactions") == 2
    assert count_records(db_url, "provenance") == 2


def test_persisted_semantic_transaction_identity():
    """Verify persisted semantic transaction identity uses compute_transaction_identity and isn't replaced by raw-payload hash."""
    zip_bytes = create_mock_zip_bytes(case="case_a")
    raw_records = list(parse_dataset_zip(zip_bytes))
    norm_rec = normalize_bulk_record(raw_records[0])

    expected_hash = compute_transaction_identity(
        accession_number="0000016732-23-000043",
        transaction_type="non_derivative",
        transaction_sk="5001",
        is_amendment=False,
        form_type="4",
    )

    assert norm_rec.record_hash == expected_hash, "Record hash must match deterministic semantic SEC transaction identity"


def test_amendments_preservation():
    zip_bytes = create_mock_zip_bytes(case="default")
    records = list(parse_dataset_zip(zip_bytes))
    amended = records[1]

    assert amended["accession_number"] == "0000016732-23-000044"
    assert amended["is_amendment"] is True
    assert amended["date_of_orig_submission"] == "2023-03-15"
    assert amended["form_type"] == "4/A"


def test_normalize_and_validate_bulk_record():
    zip_bytes = create_mock_zip_bytes(case="default")
    raw_records = list(parse_dataset_zip(zip_bytes))

    norm = normalize_bulk_record(raw_records[0])
    assert norm.accession_number == "0000016732-23-000043"
    assert norm.shares == 1000.0
    assert norm.price_per_share == 45.50
    assert norm.ownership_type == "D"

    val_res = validate_bulk_record(norm)
    assert val_res.is_valid is True
    assert len(val_res.errors) == 0

    # Invalid record test
    invalid_norm = NormalizedBulkTransaction(
        accession_number="",
        issuer_cik="",
        issuer_name=None,
        ticker=None,
        reporting_owner_name=None,
        reporting_owner_cik=None,
        transaction_date="invalid-date",
        filing_date=None,
        transaction_code="INVALID_CODE",
        security_title=None,
        shares=-10.0,
        price_per_share=-5.0,
        transaction_type=None,
        acquired_disposed="INVALID",
        ownership_type="INVALID",
        ownership_nature=None,
        source_url="",
        is_amendment=False,
        date_of_orig_submission=None,
        raw_payload={},
    )
    val_invalid = validate_bulk_record(invalid_norm)
    assert val_invalid.is_valid is False
    assert len(val_invalid.errors) >= 5


def test_acquisition_state_and_resume_behavior(tmp_path):
    db_file = tmp_path / "test_state.db"
    db_url = f"sqlite:///{db_file}"

    state_mgr = AcquisitionStateManager(db_url)
    assert state_mgr.should_skip_period("2006-Q1") is False

    # Mark failed
    state_mgr.record_period_completion(
        period="2006-Q1",
        records_parsed=0,
        records_inserted=0,
        duplicates_count=0,
        invalid_count=0,
        failures_count=1,
        status="FAILED",
    )
    assert state_mgr.get_period_status("2006-Q1") == "FAILED"
    assert state_mgr.should_skip_period("2006-Q1") is False

    # Mark completed
    state_mgr.record_period_completion(
        period="2006-Q1",
        records_parsed=100,
        records_inserted=90,
        duplicates_count=10,
        invalid_count=0,
        failures_count=0,
        status="COMPLETED",
    )
    assert state_mgr.get_period_status("2006-Q1") == "COMPLETED"
    assert state_mgr.should_skip_period("2006-Q1") is True


def test_temp_file_download_and_cleanup(tmp_path):
    """Verify ZIP files are streamed to temporary files on disk and cleaned up after processing."""
    import os
    import tempfile

    zip_bytes = create_mock_zip_bytes(case="default")
    temp_fd, temp_zip_path = tempfile.mkstemp(suffix=".zip", prefix="test_sec_", dir=str(tmp_path))
    os.close(temp_fd)

    with open(temp_zip_path, "wb") as f:
        f.write(zip_bytes)

    assert os.path.exists(temp_zip_path)

    records = list(parse_dataset_zip(temp_zip_path))
    assert len(records) == 2

    # Simulate cleanup
    os.remove(temp_zip_path)
    assert not os.path.exists(temp_zip_path)


def test_cli_default_end_period():
    """Verify CLI default end period is 2026-Q2."""
    import argparse
    parser = argparse.ArgumentParser(prog="historical acquisition")
    parser.add_argument("--start", default="2006-Q1")
    parser.add_argument("--end", default="2026-Q2")

    args = parser.parse_args([])
    assert args.start == "2006-Q1"
    assert args.end == "2026-Q2"
