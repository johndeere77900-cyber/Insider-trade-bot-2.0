"""
Unit tests for research/research_data_access.py and verify_dataset_coverage.
"""

from __future__ import annotations

import pytest

from database.connection import connect, initialize_database
from research.research_data_access import (
    DatasetIntegrityError,
    PeriodNotFoundError,
    get_historical_transactions,
    verify_dataset_coverage,
)


def test_verify_dataset_coverage_complete(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/verify_coverage_test.db"
    initialize_database(db_url)

    with connect(db_url) as conn:
        conn.execute(
            "INSERT INTO ingestion_state (period, status, records_inserted, completed_at) VALUES (?, ?, ?, ?)",
            ("2024-Q1", "COMPLETED", 2, "2024-04-01T00:00:00Z"),
        )
        conn.execute(
            """
            INSERT INTO insider_transactions
            (source, accession_number, issuer_cik, filing_date, transaction_date, record_hash, created_at)
            VALUES
            ('sec', 'acc1', 'cik1', '2024-01-15', '2024-01-10', 'hash1', 'now'),
            ('sec', 'acc2', 'cik2', '2024-03-20', '2024-03-18', 'hash2', 'now')
            """
        )
        conn.commit()

    cov = verify_dataset_coverage(
        database_url=db_url,
        dataset_type="sec",
        period="2024-Q1",
    )

    assert cov.dataset_type == "sec"
    assert cov.period == "2024-Q1"
    assert cov.expected_records == 2
    assert cov.actual_records == 2
    assert cov.first_date == "2024-01-15"
    assert cov.last_date == "2024-03-20"
    assert cov.complete is True


def test_verify_dataset_coverage_missing_rows_raises_integrity_error(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/verify_coverage_missing_test.db"
    initialize_database(db_url)

    with connect(db_url) as conn:
        conn.execute(
            "INSERT INTO ingestion_state (period, status, records_inserted, completed_at) VALUES (?, ?, ?, ?)",
            ("2024-Q1", "COMPLETED", 100, "2024-04-01T00:00:00Z"),
        )
        conn.commit()

    with pytest.raises(DatasetIntegrityError, match="Dataset coverage verification failed"):
        verify_dataset_coverage(
            database_url=db_url,
            dataset_type="sec",
            period="2024-Q1",
        )


def test_verify_dataset_coverage_not_completed_status_raises_integrity_error(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/verify_coverage_incomplete_status.db"
    initialize_database(db_url)

    with connect(db_url) as conn:
        conn.execute(
            "INSERT INTO ingestion_state (period, status, records_inserted, completed_at) VALUES (?, ?, ?, ?)",
            ("2024-Q1", "FAILED", 0, "2024-04-01T00:00:00Z"),
        )
        conn.commit()

    with pytest.raises(DatasetIntegrityError, match="status='FAILED'"):
        verify_dataset_coverage(
            database_url=db_url,
            dataset_type="sec",
            period="2024-Q1",
        )


def test_older_period_falling_back_to_archive(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/older_period_test.db"
    initialize_database(db_url)

    class MockArchiveBackend:
        def exists(self, period: str) -> bool:
            return period == "2010-Q1"

        def get(self, period: str) -> bytes:
            return b"zip_bytes"

    # Period outside Neon operational retention window (or missing in Neon)
    # gets resolved to R2 and fetched from archive.
    with pytest.raises(PeriodNotFoundError, match="2005-Q1"):
        get_historical_transactions(
            database_url=db_url,
            archive_backend=MockArchiveBackend(),
            start_period="2005-Q1",
            end_period="2005-Q1",
            reference_period="2024-Q1",
        )
