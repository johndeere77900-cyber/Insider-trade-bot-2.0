"""
Focused regression tests for historical SEC acquisition safety, retry semantics, and lean storage propagation.
"""

from __future__ import annotations

import os
import zipfile
import pytest

from archive import FilesystemSECArchive, get_archive_backend
from data.acquisition_state import AcquisitionStateManager
from main import run_historical_acquisition
from storage.repository import count_records, store_bulk_insider_transactions
from data.sec_dataset_pipeline import NormalizedBulkTransaction


def test_archive_survives_ingestion_failure_and_retry_reuses_archive(tmp_path, monkeypatch):
    db_file = tmp_path / "acq_test.db"
    db_url = f"sqlite:///{db_file}"
    archive_dir = tmp_path / "archive"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "TestBot/1.0 test@example.com")
    monkeypatch.setenv("SEC_ARCHIVE_BACKEND", "filesystem")
    monkeypatch.setenv("SEC_ARCHIVE_PATH", str(archive_dir))
    monkeypatch.setenv("SEC_STORE_RAW_PAYLOAD", "false")

    # 1. Prepare dummy zip for 2006-Q1
    period = "2006-Q1"
    archive = FilesystemSECArchive(base_path=str(archive_dir))

    zip_file = tmp_path / "dummy_2006Q1.zip"
    with zipfile.ZipFile(zip_file, "w") as zf:
        zf.writestr(
            "SUBMISSION.tsv",
            "ACCESSION_NUMBER\tISSUER_CIK\tISSUER_NAME\tFILING_DATE\n"
            "0000000001-06-000001\t0000320193\tApple Inc.\t2006-01-15\n",
        )

    # Put dummy archive directly in archive layer
    meta = archive.put(period, str(zip_file))
    assert archive.exists(period) is True

    # 2. Simulate ingestion failure on first run by raising exception in parse_dataset_zip
    def mock_parse_fail(*args, **kwargs):
        raise RuntimeError("Simulated DB connection drop during ingestion")

    monkeypatch.setattr("data.sec_dataset_pipeline.parse_dataset_zip", mock_parse_fail)

    state_mgr = AcquisitionStateManager(db_url)

    # Run historical acquisition (should fail and mark FAILED)
    res_code = run_historical_acquisition("2006-Q1", "2006-Q1")
    assert res_code == 1
    assert state_mgr.get_period_status(period) == "FAILED"

    # CRITICAL VERIFICATION: Archive remains intact after ingestion failure
    assert archive.exists(period) is True
    assert archive.checksum(period) == meta.sha256

    # 3. Simulate fixed ingestion on retry
    download_calls = []

    def mock_download(year, qtr, user_agent, target_path):
        download_calls.append((year, qtr))
        raise RuntimeError("Download should NOT be called because intact archive exists!")

    monkeypatch.setattr("data.sec_dataset_pipeline.download_dataset_zip_to_file", mock_download)

    dummy_tx = NormalizedBulkTransaction(
        accession_number="0000000001-06-000001",
        issuer_cik="0000320193",
        issuer_name="Apple Inc.",
        ticker="AAPL",
        reporting_owner_name="Cook Tim",
        reporting_owner_cik="0001214156",
        transaction_date="2006-01-15",
        filing_date="2006-01-16",
        transaction_code="S",
        security_title="Common Stock",
        shares=100.0,
        price_per_share=150.0,
        transaction_type="non_derivative",
        acquired_disposed="D",
        ownership_type="D",
        ownership_nature=None,
        source_url="https://sec.gov",
        is_amendment=False,
        date_of_orig_submission=None,
        raw_payload={"test": "payload"},
        source="SEC",
        record_hash="hash_acq_retry",
        form_type="4",
    )

    def mock_parse_success(*args, **kwargs):
        return [{"dummy": "record"}]

    def mock_normalize(raw):
        return dummy_tx

    class MockVal:
        is_valid = True

    monkeypatch.setattr("data.sec_dataset_pipeline.parse_dataset_zip", mock_parse_success)
    monkeypatch.setattr("data.sec_dataset_pipeline.normalize_bulk_record", mock_normalize)
    monkeypatch.setattr("data.sec_dataset_pipeline.validate_bulk_record", lambda r: MockVal())

    # Retry acquisition (force=False because period is FAILED)
    retry_code = run_historical_acquisition("2006-Q1", "2006-Q1")
    assert retry_code == 0
    assert len(download_calls) == 0  # Proves intact archive was reused without re-downloading
    assert state_mgr.get_period_status(period) == "COMPLETED"


def test_sec_store_raw_payload_false_lean_storage_propagation(tmp_path):
    db_file = tmp_path / "lean_test.db"
    db_url = f"sqlite:///{db_file}"

    tx = NormalizedBulkTransaction(
        accession_number="0000000002-06-000002",
        issuer_cik="0000320193",
        issuer_name="Apple Inc.",
        ticker="AAPL",
        reporting_owner_name="Cook Tim",
        reporting_owner_cik="0001214156",
        transaction_date="2006-01-15",
        filing_date="2006-01-16",
        transaction_code="S",
        security_title="Common Stock",
        shares=100.0,
        price_per_share=150.0,
        transaction_type="non_derivative",
        acquired_disposed="D",
        ownership_type="D",
        ownership_nature=None,
        source_url="https://sec.gov",
        is_amendment=False,
        date_of_orig_submission=None,
        raw_payload={"sample": "data"},
        source="SEC",
        record_hash="hash_lean_prop",
        form_type="4",
    )

    # Store with store_raw_payload=False
    ins, dup = store_bulk_insider_transactions(db_url, [tx], store_raw_payload=False)
    assert ins == 1

    from database.connection import connect
    with connect(db_url) as conn:
        cursor = conn.execute("SELECT raw_payload, record_hash FROM insider_transactions WHERE record_hash = 'hash_lean_prop'")
        row = cursor.fetchone()
        assert row is not None
        assert row["raw_payload"] is None  # Lean storage requirement: raw_payload NULL
        assert row["record_hash"] == "hash_lean_prop"


def test_operational_retention_calculation_and_selective_neon_insertion(tmp_path, monkeypatch):
    # Test Retention Calculation helper across boundaries relative to reference period "2026-Q2"
    ref = "2026-Q2"
    # Same quarter: diff = 0 -> inside
    assert AcquisitionStateManager.is_within_operational_retention("2026-Q2", ref, retention_years=3) is True
    # Exactly inside boundary: 11 quarters back (2023-Q3 to 2026-Q2 = 11 quarters)
    assert AcquisitionStateManager.is_within_operational_retention("2023-Q3", ref, retention_years=3) is True
    # Exactly outside boundary: 12 quarters back (2023-Q2 to 2026-Q2 = 12 quarters)
    assert AcquisitionStateManager.is_within_operational_retention("2023-Q2", ref, retention_years=3) is False
    # Far outside boundary
    assert AcquisitionStateManager.is_within_operational_retention("2006-Q1", ref, retention_years=3) is False

    # Explicit reference period override test
    ref_override = "2020-Q4"
    assert AcquisitionStateManager.is_within_operational_retention("2020-Q4", ref_override, retention_years=3) is True
    assert AcquisitionStateManager.is_within_operational_retention("2018-Q1", ref_override, retention_years=3) is True # diff 11 quarters
    assert AcquisitionStateManager.is_within_operational_retention("2017-Q4", ref_override, retention_years=3) is False # diff 12 quarters

    db_file = tmp_path / "retention_test.db"
    db_url = f"sqlite:///{db_file}"
    archive_dir = tmp_path / "archive"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "TestBot/1.0 test@example.com")
    monkeypatch.setenv("SEC_ARCHIVE_BACKEND", "filesystem")
    monkeypatch.setenv("SEC_ARCHIVE_PATH", str(archive_dir))
    monkeypatch.setenv("SEC_STORE_RAW_PAYLOAD", "false")
    monkeypatch.setenv("SEC_OPERATIONAL_RETENTION_YEARS", "3")

    archive = FilesystemSECArchive(base_path=str(archive_dir))

    # Create dummy zip files for an old period (2006-Q1) and recent period (2026-Q2)
    for p in ["2006-Q1", "2026-Q2"]:
        zfile = tmp_path / f"dummy_{p}.zip"
        with zipfile.ZipFile(zfile, "w") as zf:
            zf.writestr("SUBMISSION.tsv", f"ACCESSION_NUMBER\n0000000001-{p}\n")
        archive.put(p, str(zfile))

    dummy_tx_2006 = NormalizedBulkTransaction(
        accession_number="0000000001-2006",
        issuer_cik="0000320193",
        issuer_name="Apple Inc.",
        ticker="AAPL",
        reporting_owner_name="Cook Tim",
        reporting_owner_cik="0001214156",
        transaction_date="2006-01-15",
        filing_date="2006-01-16",
        transaction_code="S",
        security_title="Common Stock",
        shares=100.0,
        price_per_share=150.0,
        transaction_type="non_derivative",
        acquired_disposed="D",
        ownership_type="D",
        ownership_nature=None,
        source_url="https://sec.gov",
        is_amendment=False,
        date_of_orig_submission=None,
        raw_payload={"dummy": "2006"},
        source="SEC",
        record_hash="hash_2006",
        form_type="4",
    )

    def mock_parse(zip_path, source_url):
        return [{"raw": "data"}]

    def mock_norm(raw):
        return dummy_tx_2006

    class MockVal:
        is_valid = True

    monkeypatch.setattr("data.sec_dataset_pipeline.parse_dataset_zip", mock_parse)
    monkeypatch.setattr("data.sec_dataset_pipeline.normalize_bulk_record", mock_norm)
    monkeypatch.setattr("data.sec_dataset_pipeline.validate_bulk_record", lambda r: MockVal())

    # Run historical acquisition range from 2006-Q1 to 2026-Q2 with explicit reference_period="2026-Q2"
    res_code = run_historical_acquisition("2006-Q1", "2026-Q2", reference_period="2026-Q2")
    assert res_code == 0

    state_mgr = AcquisitionStateManager(db_url)
    assert state_mgr.get_period_status("2006-Q1") == "COMPLETED"
    assert state_mgr.get_period_status("2026-Q2") == "COMPLETED"

    # Verify R2 archive exists for both
    assert archive.exists("2006-Q1") is True
    assert archive.exists("2026-Q2") is True

    # Verify Neon (SQLite test DB) received records ONLY for 2026-Q2 (within 3yr window relative to 2026-Q2)
    # and 2006-Q1 records were skipped in Neon
    from database.connection import connect
    with connect(db_url) as conn:
        cursor = conn.execute("SELECT count(*) FROM insider_transactions")
        tx_count = cursor.fetchone()[0]
        # 2006-Q1 skipped insertion, 2026-Q2 inserted 1 row
        assert tx_count == 1
