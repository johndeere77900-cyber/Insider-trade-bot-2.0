from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

import main
from database.connection import connect, initialize_database
from scripts.verify_ingestion import (
    check_temp_files_cleaned,
    verify_run1,
    verify_run2,
)


def test_check_temp_files_cleaned() -> None:
    assert check_temp_files_cleaned("2006-Q1") is True


def test_verify_run1_and_run2_integration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "test_verify.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "InsiderTradeBotTest/test@example.com")

    initialize_database(db_url)

    # Insert sample insider transaction
    sample_raw = {
        "accession_number": "0000000000-06-000001",
        "issuer_cik": "0000001234",
        "all_owners": [
            {"RPTOWNERCIK": "0000005678", "RPTOWNERNAME": "DOE JANE"}
        ],
        "submission": {
            "DOCUMENT_TYPE": "4",
            "DATE_OF_ORIG_SUB": ""
        }
    }

    with connect(db_url) as conn:
        conn.execute(
            """
            INSERT INTO insider_transactions (
                source, accession_number, issuer_cik, issuer_name, ticker,
                insider_name, insider_cik, transaction_date, filing_date,
                form_type, transaction_code, security_title, shares, price,
                transaction_type, ownership_type, ownership_nature, source_url,
                raw_payload, record_hash, created_at
            ) VALUES (
                'SEC', '0000000000-06-000001', '0000001234', 'ACME CORP', 'ACME',
                'DOE JANE', '0000005678', '2006-01-15', '2006-01-16',
                '4', 'P', 'Common Stock', 100.0, 10.5,
                'non_derivative', 'D', 'Direct', 'https://example.com',
                ?, 'hash12345', '2026-01-01T00:00:00Z'
            )
            """,
            (json.dumps(sample_raw),)
        )

        conn.execute(
            """
            INSERT INTO provenance (
                record_type, record_id, source, source_reference,
                retrieved_at, checksum, validation_status
            ) VALUES (
                'dataset_period', '2006-Q1', 'SEC',
                'https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/2006q1_form345.zip',
                '2026-01-01T00:00:00Z', 'abc123checksum', 'validated'
            )
            """
        )

        conn.execute(
            """
            INSERT INTO ingestion_state (
                period, status, records_parsed, records_inserted,
                duplicates_count, invalid_count, failures_count, completed_at
            ) VALUES (
                '2006-Q1', 'COMPLETED', 10, 10, 0, 0, 0, '2026-01-01T00:00:00Z'
            )
            """
        )
        conn.commit()

    state_file = str(tmp_path / "sec_run1_stats.json")

    # Run 1 verification
    res1 = verify_run1("2006-Q1", state_file)
    assert res1 == 0
    assert Path(state_file).exists()

    # Run 2 verification
    res2 = verify_run2("2006-Q1", state_file)
    assert res2 == 0
