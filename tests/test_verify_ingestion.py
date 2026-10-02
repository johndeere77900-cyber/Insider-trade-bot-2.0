from __future__ import annotations

import json
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


def test_main_historical_force_reprocessing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "test_force.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "InsiderTradeBotTest/test@example.com")

    initialize_database(db_url)

    from data.acquisition_state import AcquisitionStateManager
    state_mgr = AcquisitionStateManager(db_url)
    state_mgr.record_period_completion(
        period="2006-Q1",
        records_parsed=100,
        records_inserted=100,
        duplicates_count=0,
        invalid_count=0,
        failures_count=0,
        status="COMPLETED",
    )

    assert state_mgr.should_skip_period("2006-Q1") is True

    import data.sec_dataset_pipeline as pipeline
    monkeypatch.setattr(pipeline, "download_dataset_zip_to_file", lambda y, q, user_agent, target_path: target_path)
    monkeypatch.setattr(pipeline, "parse_dataset_zip", lambda zip_path, source_url="": [])

    ret = main.run_historical_acquisition("2006-Q1", "2006-Q1", force=True)
    assert ret == 0


def test_verify_run1_and_run2_full_cycle_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "test_verify_pass.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "InsiderTradeBotTest/test@example.com")

    initialize_database(db_url)

    # Original filing
    orig_raw = {
        "accession_number": "0000000000-06-000001",
        "issuer_cik": "0000001234",
        "all_owners": [
            {"RPTOWNERCIK": "0000005678", "RPTOWNERNAME": "DOE JANE"},
            {"RPTOWNERCIK": "0000009999", "RPTOWNERNAME": "DOE JOHN"}
        ],
        "submission": {
            "ACCESSION_NUMBER": "0000000000-06-000001",
            "DOCUMENT_TYPE": "4",
            "DATE_OF_ORIG_SUB": ""
        }
    }

    # Amendment record targeting original accession
    amend_raw = {
        "accession_number": "0000000000-06-000001",
        "issuer_cik": "0000001234",
        "all_owners": [
            {"RPTOWNERCIK": "0000005678", "RPTOWNERNAME": "DOE JANE"},
            {"RPTOWNERCIK": "0000009999", "RPTOWNERNAME": "DOE JOHN"}
        ],
        "submission": {
            "ACCESSION_NUMBER": "0000000000-06-000001",
            "DOCUMENT_TYPE": "4/A",
            "DATE_OF_ORIG_SUB": "2006-01-10"
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
                NULL, NULL, '2006-01-15', '2006-01-16',
                '4', 'P', 'Common Stock', 100.0, 10.5,
                'non_derivative', 'D', 'Direct', 'https://example.com',
                ?, 'hash_orig_123', '2026-01-01T00:00:00Z'
            )
            """,
            (json.dumps(orig_raw),)
        )

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
                NULL, NULL, '2006-01-15', '2006-01-16',
                '4/A', 'P', 'Common Stock', 100.0, 10.5,
                'non_derivative', 'D', 'Direct', 'https://example.com',
                ?, 'hash_amend_456', '2026-01-01T00:00:00Z'
            )
            """,
            (json.dumps(amend_raw),)
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
                '2006-Q1', 'COMPLETED', 2, 2, 0, 0, 0, '2026-01-01T00:00:00Z'
            )
            """
        )
        conn.commit()

    state_file = str(tmp_path / "sec_run1_stats.json")

    res1 = verify_run1("2006-Q1", state_file)
    assert res1 == 0

    with open(state_file, "r") as f:
        run1_saved = json.load(f)
    assert run1_saved["multi_owner_result"] == "PASS"
    assert run1_saved["amendment_result"] == "PASS"

    with connect(db_url) as conn:
        conn.execute(
            """
            UPDATE ingestion_state
            SET records_parsed = 2, records_inserted = 0, duplicates_count = 2, status = 'COMPLETED'
            WHERE period = '2006-Q1'
            """
        )
        conn.commit()

    res2 = verify_run2("2006-Q1", state_file)
    assert res2 == 0


def test_verify_run1_and_run2_not_testable_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    db_path = tmp_path / "test_not_testable.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "InsiderTradeBotTest/test@example.com")

    initialize_database(db_url)

    # Standard record (not multi-owner, not amendment)
    single_raw = {
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
                ?, 'hash123', '2026-01-01T00:00:00Z'
            )
            """,
            (json.dumps(single_raw),)
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
                '2006-Q1', 'COMPLETED', 1, 1, 0, 0, 0, '2026-01-01T00:00:00Z'
            )
            """
        )
        conn.commit()

    state_file = str(tmp_path / "sec_run1_stats.json")

    res1 = verify_run1("2006-Q1", state_file)
    assert res1 == 0

    with open(state_file, "r") as f:
        run1_saved = json.load(f)
    assert run1_saved["multi_owner_result"] == "NOT TESTABLE"
    assert run1_saved["amendment_result"] == "NOT TESTABLE"

    with connect(db_url) as conn:
        conn.execute(
            """
            UPDATE ingestion_state
            SET records_parsed = 1, records_inserted = 0, duplicates_count = 1, status = 'COMPLETED'
            WHERE period = '2006-Q1'
            """
        )
        conn.commit()

    res2 = verify_run2("2006-Q1", state_file)
    assert res2 == 0

    captured = capsys.readouterr().out
    assert "DATA QUALITY:\nPARTIAL / NOT TESTABLE" in captured
    assert "MULTI-OWNER TEST:\nNOT TESTABLE" in captured
    assert "AMENDMENT TEST:\nNOT TESTABLE" in captured


def test_verify_run1_multi_owner_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "test_multi_fail.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "InsiderTradeBotTest/test@example.com")

    initialize_database(db_url)

    bad_multi_raw = {
        "accession_number": "0000000000-06-000001",
        "issuer_cik": "0000001234",
        "all_owners": [
            {"RPTOWNERCIK": "0000005678", "RPTOWNERNAME": "DOE JANE"},
            {"RPTOWNERCIK": "0000009999", "RPTOWNERNAME": "DOE JOHN"}
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
                ?, 'hash123', '2026-01-01T00:00:00Z'
            )
            """,
            (json.dumps(bad_multi_raw),)
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
                '2006-Q1', 'COMPLETED', 1, 1, 0, 0, 0, '2026-01-01T00:00:00Z'
            )
            """
        )
        conn.commit()

    state_file = str(tmp_path / "sec_run1_stats.json")

    with pytest.raises(SystemExit):
        verify_run1("2006-Q1", state_file)


def test_verify_run2_no_duplicates_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "test_no_dup_fail.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "InsiderTradeBotTest/test@example.com")

    initialize_database(db_url)

    state_file = str(tmp_path / "sec_run1_stats.json")
    with open(state_file, "w") as f:
        json.dump({
            "period": "2006-Q1",
            "records_parsed": 10,
            "records_inserted": 10,
            "duplicates_count": 0,
            "invalid_count": 0,
            "failures_count": 0,
            "tx_count": 10,
            "provenance_count": 1,
            "status": "COMPLETED",
            "earliest_date": "2006-01-01",
            "latest_date": "2006-03-31",
            "multi_owner_result": "PASS",
            "amendment_result": "PASS",
        }, f)

    with connect(db_url) as conn:
        conn.execute(
            """
            INSERT INTO insider_transactions (
                source, accession_number, issuer_cik, raw_payload, record_hash, created_at
            ) VALUES ('SEC', 'acc1', 'cik1', '{}', 'hash1', '2026-01-01')
            """
        )
        conn.execute(
            """
            INSERT INTO provenance (
                record_type, record_id, source, source_reference, retrieved_at, validation_status
            ) VALUES ('dataset_period', '2006-Q1', 'SEC', 'ref', '2026-01-01', 'validated')
            """
        )
        conn.execute(
            """
            INSERT INTO ingestion_state (
                period, status, records_parsed, records_inserted,
                duplicates_count, invalid_count, failures_count, completed_at
            ) VALUES (
                '2006-Q1', 'COMPLETED', 10, 0, 0, 0, 0, '2026-01-01T00:00:00Z'
            )
            """
        )
        conn.commit()

    with pytest.raises(SystemExit):
        verify_run2("2006-Q1", state_file)
