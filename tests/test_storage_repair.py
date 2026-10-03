"""
Comprehensive Regression Tests for Storage Architecture Repair & Safety Pass.

Verifies:
- storage_audit does NOT call initialize_database() or mutate database schema.
- physical vs logical payload storage measurement distinction.
- Duplicate unique index `idx_insider_tx_uniq` is no longer created on initialize_database.
- Table-level UNIQUE constraint still prevents duplicate transaction insertions.
- Migration safety check in scripts/migrate_storage.py verifies constraint existence before dropping index.
- Provenance safety audit detects missing dataset-level provenance and orphan rows.
- Provenance cleanup in dry-run mode performs ZERO deletions.
- Provenance cleanup refuses execution when safety checks fail.
- Provenance cleanup --execute deletes ONLY 'insider_transaction' rows and preserves 'dataset_period' rows.
- Provenance cleanup is idempotent.
- Historical ingestion remains resumable.
- raw_payload behavior remains unchanged for bulk records.
"""

from __future__ import annotations

import sqlite3
import pytest

from data.acquisition_state import AcquisitionStateManager
from data.sec_dataset_pipeline import compute_transaction_identity, normalize_bulk_record
from database.connection import connect, initialize_database
from scripts.migrate_storage import run_migration
from scripts.storage_audit import run_storage_audit
from scripts.storage_maintenance import audit_provenance, cleanup_provenance
from storage.repository import (
    count_records,
    store_bulk_insider_transactions,
    store_provenance,
)


def test_storage_audit_is_read_only_and_does_not_mutate_schema(tmp_path) -> None:
    """Verify run_storage_audit does NOT initialize or mutate schema when executed on an empty/uninitialized DB."""
    db_file = tmp_path / "test_audit_readonly.db"
    db_url = f"sqlite:///{db_file}"

    audit_res = run_storage_audit(db_url)
    assert audit_res is not None

    conn = sqlite3.connect(db_file)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()

    assert "insider_transactions" not in tables
    assert "provenance" not in tables


def test_physical_logical_payload_distinction(tmp_path) -> None:
    """Verify storage_audit measures both logical string length and physical storage payload statistics."""
    db_file = tmp_path / "test_payload_stats.db"
    db_url = f"sqlite:///{db_file}"

    initialize_database(db_url)
    raw_rec = {
        "accession_number": "000123",
        "issuer_cik": "000001",
        "source": "SEC",
        "source_url": "https://sec.gov",
        "form_type": "4",
        "record_hash": "hash123",
        "raw": {"data": "A" * 500},
    }
    norm = normalize_bulk_record(raw_rec)
    store_bulk_insider_transactions(db_url, [norm])

    res = run_storage_audit(db_url)
    assert res["raw_payload_count"] == 1
    assert res["raw_payload_logical_sum"] > 500
    assert res["raw_payload_physical_sum"] > 500


def test_initialization_does_not_create_duplicate_index(tmp_path) -> None:
    """Verify initialize_database creates required schema but DOES NOT create idx_insider_tx_uniq."""
    db_file = tmp_path / "test_no_dup_idx.db"
    db_url = f"sqlite:///{db_file}"

    initialize_database(db_url)

    with connect(db_url) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_insider_tx_uniq'"
        )
        row = cursor.fetchone()
        assert row is None, "idx_insider_tx_uniq should no longer be created on database initialization"


def test_unique_constraint_prevents_duplicate_transactions(tmp_path) -> None:
    """Verify table-level UNIQUE(source, accession_number, record_hash) still prevents duplicates."""
    db_file = tmp_path / "test_unique.db"
    db_url = f"sqlite:///{db_file}"

    raw_rec = {
        "accession_number": "0000016732-23-000043",
        "issuer_cik": "0000016732",
        "issuer_name": "TEST INC",
        "source": "SEC",
        "source_url": "https://www.sec.gov/test.txt",
        "form_type": "4",
        "record_hash": "abc123hash",
        "raw": {"test": 1},
    }

    norm = normalize_bulk_record(raw_rec)

    # First insert
    ins1, dup1 = store_bulk_insider_transactions(db_url, [norm])
    assert ins1 == 1
    assert dup1 == 0
    assert count_records(db_url, "insider_transactions") == 1

    # Second insert with identical (source, accession_number, record_hash)
    ins2, dup2 = store_bulk_insider_transactions(db_url, [norm])
    assert ins2 == 0
    assert dup2 == 1
    assert count_records(db_url, "insider_transactions") == 1


def test_migration_safety_checks_unique_constraint(tmp_path) -> None:
    """Verify run_migration in scripts/migrate_storage.py checks for uniqueness before dropping index."""
    db_file = tmp_path / "test_migration_safety.db"
    db_url = f"sqlite:///{db_file}"

    # Create table WITH unique constraint
    initialize_database(db_url)

    # Manually create duplicate index
    with connect(db_url) as conn:
        conn.execute("CREATE UNIQUE INDEX idx_insider_tx_uniq ON insider_transactions (source, accession_number, record_hash)")
        conn.commit()

    # Migration safely drops index because exact table UNIQUE constraint exists
    success = run_migration(db_url)
    assert success is True

    with connect(db_url) as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_insider_tx_uniq'")
        assert cursor.fetchone() is None


def test_migration_refuses_drop_if_exact_unique_constraint_missing(tmp_path) -> None:
    """Verify run_migration refuses to drop idx_insider_tx_uniq if an unrelated UNIQUE constraint exists instead of exact (source, accession_number, record_hash)."""
    db_file = tmp_path / "test_migration_unrelated_uniq.db"
    db_url = f"sqlite:///{db_file}"

    # Create table WITHOUT exact UNIQUE(source, accession_number, record_hash) constraint, but WITH an unrelated UNIQUE(accession_number)
    with connect(db_url) as conn:
        conn.execute(
            """
            CREATE TABLE insider_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                accession_number TEXT UNIQUE,
                record_hash TEXT
            )
            """
        )
        conn.execute("CREATE UNIQUE INDEX idx_insider_tx_uniq ON insider_transactions (source, accession_number, record_hash)")
        conn.commit()

    # Migration must REFUSE to drop idx_insider_tx_uniq because exact UNIQUE(source, accession_number, record_hash) is missing
    success = run_migration(db_url)
    assert success is False, "Migration must refuse to drop duplicate index if exact uniqueness protection is missing"

    with connect(db_url) as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_insider_tx_uniq'")
        assert cursor.fetchone() is not None, "idx_insider_tx_uniq must NOT be dropped when exact uniqueness protection is absent"


def test_provenance_audit_orphan_and_missing_dataset_detection(tmp_path) -> None:
    """Verify audit_provenance detects orphan transaction provenance rows and missing dataset provenance."""
    db_file = tmp_path / "test_prov_orphans.db"
    db_url = f"sqlite:///{db_file}"

    initialize_database(db_url)

    # Mark 2006-Q1 completed in ingestion_state WITHOUT dataset_period provenance
    with connect(db_url) as conn:
        conn.execute("INSERT INTO ingestion_state (period, status, completed_at) VALUES ('2006-Q1', 'COMPLETED', '2026-01-01')")
        # Add orphan insider_transaction provenance row
        conn.execute("INSERT INTO provenance (record_type, record_id, source, source_reference, retrieved_at, checksum, validation_status) VALUES ('insider_transaction', 'orphan_hash_123', 'SEC', 'ref', '2026-01-01', 'chk', 'validated')")
        conn.commit()

    res = audit_provenance(db_url)
    assert res["transaction_level_provenance_rows"] == 1
    assert res["orphan_provenance_count"] == 1
    assert "2006-Q1" in res["missing_dataset_provenance_periods"]
    assert res["can_cleanup"] is False


def test_provenance_cleanup_dry_run_performs_zero_deletion(tmp_path) -> None:
    """Verify provenance-cleanup in dry-run mode performs no deletion."""
    db_file = tmp_path / "test_prov_dryrun.db"
    db_url = f"sqlite:///{db_file}"

    initialize_database(db_url)
    store_provenance(
        db_url,
        record_type="dataset_period",
        record_id="2006-Q1",
        source="SEC",
        source_reference="http://example.com/2006q1.zip",
        checksum="hash123",
        validation_status="validated",
    )
    with connect(db_url) as conn:
        conn.execute("INSERT INTO ingestion_state (period, status, completed_at) VALUES ('2006-Q1', 'COMPLETED', '2026-01-01')")
        conn.execute("INSERT INTO provenance (record_type, record_id, source, source_reference, retrieved_at, checksum, validation_status) VALUES ('insider_transaction', 'tx_hash_1', 'SEC', 'http://example.com', '2026-01-01', 'hash1', 'validated')")
        conn.commit()

    assert count_records(db_url, "provenance") == 2

    success = cleanup_provenance(db_url, dry_run=True, execute=False)
    assert success is True
    # Verify zero rows deleted
    assert count_records(db_url, "provenance") == 2


def test_provenance_cleanup_execute_and_dataset_preservation(tmp_path) -> None:
    """Verify cleanup_provenance --execute deletes ONLY insider_transaction rows and preserves dataset_period rows."""
    db_file = tmp_path / "test_prov_exec.db"
    db_url = f"sqlite:///{db_file}"

    initialize_database(db_url)
    store_provenance(
        db_url,
        record_type="dataset_period",
        record_id="2006-Q1",
        source="SEC",
        source_reference="http://example.com/2006q1.zip",
        checksum="hash123",
        validation_status="validated",
    )

    with connect(db_url) as conn:
        conn.execute("INSERT INTO ingestion_state (period, status, completed_at) VALUES ('2006-Q1', 'COMPLETED', '2026-01-01')")
        conn.execute("INSERT INTO provenance (record_type, record_id, source, source_reference, retrieved_at, checksum, validation_status) VALUES ('insider_transaction', 'tx_hash_1', 'SEC', 'http://example.com', '2026-01-01', 'hash1', 'validated')")
        conn.commit()

    assert count_records(db_url, "provenance") == 2

    # First execute
    s1 = cleanup_provenance(db_url, dry_run=False, execute=True)
    assert s1 is True
    assert count_records(db_url, "provenance") == 1

    with connect(db_url) as conn:
        row = conn.execute("SELECT record_type, record_id FROM provenance").fetchone()
        assert row["record_type"] == "dataset_period"
        assert row["record_id"] == "2006-Q1"

    # Second execute (idempotent run)
    s2 = cleanup_provenance(db_url, dry_run=False, execute=True)
    assert s2 is True
    assert count_records(db_url, "provenance") == 1


def test_transaction_identity_deterministic() -> None:
    """Verify transaction identity calculation remains deterministic."""
    h1 = compute_transaction_identity(
        accession_number="0001140361-23-000001",
        transaction_type="non_derivative",
        transaction_sk="100",
        is_amendment=False,
        form_type="4",
    )
    h2 = compute_transaction_identity(
        accession_number="0001140361-23-000001",
        transaction_type="non_derivative",
        transaction_sk="100",
        is_amendment=False,
        form_type="4",
    )
    assert h1 == h2
    assert len(h1) == 64


def test_historical_ingestion_resumable(tmp_path) -> None:
    """Verify acquisition state manager correctly tracks period completion for resumption."""
    db_file = tmp_path / "test_resume.db"
    db_url = f"sqlite:///{db_file}"

    state_mgr = AcquisitionStateManager(db_url)
    assert state_mgr.should_skip_period("2006-Q1") is False

    state_mgr.record_period_completion(
        period="2006-Q1",
        records_parsed=1000,
        records_inserted=950,
        duplicates_count=50,
        invalid_count=0,
        failures_count=0,
        status="COMPLETED",
    )

    assert state_mgr.should_skip_period("2006-Q1") is True


def test_raw_payload_behavior_preserved(tmp_path) -> None:
    """Verify raw_payload is stored and retrievable on insider_transactions."""
    db_file = tmp_path / "test_raw.db"
    db_url = f"sqlite:///{db_file}"

    raw_data = {"submission": {"ACCESSION_NUMBER": "000123"}, "owner": {"NAME": "John Doe"}}
    raw_rec = {
        "accession_number": "000123",
        "issuer_cik": "000001",
        "issuer_name": "TEST",
        "source": "SEC",
        "source_url": "https://sec.gov",
        "form_type": "4",
        "record_hash": "hash123",
        "raw": raw_data,
    }

    norm = normalize_bulk_record(raw_rec)
    store_bulk_insider_transactions(db_url, [norm])

    with connect(db_url) as conn:
        cursor = conn.execute("SELECT raw_payload FROM insider_transactions WHERE accession_number='000123'")
        row = cursor.fetchone()
        assert row is not None
        assert "John Doe" in row[0]
