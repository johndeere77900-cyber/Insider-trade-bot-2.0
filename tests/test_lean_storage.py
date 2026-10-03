"""
Deterministic tests for Lean Operational Storage Mode (SEC_STORE_RAW_PAYLOAD).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
import pytest

from config.environment import load_environment
from core.hashing import sha256_record
from data.acquisition_state import AcquisitionStateManager
from data.sec_dataset_pipeline import normalize_bulk_record
from database.connection import connect, initialize_database
from storage.repository import (
    count_records,
    store_bulk_insider_transactions,
    store_insider_transaction,
    store_provenance,
)


def test_environment_sec_store_raw_payload_default(monkeypatch) -> None:
    """Verify SEC_STORE_RAW_PAYLOAD defaults to False in environment configuration."""
    monkeypatch.delenv("SEC_STORE_RAW_PAYLOAD", raising=False)
    env = load_environment({
        "APP_ENVIRONMENT": "testing",
        "DATABASE_URL": "sqlite:///data/test.db",
        "SEC_USER_AGENT": "TestAgent/1.0",
    })
    assert env.sec_store_raw_payload is False


def test_environment_sec_store_raw_payload_enabled(monkeypatch) -> None:
    """Verify SEC_STORE_RAW_PAYLOAD can be enabled via environment configuration."""
    env = load_environment({
        "APP_ENVIRONMENT": "testing",
        "DATABASE_URL": "sqlite:///data/test.db",
        "SEC_USER_AGENT": "TestAgent/1.0",
        "SEC_STORE_RAW_PAYLOAD": "true",
    })
    assert env.sec_store_raw_payload is True


def test_lean_storage_mode_disabled_raw_payload(tmp_path, monkeypatch) -> None:
    """
    Test lean storage mode with SEC_STORE_RAW_PAYLOAD=false:
    - transaction inserts succeed
    - normalized fields are retained
    - record_hash is retained
    - raw_payload is NOT persisted (NULL)
    - duplicate transaction identity remains protected
    - dataset-level provenance remains supported
    - ingestion_state remains supported
    """
    monkeypatch.setenv("SEC_STORE_RAW_PAYLOAD", "false")
    db_file = tmp_path / "lean_test.db"
    db_url = f"sqlite:///{db_file}"

    initialize_database(db_url)

    raw_rec = {
        "accession_number": "0001234567-24-000001",
        "issuer_cik": "0000320193",
        "issuer_name": "APPLE INC",
        "ticker": "AAPL",
        "reporting_owner_name": "COOK TIMOTHY D",
        "reporting_owner_cik": "0001214156",
        "transaction_date": "2024-01-15",
        "filing_date": "2024-01-16",
        "form_type": "4",
        "transaction_code": "S",
        "security_title": "Common Stock",
        "shares": 10000.0,
        "price_per_share": 185.50,
        "transaction_type": "non_derivative",
        "acquired_disposed": "D",
        "direct_indirect": "D",
        "ownership_nature": "Direct",
        "source_url": "https://www.sec.gov/Archives/edgar/data/320193/000123456724000001/0001234567-24-000001.txt",
        "is_amendment": False,
        "record_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "raw": {"submission": {"ACCESSION_NUMBER": "0001234567-24-000001"}, "owner": {"NAME": "COOK TIMOTHY D"}},
    }

    norm = normalize_bulk_record(raw_rec)

    # 1. Bulk insertion succeeds
    inserted, duplicates = store_bulk_insider_transactions(db_url, [norm])
    assert inserted == 1
    assert duplicates == 0

    # 2. Query stored row to verify normalized fields, record_hash, and raw_payload IS NULL
    with connect(db_url) as conn:
        cursor = conn.execute(
            """
            SELECT accession_number, issuer_cik, ticker, insider_name,
                   transaction_date, filing_date, form_type, shares, price,
                   record_hash, raw_payload
            FROM insider_transactions
            WHERE accession_number = '0001234567-24-000001'
            """
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["accession_number"] == "0001234567-24-000001"
        assert row["issuer_cik"] == "0000320193"
        assert row["ticker"] == "AAPL"
        assert row["insider_name"] == "COOK TIMOTHY D"
        assert row["transaction_date"] == "2024-01-15"
        assert row["filing_date"] == "2024-01-16"
        assert row["form_type"] == "4"
        assert row["shares"] == 10000.0
        assert row["price"] == 185.50
        assert row["record_hash"] == norm.record_hash
        # Verify raw_payload is NULL/not persisted
        assert row["raw_payload"] is None

    # 3. Verify single-record store_insider_transaction with lean mode
    single_hash = store_insider_transaction(
        db_url,
        source="SEC",
        accession_number="0001234567-24-000002",
        issuer_cik="0000320193",
        issuer_name="APPLE INC",
        ticker="AAPL",
        insider_name="COOK TIMOTHY D",
        raw_payload={"data": "test_payload"},
    )
    assert single_hash is not None
    with connect(db_url) as conn:
        cursor = conn.execute(
            "SELECT raw_payload, record_hash FROM insider_transactions WHERE accession_number = '0001234567-24-000002'"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["raw_payload"] is None
        assert row["record_hash"] == single_hash

    # 4. Verify duplicate transaction identity protection
    ins2, dup2 = store_bulk_insider_transactions(db_url, [norm])
    assert ins2 == 0
    assert dup2 == 1
    assert count_records(db_url, "insider_transactions") == 2

    # 5. Dataset-level provenance remains supported
    store_provenance(
        db_url,
        record_type="dataset_period",
        record_id="2024-Q1",
        source="SEC",
        source_reference="https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/2024q1_form345.zip",
        checksum="abcd1234checksum",
        validation_status="validated",
    )
    with connect(db_url) as conn:
        cursor = conn.execute(
            "SELECT * FROM provenance WHERE record_type = 'dataset_period' AND record_id = '2024-Q1'"
        )
        p_row = cursor.fetchone()
        assert p_row is not None
        assert p_row["checksum"] == "abcd1234checksum"

    # 6. Ingestion state remains supported
    state_mgr = AcquisitionStateManager(db_url)
    assert state_mgr.should_skip_period("2024-Q1") is False
    state_mgr.record_period_completion(
        period="2024-Q1",
        records_parsed=100,
        records_inserted=98,
        duplicates_count=2,
        invalid_count=0,
        failures_count=0,
        status="COMPLETED",
    )
    assert state_mgr.should_skip_period("2024-Q1") is True


def test_raw_payload_enabled_mode(tmp_path, monkeypatch) -> None:
    """
    Test storage mode with SEC_STORE_RAW_PAYLOAD=true:
    - raw_payload behavior remains available and persisted as JSON string.
    """
    monkeypatch.setenv("SEC_STORE_RAW_PAYLOAD", "true")
    db_file = tmp_path / "raw_enabled_test.db"
    db_url = f"sqlite:///{db_file}"

    initialize_database(db_url)

    raw_data = {"submission": {"ACCESSION_NUMBER": "000999"}, "owner": {"NAME": "JANE DOE"}}
    raw_rec = {
        "accession_number": "000999",
        "issuer_cik": "000002",
        "issuer_name": "TEST CORP",
        "source": "SEC",
        "source_url": "https://sec.gov",
        "form_type": "4",
        "record_hash": "hash_999",
        "raw": raw_data,
    }

    norm = normalize_bulk_record(raw_rec)

    inserted, duplicates = store_bulk_insider_transactions(db_url, [norm])
    assert inserted == 1

    with connect(db_url) as conn:
        cursor = conn.execute(
            "SELECT raw_payload FROM insider_transactions WHERE accession_number = '000999'"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["raw_payload"] is not None
        parsed_payload = json.loads(row["raw_payload"])
        assert parsed_payload["owner"]["NAME"] == "JANE DOE"


@dataclass
class DummyRecord:
    source: str = "SEC"
    accession_number: str = "000000"
    issuer_cik: str = "000000"
    issuer_name: str | None = None
    ticker: str | None = None
    reporting_owner_name: str | None = None
    reporting_owner_cik: str | None = None
    transaction_date: str | None = None
    filing_date: str | None = None
    form_type: str | None = "4"
    transaction_code: str | None = None
    security_title: str | None = None
    shares: float | None = None
    price_per_share: float | None = None
    transaction_type: str | None = None
    ownership_type: str | None = None
    ownership_nature: str | None = None
    source_url: str = "https://sec.gov"
    record_hash: str | None = None
    raw_payload: dict[str, Any] | None = None


def test_missing_identity_rejection(tmp_path) -> None:
    """
    Verify that if BOTH record_hash and raw_payload are missing:
    - store_bulk_insider_transactions rejects the record with ValueError
    - it does NOT generate sha256({})
    """
    db_file = tmp_path / "missing_id_test.db"
    db_url = f"sqlite:///{db_file}"
    initialize_database(db_url)

    bad_record = DummyRecord(record_hash=None, raw_payload=None)

    with pytest.raises(ValueError, match="Transaction record identity cannot be established"):
        store_bulk_insider_transactions(db_url, [bad_record])


def test_legacy_fallback_hash_from_raw_payload(tmp_path) -> None:
    """
    Verify that if record_hash is missing BUT raw_payload exists:
    - legacy fallback behavior computes hash from raw_payload
    """
    db_file = tmp_path / "legacy_fallback_test.db"
    db_url = f"sqlite:///{db_file}"
    initialize_database(db_url)

    raw_p = {"data": "test_legacy_payload"}
    rec = DummyRecord(
        accession_number="000111",
        record_hash=None,
        raw_payload=raw_p,
    )

    expected_hash = sha256_record(raw_p)
    inserted, duplicates = store_bulk_insider_transactions(db_url, [rec])
    assert inserted == 1

    with connect(db_url) as conn:
        cursor = conn.execute(
            "SELECT record_hash FROM insider_transactions WHERE accession_number = '000111'"
        )
        row = cursor.fetchone()
        assert row is not None
        assert row["record_hash"] == expected_hash


def test_historical_acquisition_configuration_propagation(tmp_path, monkeypatch) -> None:
    """
    Verify historical acquisition path explicitly passes settings.sec_store_raw_payload
    to store_bulk_insider_transactions.
    """
    monkeypatch.setenv("SEC_STORE_RAW_PAYLOAD", "false")
    db_file = tmp_path / "config_prop_test.db"
    db_url = f"sqlite:///{db_file}"

    initialize_database(db_url)

    captured_calls = []

    def mock_store_bulk(database_url: str, records: list[Any], *, store_raw_payload: bool | None = None):
        captured_calls.append((database_url, store_raw_payload))
        return len(records), 0

    monkeypatch.setattr("storage.repository.store_bulk_insider_transactions", mock_store_bulk)

    # Patch download and state manager to avoid real network/files
    import zipfile
    def mock_download(year, qtr, user_agent, target_path, **kwargs):
        with zipfile.ZipFile(target_path, "w") as zf:
            zf.writestr("test.txt", "dummy content")
        return target_path

    monkeypatch.setattr("data.sec_dataset_pipeline.download_dataset_zip_to_file", mock_download)
    monkeypatch.setattr("storage.repository.store_provenance", lambda *a, **kw: None)

    fake_raw = {
        "accession_number": "0000000001-24-000001",
        "issuer_cik": "0000000001",
        "reporting_owner_name": "JOHN DOE",
        "reporting_owner_cik": "0000000002",
        "source": "SEC",
        "source_url": "https://sec.gov",
        "form_type": "4",
        "record_hash": "hash_proc",
        "raw": {"data": "test"},
    }

    def mock_parse(*args, **kwargs):
        yield fake_raw

    monkeypatch.setattr("data.sec_dataset_pipeline.parse_dataset_zip", mock_parse)

    # Override environment settings DATABASE_URL and archive path
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "TestAgent/1.0")
    monkeypatch.setenv("SEC_ARCHIVE_PATH", str(tmp_path / "archive"))

    import main
    main.run_historical_acquisition("2006-Q1", "2006-Q1", batch_size=5000, force=True)

    assert len(captured_calls) > 0
    for _, passed_store_raw in captured_calls:
        assert passed_store_raw is False
