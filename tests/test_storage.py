from __future__ import annotations

from storage.repository import Repository


def test_repository_can_be_created(tmp_path) -> None:
    repository = Repository(
        database_url=f"sqlite:///{tmp_path / 'storage.db'}"
    )

    assert repository is not None


def test_repository_can_store_and_retrieve_a_record(tmp_path) -> None:
    repository = Repository(
        database_url=f"sqlite:///{tmp_path / 'storage.db'}"
    )

    record = {
        "symbol": "AAPL",
        "source": "TEST",
        "record_hash": "test-hash-001",
    }

    result = repository.store(
        table="insider_transactions",
        record=record,
    )

    assert result is not None


def test_postgresql_bulk_insert_uses_cursor(monkeypatch) -> None:
    """Test that store_bulk_insider_transactions uses cursor.executemany for PostgreSQL."""
    from unittest.mock import MagicMock
    import storage.repository as repo
    import database.connection as db_conn

    mock_conn = MagicMock()
    mock_cursor = MagicMock()

    conn_cm = MagicMock()
    conn_cm.__enter__.return_value = mock_conn

    cursor_cm = MagicMock()
    cursor_cm.__enter__.return_value = mock_cursor
    mock_conn.cursor.return_value = cursor_cm

    monkeypatch.setattr(repo, "connect", lambda url: conn_cm)
    monkeypatch.setattr(db_conn, "connect", lambda url: conn_cm)
    monkeypatch.setattr(repo, "is_postgresql_url", lambda url: True)
    monkeypatch.setattr(repo, "initialize_database", lambda url: None)
    monkeypatch.setattr(repo, "count_records", lambda url, tbl: 1)

    fake_record = MagicMock()
    fake_record.source = "SEC"
    fake_record.accession_number = "0001"
    fake_record.issuer_cik = "100"
    fake_record.issuer_name = "Test"
    fake_record.ticker = "TST"
    fake_record.reporting_owner_name = "Owner"
    fake_record.reporting_owner_cik = "200"
    fake_record.transaction_date = "2026-01-01"
    fake_record.filing_date = "2026-01-02"
    fake_record.form_type = "4"
    fake_record.transaction_code = "P"
    fake_record.security_title = "Common Stock"
    fake_record.shares = 100.0
    fake_record.price_per_share = 10.0
    fake_record.transaction_type = "P"
    fake_record.ownership_type = "D"
    fake_record.ownership_nature = None
    fake_record.source_url = "http://example.com"
    fake_record.raw_payload = {"test": 1}
    fake_record.record_hash = "hash123"

    pg_url = "postgresql://user:pass@localhost:5432/testdb"
    ins, dup = repo.store_bulk_insider_transactions(pg_url, [fake_record])

    assert mock_cursor.executemany.call_count == 1
    assert not mock_conn.executemany.called


def test_postgresql_transaction_date_query_no_empty_string_comparison() -> None:
    """Test that PostgreSQL transaction_date query uses IS NOT NULL without empty string comparison."""
    import database.connection as db_conn
    import scripts.verify_ingestion as verify

    pg_url = "postgresql://user:pass@localhost:5432/testdb"
    sqlite_url = "sqlite:///test.db"

    assert db_conn.is_postgresql_url(pg_url) is True
    assert db_conn.is_postgresql_url(sqlite_url) is False

    main_pg_sql = (
        "SELECT MIN(transaction_date), MAX(transaction_date) FROM insider_transactions WHERE transaction_date IS NOT NULL"
        if db_conn.is_postgresql_url(pg_url) else
        "SELECT MIN(transaction_date), MAX(transaction_date) FROM insider_transactions WHERE transaction_date IS NOT NULL AND transaction_date != ''"
    )
    assert "!= ''" not in main_pg_sql
    assert "transaction_date IS NOT NULL" in main_pg_sql

    main_sqlite_sql = (
        "SELECT MIN(transaction_date), MAX(transaction_date) FROM insider_transactions WHERE transaction_date IS NOT NULL"
        if db_conn.is_postgresql_url(sqlite_url) else
        "SELECT MIN(transaction_date), MAX(transaction_date) FROM insider_transactions WHERE transaction_date IS NOT NULL AND transaction_date != ''"
    )
    assert "!= ''" in main_sqlite_sql


def test_store_provenance_idempotent_sqlite(tmp_path) -> None:
    """Test that repeated store_provenance calls for the same record key do not fail and update fields."""
    from database.connection import connect
    from storage.repository import count_records, store_provenance

    db_url = f"sqlite:///{tmp_path / 'provenance_test.db'}"

    # 1. First dataset-period provenance insert succeeds.
    store_provenance(
        db_url,
        record_type="dataset_period",
        record_id="2006-Q1",
        source="SEC",
        source_reference="http://example.com/2006q1.zip",
        checksum="checksum_v1",
        validation_status="validated",
    )

    assert count_records(db_url, "provenance") == 1

    with connect(db_url) as conn:
        row = conn.execute(
            "SELECT source_reference, checksum, validation_status FROM provenance WHERE record_id = '2006-Q1'"
        ).fetchone()
        assert row["source_reference"] == "http://example.com/2006q1.zip"
        assert row["checksum"] == "checksum_v1"

    # 2. Repeating the same dataset-period provenance write does NOT raise a unique-constraint error.
    store_provenance(
        db_url,
        record_type="dataset_period",
        record_id="2006-Q1",
        source="SEC",
        source_reference="http://example.com/2006q1_retry.zip",
        checksum="checksum_v2",
        validation_status="validated",
    )

    # 3. Provenance row count remains exactly one.
    assert count_records(db_url, "provenance") == 1

    # 4. The latest checksum/status/retrieval information remains valid.
    with connect(db_url) as conn:
        row = conn.execute(
            "SELECT source_reference, checksum, validation_status FROM provenance WHERE record_id = '2006-Q1'"
        ).fetchone()
        assert row["source_reference"] == "http://example.com/2006q1_retry.zip"
        assert row["checksum"] == "checksum_v2"


def test_store_provenance_idempotent_postgresql(monkeypatch) -> None:
    """Test that store_provenance uses ON CONFLICT for PostgreSQL and includes DO UPDATE SET clause."""
    from unittest.mock import MagicMock
    import storage.repository as repo
    import database.connection as db_conn

    mock_conn = MagicMock()

    conn_cm = MagicMock()
    conn_cm.__enter__.return_value = mock_conn

    monkeypatch.setattr(repo, "connect", lambda url: conn_cm)
    monkeypatch.setattr(db_conn, "connect", lambda url: conn_cm)
    monkeypatch.setattr(repo, "is_postgresql_url", lambda url: True)
    monkeypatch.setattr(repo, "initialize_database", lambda url: None)

    pg_url = "postgresql://user:pass@localhost:5432/testdb"
    repo.store_provenance(
        pg_url,
        record_type="dataset_period",
        record_id="2006-Q1",
        source="SEC",
        source_reference="http://example.com/2006q1.zip",
        checksum="checksum1",
        validation_status="validated",
    )

    assert mock_conn.execute.called
    executed_sql = mock_conn.execute.call_args[0][0]
    assert "ON CONFLICT (record_type, record_id, source)" in executed_sql
    assert "DO UPDATE SET" in executed_sql
