"""
Comprehensive unit tests for official SEC bulk datasets pipeline, normalization, validation,
multiple reporting owners, footnotes/holdings source preservation, amendment relationships,
deterministic transaction deduplication, bounded batching, period provenance, and resumable state.
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
    normalize_bulk_record,
    parse_dataset_zip,
    parse_sec_date,
    validate_bulk_record,
)
from storage.repository import (
    count_records,
    store_bulk_insider_transactions,
)


def create_mock_zip_bytes() -> bytes:
    """Create mock SEC dataset zip archive bytes with multi-owner, footnotes, holdings, and amendments."""
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
        sub_writer.writerow([
            "0000016732-23-000043", "31-MAR-2023", "30-MAR-2023",
            "", "4", "0000016732", "CAMPBELL SOUP CO", "CPB"
        ])
        sub_writer.writerow([
            "0000016732-23-000044", "31-MAR-2023", "30-MAR-2023",
            "15-MAR-2023", "4/A", "0000016732", "CAMPBELL SOUP CO", "CPB"
        ])
        zf.writestr("SUBMISSION.tsv", sub_io.getvalue().encode("utf-8"))

        # REPORTINGOWNER.tsv (contains 2 owners for 0000016732-23-000043)
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
        owner_writer.writerow([
            "0000016732-23-000043", "0001801062", "Watanabe Joint Holder",
            "Ten Percent Owner", "10% Owner"
        ])
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
        nonderiv_writer.writerow([
            "0000016732-23-000043", "5001", "Common Stock", "30-MAR-2023",
            "4", "P", "1000.0", "45.50", "A", "D", ""
        ])
        nonderiv_writer.writerow([
            "0000016732-23-000044", "5002", "Common Stock", "28-MAR-2023",
            "4/A", "S", "500.0", "46.00", "D", "I", "By Trust"
        ])
        zf.writestr("NONDERIV_TRANS.tsv", nonderiv_io.getvalue().encode("utf-8"))

        # DERIV_TRANS.tsv (empty data)
        deriv_io = io.StringIO()
        deriv_writer = csv.writer(deriv_io, delimiter="\t")
        deriv_writer.writerow([
            "ACCESSION_NUMBER", "DERIV_TRANS_SK", "SECURITY_TITLE", "TRANS_DATE",
            "TRANS_FORM_TYPE", "TRANS_CODE", "TRANS_SHARES",
            "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD",
            "DIRECT_INDIRECT_OWNERSHIP", "NATURE_OF_OWNERSHIP"
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


def test_multiple_reporting_owners_and_source_preservation():
    zip_bytes = create_mock_zip_bytes()
    records = list(parse_dataset_zip(zip_bytes))
    # 2 owners for filing 43 + 1 owner for filing 44 = 3 records total
    assert len(records) == 3

    r1, r2, r3 = records[0], records[1], records[2]

    # Verify multiple reporting owners
    assert r1["accession_number"] == "0000016732-23-000043"
    assert r1["reporting_owner_name"] == "Watanabe Todd Franklin"

    assert r2["accession_number"] == "0000016732-23-000043"
    assert r2["reporting_owner_name"] == "Watanabe Joint Holder"

    # Distinct hashes for separate owners
    assert r1["record_hash"] != r2["record_hash"]

    # Source data preservation (footnotes, signatures, holdings)
    raw = r1["raw"]
    assert len(raw["footnotes"]) == 1
    assert raw["footnotes"][0]["FOOTNOTE_TXT"] == "Acquired under 10b5-1 plan."
    assert len(raw["signatures"]) == 1
    assert raw["signatures"][0]["OWNERSIGNATURENAME"] == "/s/ Todd Watanabe"
    assert len(raw["holdings"]) == 1


def test_amendments_preservation():
    zip_bytes = create_mock_zip_bytes()
    records = list(parse_dataset_zip(zip_bytes))
    amended = records[2]

    assert amended["accession_number"] == "0000016732-23-000044"
    assert amended["is_amendment"] is True
    assert amended["date_of_orig_submission"] == "2023-03-15"
    assert amended["form_type"] == "4/A"


def test_normalize_and_validate_bulk_record():
    zip_bytes = create_mock_zip_bytes()
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


def test_bulk_store_and_deduplication(tmp_path):
    db_file = tmp_path / "test_bulk.db"
    db_url = f"sqlite:///{db_file}"

    zip_bytes = create_mock_zip_bytes()
    raw_records = list(parse_dataset_zip(zip_bytes))
    norm_records = [normalize_bulk_record(r) for r in raw_records]

    # First store
    inserted, duplicates = store_bulk_insider_transactions(db_url, norm_records)
    assert inserted == 3
    assert duplicates == 0
    assert count_records(db_url, "insider_transactions") == 3
    assert count_records(db_url, "provenance") == 3

    # Second store (idempotent rerun)
    inserted_2, duplicates_2 = store_bulk_insider_transactions(db_url, norm_records)
    assert inserted_2 == 0
    assert duplicates_2 == 3
    assert count_records(db_url, "insider_transactions") == 3


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
    # FAILED period should NOT be skipped on rerun
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
