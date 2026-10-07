"""
Focused regression tests for historical SEC acquisition safety, retry semantics, and lean storage propagation.
"""

from __future__ import annotations

import os
import zipfile
import pytest

from archive import ArchiveError, FilesystemSECArchive, S3SECArchive, get_archive_backend
from data.acquisition_state import AcquisitionStateManager, get_latest_available_sec_period, get_current_sec_period
from main import run_historical_acquisition
from storage.repository import count_records, store_bulk_insider_transactions
from data.sec_dataset_pipeline import NormalizedBulkTransaction


def test_historical_acquisition_requires_explicit_reference_period(tmp_path, monkeypatch):
    """TEST A: Verify historical acquisition raises ValueError if reference_period is None, empty, or malformed."""
    db_file = tmp_path / "req_ref_test.db"
    db_url = f"sqlite:///{db_file}"
    archive_dir = tmp_path / "archive"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "TestBot/1.0 test@example.com")
    monkeypatch.setenv("SEC_ARCHIVE_BACKEND", "filesystem")
    monkeypatch.setenv("SEC_ARCHIVE_PATH", str(archive_dir))

    with pytest.raises(ValueError, match="reference_period is required"):
        run_historical_acquisition(
            "2006-Q1",
            "2006-Q1",
            reference_period=None,
        )

    for invalid_ref in [
        "INVALID", "2026", "2026-Q", "2026-Q0", "2026-Q5", "2026-QX",
        "2026-Q11", "X2026-Q2", "2026-Q2-extra"
    ]:
        with pytest.raises(ValueError, match="Invalid reference_period"):
            run_historical_acquisition(
                "2006-Q1",
                "2006-Q1",
                reference_period=invalid_ref,
            )

    # Verify " 2026-Q2 " normalizes successfully and proceeds past validation
    def mock_download(year, qtr, user_agent, target_path):
        with zipfile.ZipFile(target_path, "w") as zf:
            zf.writestr("test.txt", "data")
        return target_path

    monkeypatch.setattr("data.sec_dataset_pipeline.download_dataset_zip_to_file", mock_download)
    monkeypatch.setattr("data.sec_dataset_pipeline.parse_dataset_zip", lambda *a, **k: [])

    ret_code = run_historical_acquisition("2006-Q1", "2006-Q1", reference_period=" 2026-Q2 ", force=True)
    assert ret_code == 0


def test_invalid_reference_period_fails_before_infrastructure(monkeypatch):
    """Verify malformed reference_period fails BEFORE load_environment or archive backend initialization."""
    called_infra = []

    def fail_env():
        called_infra.append("env")
        raise RuntimeError("load_environment should NOT be called!")

    def fail_archive(*args, **kwargs):
        called_infra.append("archive")
        raise RuntimeError("get_archive_backend should NOT be called!")

    monkeypatch.setattr("config.environment.load_environment", fail_env)
    monkeypatch.setattr("archive.get_archive_backend", fail_archive)

    with pytest.raises(ValueError, match="Invalid reference_period"):
        run_historical_acquisition("2006-Q1", "2006-Q1", reference_period="INVALID-REF")

    assert len(called_infra) == 0

    with pytest.raises(ValueError, match="reference_period is required"):
        AcquisitionStateManager.is_within_operational_retention("2006-Q1", reference_period=None)


def test_partial_database_retention_unaffected_by_neon_stored_periods():
    """TEST B: Partial database in Neon (2006-Q1, 2006-Q2) with reference_period=2026-Q2 strictly evaluates relative to 2026-Q2."""
    ref = "2026-Q2"
    assert AcquisitionStateManager.is_within_operational_retention("2006-Q1", reference_period=ref) is False
    assert AcquisitionStateManager.is_within_operational_retention("2006-Q2", reference_period=ref) is False
    assert AcquisitionStateManager.is_within_operational_retention("2025-Q1", reference_period=ref) is True


def test_fatal_archive_error_propagates_out_of_acquisition(tmp_path, monkeypatch):
    """TEST D: Fatal R2/S3 archive infrastructure error propagates out rather than marking period FAILED."""
    db_file = tmp_path / "fatal_arch_test.db"
    db_url = f"sqlite:///{db_file}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "TestBot/1.0 test@example.com")

    class FatalS3Archive(FilesystemSECArchive):
        def exists(self, period: str) -> bool:
            raise ArchiveError("403 Access Denied: S3 credentials invalid")

    fatal_backend = FatalS3Archive(base_path=str(tmp_path / "archive"))
    monkeypatch.setattr("archive.get_archive_backend", lambda *a, **k: fatal_backend)

    with pytest.raises(ArchiveError, match="403 Access Denied"):
        run_historical_acquisition("2006-Q1", "2006-Q1", reference_period="2026-Q2")


def test_historical_acquisition_uses_explicit_reference_period(tmp_path, monkeypatch):
    """TEST B: Verify historical acquisition uses normalized explicit reference_period."""
    db_file = tmp_path / "explicit_ref_test.db"
    db_url = f"sqlite:///{db_file}"
    archive_dir = tmp_path / "archive"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "TestBot/1.0 test@example.com")
    monkeypatch.setenv("SEC_ARCHIVE_BACKEND", "filesystem")
    monkeypatch.setenv("SEC_ARCHIVE_PATH", str(archive_dir))

    captured = []

    def fake_retention(period, reference_period=None, retention_years=3, **kwargs):
        captured.append(reference_period)
        return False

    monkeypatch.setattr(
        "data.acquisition_state.AcquisitionStateManager.is_within_operational_retention",
        fake_retention,
    )

    def mock_download(year, qtr, user_agent, target_path):
        with zipfile.ZipFile(target_path, "w") as zf:
            zf.writestr("test.txt", "data")
        return target_path

    monkeypatch.setattr("data.sec_dataset_pipeline.download_dataset_zip_to_file", mock_download)
    monkeypatch.setattr("data.sec_dataset_pipeline.parse_dataset_zip", lambda *a, **k: [])

    run_historical_acquisition("2006-Q1", "2006-Q2", reference_period="2026-Q2", force=True)

    assert captured
    assert all(value == "2026-Q2" for value in captured)


def test_explicit_reference_period_prevents_latest_period_lookup(tmp_path, monkeypatch):
    """TEST C: Verify passing explicit reference_period prevents get_latest_available_sec_period lookup."""
    db_file = tmp_path / "no_latest_lookup.db"
    db_url = f"sqlite:///{db_file}"
    archive_dir = tmp_path / "archive"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "TestBot/1.0 test@example.com")
    monkeypatch.setenv("SEC_ARCHIVE_BACKEND", "filesystem")
    monkeypatch.setenv("SEC_ARCHIVE_PATH", str(archive_dir))

    def fail_latest_lookup(*args, **kwargs):
        raise AssertionError("latest-period discovery must not be used when reference_period is explicit")

    monkeypatch.setattr("data.acquisition_state.get_latest_available_sec_period", fail_latest_lookup)

    def mock_download(year, qtr, user_agent, target_path):
        with zipfile.ZipFile(target_path, "w") as zf:
            zf.writestr("test.txt", "data")
        return target_path

    monkeypatch.setattr("data.sec_dataset_pipeline.download_dataset_zip_to_file", mock_download)
    monkeypatch.setattr("data.sec_dataset_pipeline.parse_dataset_zip", lambda *a, **k: [])

    res = run_historical_acquisition("2006-Q1", "2006-Q1", reference_period="2026-Q2", force=True)
    assert res == 0


def test_frozen_retention_reference_called_once(tmp_path, monkeypatch):
    """Test A: Verify retention reference is normalized once before loop and passed to is_within_operational_retention for each period."""
    db_file = tmp_path / "frozen_ref_test.db"
    db_url = f"sqlite:///{db_file}"
    archive_dir = tmp_path / "archive"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "TestBot/1.0 test@example.com")
    monkeypatch.setenv("SEC_ARCHIVE_BACKEND", "filesystem")
    monkeypatch.setenv("SEC_ARCHIVE_PATH", str(archive_dir))

    captured_refs = []

    def mock_retention(period, reference_period=None, retention_years=3, **kwargs):
        captured_refs.append(reference_period)
        return False

    monkeypatch.setattr("data.acquisition_state.AcquisitionStateManager.is_within_operational_retention", mock_retention)

    def mock_download(year, qtr, user_agent, target_path):
        with zipfile.ZipFile(target_path, "w") as zf:
            zf.writestr("test.txt", "data")
        return target_path

    monkeypatch.setattr("data.sec_dataset_pipeline.download_dataset_zip_to_file", mock_download)
    monkeypatch.setattr("data.sec_dataset_pipeline.parse_dataset_zip", lambda *a, **k: [])

    # Process 3 periods: 2006-Q1, 2006-Q2, 2006-Q3
    run_historical_acquisition("2006-Q1", "2006-Q3", reference_period="2026-Q2", force=True)

    # Retention check was called for all 3 periods with the frozen reference_period "2026-Q2"
    assert len(captured_refs) == 3
    assert all(r == "2026-Q2" for r in captured_refs)


def test_invalid_orphan_zip_deleted_and_downloaded(tmp_path, monkeypatch):
    """Test B: Verify corrupt orphan ZIP is deleted and official dataset is downloaded."""
    db_file = tmp_path / "corrupt_orphan_test.db"
    db_url = f"sqlite:///{db_file}"
    archive_dir = tmp_path / "archive"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "TestBot/1.0 test@example.com")
    monkeypatch.setenv("SEC_ARCHIVE_BACKEND", "filesystem")
    monkeypatch.setenv("SEC_ARCHIVE_PATH", str(archive_dir))

    period = "2006-Q1"
    archive = FilesystemSECArchive(base_path=str(archive_dir))

    # Create corrupt orphan ZIP (not a valid ZIP)
    zip_path = archive._zip_path(period)
    with open(zip_path, "wb") as f:
        f.write(b"CORRUPT NON ZIP CONTENT")

    assert archive.is_incomplete(period) is True

    download_calls = []

    def mock_download(year, qtr, user_agent, target_path):
        download_calls.append((year, qtr))
        # Create valid zip at target_path upon download
        with zipfile.ZipFile(target_path, "w") as zf:
            zf.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\n0000000001-06-000001\n")

    monkeypatch.setattr("data.sec_dataset_pipeline.download_dataset_zip_to_file", mock_download)
    monkeypatch.setattr("data.sec_dataset_pipeline.parse_dataset_zip", lambda *a, **k: [])

    res_code = run_historical_acquisition("2006-Q1", "2006-Q1", reference_period="2006-Q1")
    assert res_code == 0

    # Corrupt orphan ZIP deleted, SEC download performed, archive completed
    assert len(download_calls) == 1
    assert archive.exists(period) is True


def test_storage_error_not_treated_as_incomplete_no_deletion_no_download(tmp_path, monkeypatch):
    """Test C: Storage error during is_incomplete raises fatal ArchiveError without deleting or downloading."""
    db_file = tmp_path / "storage_error_test.db"
    db_url = f"sqlite:///{db_file}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "TestBot/1.0 test@example.com")

    class ErrorArchive(FilesystemSECArchive):
        def is_incomplete(self, period: str) -> bool:
            raise ArchiveError("500 Internal Error from S3 storage")

    error_archive = ErrorArchive(base_path=str(tmp_path / "archive"))
    monkeypatch.setattr("archive.get_archive_backend", lambda *a, **k: error_archive)

    download_calls = []
    monkeypatch.setattr("data.sec_dataset_pipeline.download_dataset_zip_to_file", lambda *a, **k: download_calls.append(1))

    # Acquisition run propagates fatal ArchiveError
    with pytest.raises(ArchiveError, match="500 Internal Error"):
        run_historical_acquisition("2006-Q1", "2006-Q1", reference_period="2006-Q1")
    assert len(download_calls) == 0  # Storage error must NOT trigger SEC download!


def test_s3_orphan_zip_recovery_zero_sec_downloads(tmp_path, monkeypatch):
    """Test D: S3 orphan ZIP recovery with get_incomplete_zip and 0 SEC downloads."""
    db_file = tmp_path / "s3_orphan_test.db"
    db_url = f"sqlite:///{db_file}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "TestBot/1.0 test@example.com")

    period = "2006-Q1"

    # Create dummy zip bytes
    z_file = tmp_path / "valid.zip"
    with zipfile.ZipFile(z_file, "w") as zf:
        zf.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\n0000000001-06-000001\n")
    z_bytes = z_file.read_bytes()

    store = {}
    store[f"sec-archives/{period}.zip"] = z_bytes

    class MockBody:
        def __init__(self, content: bytes):
            self._content = content
        def read(self) -> bytes:
            return self._content

    class MockS3Client:
        def head_object(self, Bucket: str, Key: str):
            if Key not in store:
                raise Exception("NotFound 404")
            return {}

        def put_object(self, Bucket: str, Key: str, Body: bytes, **kwargs):
            store[Key] = Body

        def get_object(self, Bucket: str, Key: str):
            if Key not in store:
                raise Exception("NotFound 404")
            return {"Body": MockBody(store[Key])}

    mock_client = MockS3Client()
    s3_backend = S3SECArchive(bucket="test-bucket", prefix="sec-archives", s3_client=mock_client)
    monkeypatch.setattr("archive.get_archive_backend", lambda *a, **k: s3_backend)

    assert s3_backend.is_incomplete(period) is True

    download_calls = []
    monkeypatch.setattr("data.sec_dataset_pipeline.download_dataset_zip_to_file", lambda *a, **k: download_calls.append(1))
    monkeypatch.setattr("data.sec_dataset_pipeline.parse_dataset_zip", lambda *a, **k: [])

    res_code = run_historical_acquisition("2006-Q1", "2006-Q1", reference_period="2006-Q1")
    assert res_code == 0

    assert len(download_calls) == 0  # Zero SEC downloads
    assert s3_backend.is_incomplete(period) is False
    assert s3_backend.exists(period) is True


def test_latest_available_sec_period_detection(tmp_path):
    db_file = tmp_path / "latest_period_test.db"
    db_url = f"sqlite:///{db_file}"
    archive_dir = tmp_path / "archive"
    archive = FilesystemSECArchive(base_path=str(archive_dir))

    # 1. Uninitialized state (no completed DB period, no archived period) -> raises RuntimeError
    with pytest.raises(RuntimeError, match="No authoritative SEC dataset period is available"):
        get_latest_available_sec_period(db_url, archive)

    # 2. Add completed period in DB (2025-Q3)
    state_mgr = AcquisitionStateManager(db_url)
    state_mgr.record_period_completion("2025-Q3", 100, 100, 0, 0, 0, status="COMPLETED")
    assert get_latest_available_sec_period(db_url, archive) == "2025-Q3"

    # 3. Add newer archive in R2 (2026-Q1)
    zfile = tmp_path / "2026Q1.zip"
    with zipfile.ZipFile(zfile, "w") as zf:
        zf.writestr("test.txt", "content")
    archive.put("2026-Q1", str(zfile))

    # Returns 2026-Q1 (max of DB and R2)
    assert get_latest_available_sec_period(db_url, archive) == "2026-Q1"

    # 4. Verify historical acquisition end_period="2010-Q4" evaluated relative to 2026-Q1 reference
    assert AcquisitionStateManager.is_within_operational_retention(
        "2010-Q4",
        reference_period="2026-Q1",
        retention_years=3,
    ) is False


def test_incomplete_archive_recovery_zero_sec_downloads(tmp_path, monkeypatch):
    db_file = tmp_path / "incomplete_test.db"
    db_url = f"sqlite:///{db_file}"
    archive_dir = tmp_path / "archive"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "TestBot/1.0 test@example.com")
    monkeypatch.setenv("SEC_ARCHIVE_BACKEND", "filesystem")
    monkeypatch.setenv("SEC_ARCHIVE_PATH", str(archive_dir))
    monkeypatch.setenv("SEC_STORE_RAW_PAYLOAD", "false")

    period = "2006-Q1"
    archive = FilesystemSECArchive(base_path=str(archive_dir))

    # Create orphaned ZIP file without manifest (simulating manifest upload failure)
    zip_file = archive._zip_path(period)
    with zipfile.ZipFile(zip_file, "w") as zf:
        zf.writestr(
            "SUBMISSION.tsv",
            "ACCESSION_NUMBER\tISSUER_CIK\tISSUER_NAME\tFILING_DATE\n"
            "0000000001-06-000001\t0000320193\tApple Inc.\t2006-01-15\n",
        )

    assert archive.is_incomplete(period) is True
    assert archive.exists(period) is False

    # Track SEC download calls during acquisition run
    download_calls = []

    def mock_download(year, qtr, user_agent, target_path):
        download_calls.append((year, qtr))
        raise RuntimeError("Download should NOT be called because valid incomplete ZIP exists!")

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
        record_hash="hash_incomplete_rec",
        form_type="4",
    )

    def mock_parse_success(*args, **kwargs):
        return [{"dummy": "record"}]

    class MockVal:
        is_valid = True

    monkeypatch.setattr("data.sec_dataset_pipeline.parse_dataset_zip", mock_parse_success)
    monkeypatch.setattr("data.sec_dataset_pipeline.normalize_bulk_record", lambda r: dummy_tx)
    monkeypatch.setattr("data.sec_dataset_pipeline.validate_bulk_record", lambda r: MockVal())

    # Execute acquisition: should detect incomplete ZIP, reconcile/write manifest, with ZERO SEC downloads
    res_code = run_historical_acquisition("2006-Q1", "2006-Q1", reference_period="2006-Q1")
    assert res_code == 0

    # CRITICAL ASSERTIONS:
    assert len(download_calls) == 0  # Proves zero SEC downloads performed
    assert archive.is_incomplete(period) is False  # Archive is now complete
    assert archive.exists(period) is True


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

    # 2. Simulate recoverable parsing failure on first run by raising SECDatasetError in parse_dataset_zip
    from data.sec_dataset_pipeline import SECDatasetError

    def mock_parse_fail(*args, **kwargs):
        raise SECDatasetError("Simulated period dataset parse error")

    monkeypatch.setattr("data.sec_dataset_pipeline.parse_dataset_zip", mock_parse_fail)

    state_mgr = AcquisitionStateManager(db_url)

    # Run historical acquisition (should handle recoverable error and mark FAILED)
    res_code = run_historical_acquisition("2006-Q1", "2006-Q1", reference_period="2006-Q1")
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
    retry_code = run_historical_acquisition("2006-Q1", "2006-Q1", reference_period="2006-Q1")
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
