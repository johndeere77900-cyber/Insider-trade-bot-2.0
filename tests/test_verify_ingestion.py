from __future__ import annotations

import json
from pathlib import Path

import pytest

import main
from database.connection import connect, initialize_database
import datetime
from scripts.verify_ingestion import (
    check_temp_files_cleaned,
    get_field,
    json_safe_value,
    verify_run1,
    verify_run2,
)


def test_json_safe_value_with_dates() -> None:
    """Test that json_safe_value converts date/datetime objects to ISO format strings."""
    d = datetime.date(2006, 1, 15)
    dt = datetime.datetime(2006, 1, 15, 12, 30, 0)
    assert json_safe_value(d) == "2006-01-15"
    assert json_safe_value(dt) == "2006-01-15T12:30:00"
    assert json_safe_value("2006-01-15") == "2006-01-15"
    assert json_safe_value(123) == 123
    assert json_safe_value(None) is None


def test_verify_run1_date_json_serialization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression test: verify that date objects returned from query_one do not cause TypeError during json.dump in verify_run1."""
    import scripts.verify_ingestion as vi

    db_path = tmp_path / "test_date_serialize.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "InsiderTradeBotTest/test@example.com")

    initialize_database(db_url)

    raw_data = {
        "accession_number": "0000000000-06-000001",
        "issuer_cik": "0000001234",
        "submission": {"DOCUMENT_TYPE": "4"}
    }

    with connect(db_url) as conn:
        conn.execute(
            """
            INSERT INTO insider_transactions (
                source, accession_number, issuer_cik, filing_date, transaction_date,
                form_type, raw_payload, record_hash, created_at
            ) VALUES (
                'SEC', '0000000000-06-000001', '0000001234', '2006-01-15', '2006-01-14',
                '4', ?, 'hash1', '2026-01-01T00:00:00Z'
            )
            """,
            (json.dumps(raw_data),)
        )
        conn.execute(
            """
            INSERT INTO provenance (
                record_type, record_id, source, source_reference, retrieved_at, checksum, validation_status
            ) VALUES ('dataset_period', '2006-Q1', 'SEC', '2006q1_form345.zip', '2026-01-01', 'chk', 'validated')
            """
        )
        conn.execute(
            """
            INSERT INTO ingestion_state (
                period, status, records_parsed, records_inserted, duplicates_count, invalid_count, failures_count, completed_at
            ) VALUES ('2006-Q1', 'COMPLETED', 1, 1, 0, 0, 0, '2026-01-01')
            """
        )
        conn.commit()

    # Wrap query_one so that when date_range_sql is executed, min_d and max_d are returned as datetime.date objects (as PostgreSQL driver does)
    original_query_one = vi.query_one

    def mock_query_one(conn, db_url_arg, sql, params=()):
        res = original_query_one(conn, db_url_arg, sql, params)
        if isinstance(res, dict) and "min_d" in res and "max_d" in res:
            return {
                "min_d": datetime.date(2006, 1, 14),
                "max_d": datetime.date(2006, 3, 30),
            }
        return res

    monkeypatch.setattr(vi, "query_one", mock_query_one)

    state_file = str(tmp_path / "sec_run1_stats.json")

    # verify_run1 MUST succeed without TypeError: Object of type date is not JSON serializable
    res = verify_run1("2006-Q1", state_file)
    assert res == 0

    with open(state_file, "r") as f:
        data = json.load(f)

    assert data["earliest_date"] == "2006-01-14"
    assert data["latest_date"] == "2006-03-30"


def test_get_field_postgres_tuples_and_mappings() -> None:
    """Test get_field with dict, sqlite3.Row mock/mapping, and psycopg tuple rows."""
    cols = ["id", "source", "status", "count"]

    # 1. Dict
    row_dict = {"source": "SEC", "status": "validated"}
    assert get_field(row_dict, "source", cols) == "SEC"
    assert get_field(row_dict, "missing", cols) is None

    # 2. psycopg tuple row
    row_tuple = (101, "SEC", "validated", 234581)
    assert get_field(row_tuple, "source", cols) == "SEC"
    assert get_field(row_tuple, "count", cols) == 234581
    assert get_field(row_tuple, "nonexistent", cols) is None

    # 3. Single item count tuple
    row_count = (234581,)
    assert get_field(row_count, "c", ["c"]) == 234581


def test_query_one_and_query_all_normalization_with_psycopg_cursor_mock() -> None:
    """Regression test: verify query_one/query_all convert tuple rows into dicts using cursor.description."""
    from scripts.verify_ingestion import query_all, query_one

    class MockCursor:
        def __init__(self, description, fetchone_val=None, fetchall_val=None):
            self.description = description
            self._fetchone_val = fetchone_val
            self._fetchall_val = fetchall_val or []

        def fetchone(self):
            return self._fetchone_val

        def fetchall(self):
            return self._fetchall_val

    class MockConn:
        def __init__(self, cursor_obj):
            self._cursor = cursor_obj

        def execute(self, sql, params=()):
            return self._cursor

    # Mock psycopg cursor description for provenance query
    desc = [
        ("record_type", 1043),
        ("record_id", 1043),
        ("source", 1043),
        ("source_reference", 1043),
        ("checksum", 1043),
        ("validation_status", 1043),
    ]
    tuple_row = ("dataset_period", "2006-Q1", "SEC", "2006q1_form345.zip", "abc123chk", "validated")

    conn_one = MockConn(MockCursor(desc, fetchone_val=tuple_row))
    res_one = query_one(conn_one, "postgres://fake", "SELECT * FROM provenance")

    assert isinstance(res_one, dict)
    assert get_field(res_one, "source") == "SEC"
    assert get_field(res_one, "source_reference") == "2006q1_form345.zip"
    assert get_field(res_one, "checksum") == "abc123chk"
    assert get_field(res_one, "validation_status") == "validated"

    # Test query_all
    conn_all = MockConn(MockCursor(desc, fetchall_val=[tuple_row]))
    res_all = query_all(conn_all, "postgres://fake", "SELECT * FROM provenance")

    assert len(res_all) == 1
    assert isinstance(res_all[0], dict)
    assert get_field(res_all[0], "source") == "SEC"


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


def test_verify_run1_zero_period_records_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that zero records belonging to target period causes verify_run1 to fail, even if DB has other records."""
    db_path = tmp_path / "test_zero_period.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "InsiderTradeBotTest/test@example.com")

    initialize_database(db_url)

    # Insert an UNRELATED record outside 2006-Q1 (e.g. filing_date in 2020)
    unrelated_raw = {
        "accession_number": "0000000000-20-000001",
        "issuer_cik": "0000001234",
        "submission": {"DOCUMENT_TYPE": "4"}
    }

    with connect(db_url) as conn:
        conn.execute(
            """
            INSERT INTO insider_transactions (
                source, accession_number, issuer_cik, filing_date, transaction_date,
                form_type, raw_payload, record_hash, created_at
            ) VALUES (
                'SEC', '0000000000-20-000001', '0000001234', '2020-05-15', '2020-05-14',
                '4', ?, 'hash2020', '2026-01-01T00:00:00Z'
            )
            """,
            (json.dumps(unrelated_raw),)
        )
        conn.execute(
            """
            INSERT INTO provenance (
                record_type, record_id, source, source_reference, retrieved_at, checksum, validation_status
            ) VALUES ('dataset_period', '2006-Q1', 'SEC', '2006q1_form345.zip', '2026-01-01', 'chk', 'validated')
            """
        )
        conn.execute(
            """
            INSERT INTO ingestion_state (
                period, status, records_parsed, records_inserted, duplicates_count, invalid_count, failures_count, completed_at
            ) VALUES ('2006-Q1', 'COMPLETED', 1, 1, 0, 0, 0, '2026-01-01')
            """
        )
        conn.commit()

    state_file = str(tmp_path / "sec_run1_stats.json")

    # verify_run1 MUST fail because 2006-Q1 record count is 0
    with pytest.raises(SystemExit):
        verify_run1("2006-Q1", state_file)


def test_verify_run1_amendment_no_self_comparison(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that an isolated amendment record without a distinct original filing yields NOT TESTABLE rather than PASS."""
    db_path = tmp_path / "test_amend_self.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "InsiderTradeBotTest/test@example.com")

    initialize_database(db_url)

    # Isolated amendment record
    amend_raw = {
        "accession_number": "0000000000-06-000002",
        "issuer_cik": "0000001234",
        "all_owners": [{"RPTOWNERCIK": "0000005678", "RPTOWNERNAME": "DOE JANE"}],
        "submission": {
            "ACCESSION_NUMBER": "0000000000-06-000002",
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
                'SEC', '0000000000-06-000002', '0000001234', 'ACME CORP', 'ACME',
                'DOE JANE', '0000005678', '2006-01-15', '2006-01-16',
                '4/A', 'P', 'Common Stock', 100.0, 10.5,
                'non_derivative', 'D', 'Direct', 'https://example.com',
                ?, 'hash_amend_only', '2026-01-01T00:00:00Z'
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

    # Because no distinct original filing row exists to compare against, amendment_result MUST be NOT TESTABLE
    assert run1_saved["amendment_result"] == "NOT TESTABLE"


def test_verify_run1_and_run2_distinct_amendment_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that having both original filing and amendment stored as distinct rows results in PASS."""
    db_path = tmp_path / "test_amend_distinct.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "InsiderTradeBotTest/test@example.com")

    initialize_database(db_url)

    orig_raw = {
        "accession_number": "0000000000-06-000001",
        "issuer_cik": "0000001234",
        "all_owners": [{"RPTOWNERCIK": "0000005678", "RPTOWNERNAME": "DOE JANE"}],
        "submission": {
            "ACCESSION_NUMBER": "0000000000-06-000001",
            "DOCUMENT_TYPE": "4",
            "DATE_OF_ORIG_SUB": ""
        }
    }

    amend_raw = {
        "accession_number": "0000000000-06-000001",
        "issuer_cik": "0000001234",
        "all_owners": [{"RPTOWNERCIK": "0000005678", "RPTOWNERNAME": "DOE JANE"}],
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
                'DOE JANE', '0000005678', '2006-01-15', '2006-01-16',
                '4', 'P', 'Common Stock', 100.0, 10.5,
                'non_derivative', 'D', 'Direct', 'https://example.com',
                ?, 'hash_orig_101', '2026-01-01T00:00:00Z'
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
                'DOE JANE', '0000005678', '2006-01-15', '2006-01-16',
                '4/A', 'P', 'Common Stock', 100.0, 10.5,
                'non_derivative', 'D', 'Direct', 'https://example.com',
                ?, 'hash_amend_202', '2026-01-01T00:00:00Z'
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
            "total_tx_count": 10,
            "period_tx_count": 10,
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
                source, accession_number, issuer_cik, filing_date, raw_payload, record_hash, created_at
            ) VALUES ('SEC', 'acc1', 'cik1', '2006-01-15', '{}', 'hash1', '2026-01-01')
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


def test_verify_run1_multi_owner_pass_and_not_testable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test multi-owner PASS when multi-owner filing has top-level insider fields unset, and NOT TESTABLE when single owner only."""
    db_path = tmp_path / "test_multi_owner.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "InsiderTradeBotTest/test@example.com")

    initialize_database(db_url)

    # Multi-owner record with top-level insider fields None -> PASS
    multi_raw = {
        "accession_number": "0000000000-06-000010",
        "issuer_cik": "0000001234",
        "all_owners": [
            {"RPTOWNERCIK": "0000001111", "RPTOWNERNAME": "OWNER ONE"},
            {"RPTOWNERCIK": "0000002222", "RPTOWNERNAME": "OWNER TWO"}
        ],
        "submission": {"DOCUMENT_TYPE": "4"}
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
                'SEC', '0000000000-06-000010', '0000001234', 'ACME CORP', 'ACME',
                NULL, NULL, '2006-01-15', '2006-01-16',
                '4', 'P', 'Common Stock', 100.0, 10.5,
                'non_derivative', 'D', 'Direct', 'https://example.com',
                ?, 'hash_multi_1', '2026-01-01T00:00:00Z'
            )
            """,
            (json.dumps(multi_raw),)
        )
        conn.execute(
            """
            INSERT INTO provenance (
                record_type, record_id, source, source_reference,
                retrieved_at, checksum, validation_status
            ) VALUES (
                'dataset_period', '2006-Q1', 'SEC',
                '2006q1_form345.zip',
                '2026-01-01T00:00:00Z', 'chk123', 'validated'
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

    res = verify_run1("2006-Q1", state_file)
    assert res == 0

    with open(state_file, "r") as f:
        data = json.load(f)

    assert data["multi_owner_result"] == "PASS"


def test_verify_run1_amendment_fail_on_missing_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test amendment FAIL when amendment record hash is corrupt or unlisted."""
    db_path = tmp_path / "test_amend_fail.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "InsiderTradeBotTest/test@example.com")

    initialize_database(db_url)

    # Raw payload invalid JSON causes data quality failure -> SystemExit
    with connect(db_url) as conn:
        conn.execute(
            """
            INSERT INTO insider_transactions (
                source, accession_number, issuer_cik, filing_date, transaction_date,
                form_type, raw_payload, record_hash, created_at
            ) VALUES (
                'SEC', '0000000000-06-000099', '0000001234', '2006-01-16', '2006-01-15',
                '4/A', 'INVALID_JSON', 'hash_corrupt', '2026-01-01T00:00:00Z'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO provenance (
                record_type, record_id, source, source_reference,
                retrieved_at, checksum, validation_status
            ) VALUES ('dataset_period', '2006-Q1', 'SEC', '2006q1_form345.zip', '2026-01-01', 'chk', 'validated')
            """
        )
        conn.execute(
            """
            INSERT INTO ingestion_state (
                period, status, records_parsed, records_inserted,
                duplicates_count, invalid_count, failures_count, completed_at
            ) VALUES ('2006-Q1', 'COMPLETED', 1, 1, 0, 0, 0, '2026-01-01')
            """
        )
        conn.commit()

    state_file = str(tmp_path / "sec_run1_stats.json")

    with pytest.raises(SystemExit):
        verify_run1("2006-Q1", state_file)
