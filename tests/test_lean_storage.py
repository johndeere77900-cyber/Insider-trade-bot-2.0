"""
Deterministic tests for Lean Operational Storage Mode (SEC_STORE_RAW_PAYLOAD).
"""

from __future__ import annotations

import json
import pytest

from config.environment import load_environment
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
