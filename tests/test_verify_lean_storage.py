"""
Unit tests for Lean Storage Validation Script (scripts/verify_lean_storage.py).
"""

from __future__ import annotations

import json
import os
import sys
import pytest

from data.acquisition_state import AcquisitionStateManager
from database.connection import connect, initialize_database
from scripts.verify_lean_storage import (
    check_lean_env_var,
    verify_lean_run1,
    verify_lean_run2_and_summary,
)
from storage.repository import store_bulk_insider_transactions, store_provenance


@pytest.fixture
def setup_lean_db(tmp_path, monkeypatch):
    """Set up SQLite database with lean storage mode env var."""
    monkeypatch.setenv("SEC_STORE_RAW_PAYLOAD", "false")
    db_file = tmp_path / "lean_validation_test.db"
    db_url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    initialize_database(db_url)
    return db_url


class MockRecord:
    def __init__(self, acc: str, rec_hash: str):
        self.source = "SEC"
        self.accession_number = acc
        self.issuer_cik = "0000123456"
        self.issuer_name = "TEST CORP"
        self.ticker = "TST"
        self.reporting_owner_name = "DOE JOHN"
        self.reporting_owner_cik = "0000654321"
        self.transaction_date = "2006-01-15"
        self.filing_date = "2006-01-16"
        self.form_type = "4"
        self.transaction_code = "P"
        self.security_title = "Common Stock"
        self.shares = 100.0
        self.price_per_share = 10.0
        self.transaction_type = "non_derivative"
        self.ownership_type = "D"
        self.ownership_nature = "Direct"
        self.source_url = "https://sec.gov"
        self.record_hash = rec_hash
        self.raw_payload = {"data": "test"}


def test_check_lean_env_var_pass(monkeypatch):
    monkeypatch.setenv("SEC_STORE_RAW_PAYLOAD", "false")
    check_lean_env_var()  # Should not exit


def test_check_lean_env_var_fail_true(monkeypatch):
    monkeypatch.setenv("SEC_STORE_RAW_PAYLOAD", "true")
    with pytest.raises(SystemExit) as exc:
        check_lean_env_var()
    assert exc.value.code == 1


def test_check_lean_env_var_fail_missing(monkeypatch):
    monkeypatch.delenv("SEC_STORE_RAW_PAYLOAD", raising=False)
    with pytest.raises(SystemExit) as exc:
        check_lean_env_var()
    assert exc.value.code == 1


def test_verify_lean_run1_pass(setup_lean_db, tmp_path):
    db_url = setup_lean_db
    period = "2006-Q1"

    # Insert test data using store_bulk_insider_transactions in lean mode
    recs = [MockRecord("001", "hash_001"), MockRecord("002", "hash_002")]
    ins, dup = store_bulk_insider_transactions(db_url, recs, store_raw_payload=False)
    assert ins == 2

    # Store dataset provenance
    store_provenance(
        db_url,
        record_type="dataset_period",
        record_id=period,
        source="SEC",
        source_reference="http://sec.gov/2006q1.zip",
        checksum="checksum123",
        validation_status="validated",
    )

    # Record ingestion state
    state_mgr = AcquisitionStateManager(db_url)
    state_mgr.record_period_completion(
        period=period,
        records_parsed=2,
        records_inserted=2,
        duplicates_count=0,
        invalid_count=0,
        failures_count=0,
        status="COMPLETED",
    )

    state_file = str(tmp_path / "state_run1.json")
    run1_data = verify_lean_run1(period, state_file)

    assert run1_data["total_tx_count"] == 2
    assert run1_data["raw_null_count"] == 2
    assert run1_data["raw_non_null_count"] == 0
    assert run1_data["missing_record_hash_count"] == 0
    assert run1_data["tx_prov_count"] == 0
    assert run1_data["status"] == "COMPLETED"
    assert os.path.exists(state_file)


def test_verify_lean_run1_fail_raw_payload_populated(setup_lean_db, tmp_path):
    db_url = setup_lean_db
    period = "2006-Q1"

    # Manually insert row with non-null raw_payload
    with connect(db_url) as conn:
        conn.execute(
            """
            INSERT INTO insider_transactions (
                source, accession_number, issuer_cik, raw_payload, record_hash, created_at
            ) VALUES (
                'SEC', '001', '000123', '{"data": "non_null"}', 'hash_001', '2024-01-01'
            )
            """
        )
        conn.commit()

    store_provenance(db_url, "dataset_period", period, "SEC", "ref", "chk", "validated")
    state_mgr = AcquisitionStateManager(db_url)
    state_mgr.record_period_completion(period, 1, 1, 0, 0, 0, "COMPLETED")

    state_file = str(tmp_path / "state_run1.json")
    with pytest.raises(SystemExit) as exc:
        verify_lean_run1(period, state_file)
    assert exc.value.code == 1


def test_verify_lean_run1_fail_tx_provenance_exists(setup_lean_db, tmp_path):
    db_url = setup_lean_db
    period = "2006-Q1"

    recs = [MockRecord("001", "hash_001")]
    store_bulk_insider_transactions(db_url, recs, store_raw_payload=False)
    store_provenance(db_url, "dataset_period", period, "SEC", "ref", "chk", "validated")
    # Store illegal transaction-level provenance
    store_provenance(db_url, "insider_transaction", "hash_001", "SEC", "ref", "chk", "validated")

    state_mgr = AcquisitionStateManager(db_url)
    state_mgr.record_period_completion(period, 1, 1, 0, 0, 0, "COMPLETED")

    state_file = str(tmp_path / "state_run1.json")
    with pytest.raises(SystemExit) as exc:
        verify_lean_run1(period, state_file)
    assert exc.value.code == 1


def test_verify_lean_run2_pass(setup_lean_db, tmp_path, monkeypatch):
    db_url = setup_lean_db
    period = "2006-Q1"

    recs = [MockRecord("001", "hash_001"), MockRecord("002", "hash_002")]
    store_bulk_insider_transactions(db_url, recs, store_raw_payload=False)
    store_provenance(db_url, "dataset_period", period, "SEC", "ref", "chk", "validated")

    state_mgr = AcquisitionStateManager(db_url)
    state_mgr.record_period_completion(period, 2, 2, 0, 0, 0, "COMPLETED")

    state_file = str(tmp_path / "state_run1.json")
    verify_lean_run1(period, state_file)

    summary_file = tmp_path / "github_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

    verify_lean_run2_and_summary(period, state_file)

    assert summary_file.exists()
    summary_text = summary_file.read_text(encoding="utf-8")
    assert "LEAN STORAGE VALIDATION" in summary_text
    assert "FINAL RESULT:\nPASS" in summary_text
    assert "difference: 0" in summary_text


def test_verify_lean_run2_idempotency_fail(setup_lean_db, tmp_path):
    db_url = setup_lean_db
    period = "2006-Q1"

    recs = [MockRecord("001", "hash_001")]
    store_bulk_insider_transactions(db_url, recs, store_raw_payload=False)
    store_provenance(db_url, "dataset_period", period, "SEC", "ref", "chk", "validated")

    state_mgr = AcquisitionStateManager(db_url)
    state_mgr.record_period_completion(period, 1, 1, 0, 0, 0, "COMPLETED")

    state_file = str(tmp_path / "state_run1.json")
    verify_lean_run1(period, state_file)

    # Simulate second run adding new row (idempotency failure)
    recs2 = [MockRecord("002", "hash_002")]
    store_bulk_insider_transactions(db_url, recs2, store_raw_payload=False)

    with pytest.raises(SystemExit) as exc:
        verify_lean_run2_and_summary(period, state_file)
    assert exc.value.code == 1
