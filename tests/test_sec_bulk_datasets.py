"""
Unit tests for official SEC bulk datasets pipeline, normalization, validation,
deduplication, temporal integrity, amendments, provenance, and resumable state.
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
    """Create mock SEC dataset zip archive bytes in memory."""
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
        owner_writer.writerow([
            "0000016732-23-000044", "0001801061", "Watanabe Todd Franklin",
            "Officer", "Director,Officer"
        ])
        zf.writestr("REPORTINGOWNER.tsv", owner_io.getvalue().encode("utf-8"))

        # NONDERIV_TRANS.tsv
        nonderiv_io = io.StringIO()
        nonderiv_writer = csv.writer(nonderiv_io, delimiter="\t")
        nonderiv_writer.writerow([
            "ACCESSION_NUMBER", "SECURITY_TITLE", "TRANS_DATE",
            "TRANS_FORM_TYPE", "TRANS_CODE", "TRANS_SHARES",
            "TRANS_PRICEPERSHARE", "TRANS_ACQUIRED_DISP_CD",
            "DIRECT_INDIRECT_OWNERSHIP", "NATURE_OF_OWNERSHIP"
        ])
        nonderiv_writer.writerow([
            "0000016732-23-000043", "Common Stock", "30-MAR-2023",
            "4", "P", "1000.0", "45.50", "A", "D", ""
        ])
        nonderiv_writer.writerow([
            "0000016732-23-000044", "Common Stock", "28-MAR-2023",
            "4/A", "S", "500.0", "46.00", "D", "I", "By Trust"
        ])
        zf.writestr("NONDERIV_TRANS.tsv", nonderiv_io.getvalue().encode("utf-8"))

        # DERIV_TRANS.tsv (empty data)
        deriv_io = io.StringIO()
        deriv_writer = csv.writer(deriv_io, delimiter="\t")
        deriv_writer.writerow([
            "ACCESSION_NUMBER", "SECURITY_TITLE", "TRANS_DATE",
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


def test_parse_dataset_zip_and_amendments():
    zip_bytes = create_mock_zip_bytes()
    records = list(parse_dataset_zip(zip_bytes))
    assert len(records) == 2

    r1, r2 = records[0], records[1]
    assert r1["accession_number"] == "0000016732-23-000043"
    assert r1["filing_date"] == "2023-03-31"
    assert r1["transaction_date"] == "2023-03-30"
    assert r1["transaction_code"] == "P"
    assert r1["is_amendment"] is False

    assert r2["accession_number"] == "0000016732-23-000044"
    assert r2["is_amendment"] is True
    assert r2["date_of_orig_submission"] == "2023-03-15"


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
        transaction_code=None,
        security_title=None,
        shares=None,
        price_per_share=None,
        transaction_type=None,
        acquired_disposed=None,
        ownership_type=None,
        ownership_nature=None,
        source_url="",
        is_amendment=False,
        date_of_orig_submission=None,
        raw_payload={},
    )
    val_invalid = validate_bulk_record(invalid_norm)
    assert val_invalid.is_valid is False
    assert len(val_invalid.errors) >= 3


def test_bulk_store_and_deduplication(tmp_path):
    db_file = tmp_path / "test_bulk.db"
    db_url = f"sqlite:///{db_file}"

    zip_bytes = create_mock_zip_bytes()
    raw_records = list(parse_dataset_zip(zip_bytes))
    norm_records = [normalize_bulk_record(r) for r in raw_records]

    # First store
    inserted, duplicates = store_bulk_insider_transactions(db_url, norm_records)
    assert inserted == 2
    assert duplicates == 0
    assert count_records(db_url, "insider_transactions") == 2
    assert count_records(db_url, "provenance") == 2

    # Second store (idempotent rerun)
    inserted_2, duplicates_2 = store_bulk_insider_transactions(db_url, norm_records)
    assert inserted_2 == 0
    assert duplicates_2 == 2
    assert count_records(db_url, "insider_transactions") == 2


def test_acquisition_state_manager(tmp_path):
    db_file = tmp_path / "test_state.db"
    db_url = f"sqlite:///{db_file}"

    state_mgr = AcquisitionStateManager(db_url)
    assert state_mgr.is_period_completed("2006-Q1") is False

    state_mgr.record_period_completion(
        period="2006-Q1",
        records_parsed=100,
        records_inserted=90,
        duplicates_count=10,
        invalid_count=0,
        failures_count=0,
    )

    assert state_mgr.is_period_completed("2006-Q1") is True
    assert state_mgr.get_completed_periods() == ["2006-Q1"]

    periods = state_mgr.parse_period_range("2006-Q1", "2006-Q3")
    assert len(periods) == 3
    assert periods[0] == (2006, 1, "2006-Q1")
    assert periods[2] == (2006, 3, "2006-Q3")
