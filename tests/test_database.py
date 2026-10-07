from __future__ import annotations

import sqlite3

from database.connection import DatabaseConnection


def test_database_connection_can_be_created(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    connection = DatabaseConnection(
        f"sqlite:///{database_path}"
    )

    assert connection is not None


def test_database_connection_can_connect(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    database = DatabaseConnection(
        f"sqlite:///{database_path}"
    )

    connection = database.connect()

    try:
        assert isinstance(connection, sqlite3.Connection)
    finally:
        connection.close()


def test_database_connection_creates_database_file(tmp_path) -> None:
    database_path = tmp_path / "test.db"

    database = DatabaseConnection(
        f"sqlite:///{database_path}"
    )

    connection = database.connect()
    connection.close()

    assert database_path.exists()


def test_postgres_connection_resolves_ipv4(monkeypatch) -> None:
    import socket
    import sys
    from unittest.mock import MagicMock
    from database.connection import connect

    called_kwargs = {}

    mock_psycopg = MagicMock()

    def mock_connect(**kwargs):
        nonlocal called_kwargs
        called_kwargs = kwargs
        return MagicMock()

    mock_psycopg.connect = mock_connect

    def mock_conninfo_to_dict(url):
        return {
            "user": "user",
            "password": "pass",
            "dbname": "neondb",
            "host": "ep-foo-bar.us-east-2.aws.neon.tech",
            "port": "5432",
            "sslmode": "require",
        }

    mock_psycopg.conninfo.conninfo_to_dict = mock_conninfo_to_dict

    def mock_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        if family == socket.AF_INET and host == "ep-foo-bar.us-east-2.aws.neon.tech":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 0))]
        return []

    monkeypatch.setitem(sys.modules, "psycopg", mock_psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.conninfo", mock_psycopg.conninfo)
    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    db_url = "postgresql://user:pass@ep-foo-bar.us-east-2.aws.neon.tech:5432/neondb?sslmode=require"
    connect(db_url)

    assert called_kwargs.get("host") == "ep-foo-bar.us-east-2.aws.neon.tech"
    assert called_kwargs.get("hostaddr") == "192.0.2.1"
    assert called_kwargs.get("sslmode") == "require"
    assert called_kwargs.get("user") == "user"
    assert called_kwargs.get("password") == "pass"
    assert called_kwargs.get("dbname") == "neondb"


def test_postgres_connection_raises_error_on_ipv4_resolution_failure(monkeypatch) -> None:
    import socket
    import sys
    import pytest
    from unittest.mock import MagicMock
    from database.connection import connect

    mock_psycopg = MagicMock()

    def mock_conninfo_to_dict(url):
        return {
            "user": "user",
            "password": "pass",
            "dbname": "neondb",
            "host": "ep-foo-bar.us-east-2.aws.neon.tech",
            "port": "5432",
            "sslmode": "require",
        }

    mock_psycopg.conninfo.conninfo_to_dict = mock_conninfo_to_dict

    original_exc = socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    def mock_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        raise original_exc

    monkeypatch.setitem(sys.modules, "psycopg", mock_psycopg)
    monkeypatch.setitem(sys.modules, "psycopg.conninfo", mock_psycopg.conninfo)
    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)

    db_url = "postgresql://user:pass@ep-foo-bar.us-east-2.aws.neon.tech:5432/neondb?sslmode=require"

    with pytest.raises(RuntimeError) as exc_info:
        connect(db_url)

    assert "Could not resolve an IPv4 address for PostgreSQL host: ep-foo-bar.us-east-2.aws.neon.tech" in str(exc_info.value)
    assert exc_info.value.__cause__ is original_exc


def get_postgres_unique_constraints(pg_url: str, table_name: str = "corporate_actions") -> dict[str, set[str]]:
    with connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.conname AS constraint_name,
                    ARRAY_AGG(a.attname::text) AS columns
                FROM pg_constraint c
                JOIN pg_class t ON c.conrelid = t.oid
                JOIN pg_namespace n ON t.relnamespace = n.oid
                JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(c.conkey)
                WHERE n.nspname = 'public'
                  AND t.relname = %s
                  AND c.contype = 'u'
                GROUP BY c.conname;
                """,
                (table_name,)
            )
            return {row[0]: set(row[1]) for row in cur.fetchall()}


def get_postgres_indexes(pg_url: str, table_name: str = "corporate_actions") -> set[str]:
    with connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = 'public' AND tablename = %s;
                """,
                (table_name,)
            )
            return {row[0] for row in cur.fetchall()}


def test_postgres_migration_test_a_unrelated_unique_survives() -> None:
    """
    Test A — An unrelated UNIQUE constraint survives the migration.
    """
    import os
    import pytest
    from database.connection import connect, initialize_database, is_postgresql_url

    pg_url = os.getenv("POSTGRES_TEST_URL") or os.getenv("DATABASE_URL", "")
    if not is_postgresql_url(pg_url):
        pytest.skip("PostgreSQL test database not available for migration testing.")

    with connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS corporate_actions CASCADE;")
            cur.execute(
                """
                CREATE TABLE corporate_actions (
                    id BIGSERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_date TEXT NOT NULL,
                    ratio TEXT,
                    cash_amount DOUBLE PRECISION,
                    source TEXT NOT NULL,
                    raw_payload TEXT,
                    record_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    CONSTRAINT legacy_ca_identity UNIQUE (symbol, action_type, action_date, source),
                    CONSTRAINT unrelated_unq_constraint UNIQUE (created_at)
                );
                """
            )
        conn.commit()

    initialize_database(pg_url)

    constraints = get_postgres_unique_constraints(pg_url, "corporate_actions")
    assert "corporate_actions_identity_key" in constraints
    assert constraints["corporate_actions_identity_key"] == {"symbol", "action_type", "action_date", "source"}
    assert "unrelated_unq_constraint" in constraints
    assert constraints["unrelated_unq_constraint"] == {"created_at"}


def test_postgres_migration_test_b_legacy_identity_constraint_renamed() -> None:
    """
    Test B — A legacy UNIQUE constraint on (symbol, action_type, action_date, source) is renamed to corporate_actions_identity_key.
    """
    import os
    import pytest
    from database.connection import connect, initialize_database, is_postgresql_url

    pg_url = os.getenv("POSTGRES_TEST_URL") or os.getenv("DATABASE_URL", "")
    if not is_postgresql_url(pg_url):
        pytest.skip("PostgreSQL test database not available for migration testing.")

    with connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS corporate_actions CASCADE;")
            cur.execute(
                """
                CREATE TABLE corporate_actions (
                    id BIGSERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_date TEXT NOT NULL,
                    ratio TEXT,
                    cash_amount DOUBLE PRECISION,
                    source TEXT NOT NULL,
                    raw_payload TEXT,
                    record_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    CONSTRAINT old_legacy_identity_name UNIQUE (symbol, action_type, action_date, source)
                );
                """
            )
        conn.commit()

    initialize_database(pg_url)

    constraints = get_postgres_unique_constraints(pg_url, "corporate_actions")
    assert "corporate_actions_identity_key" in constraints
    assert constraints["corporate_actions_identity_key"] == {"symbol", "action_type", "action_date", "source"}
    assert "old_legacy_identity_name" not in constraints


def test_postgres_migration_test_c_legacy_identity_index_migrated() -> None:
    """
    Test C — A legacy unique identity index is migrated without removing unrelated UNIQUE constraints.
    """
    import os
    import pytest
    from database.connection import connect, initialize_database, is_postgresql_url

    pg_url = os.getenv("POSTGRES_TEST_URL") or os.getenv("DATABASE_URL", "")
    if not is_postgresql_url(pg_url):
        pytest.skip("PostgreSQL test database not available for migration testing.")

    with connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS corporate_actions CASCADE;")
            cur.execute(
                """
                CREATE TABLE corporate_actions (
                    id BIGSERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_date TEXT NOT NULL,
                    ratio TEXT,
                    cash_amount DOUBLE PRECISION,
                    source TEXT NOT NULL,
                    raw_payload TEXT,
                    record_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    CONSTRAINT unrelated_unq_constraint UNIQUE (created_at)
                );
                CREATE UNIQUE INDEX idx_corp_actions_identity ON corporate_actions (symbol, action_type, action_date, source);
                """
            )
        conn.commit()

    initialize_database(pg_url)

    constraints = get_postgres_unique_constraints(pg_url, "corporate_actions")
    indexes = get_postgres_indexes(pg_url, "corporate_actions")

    assert "corporate_actions_identity_key" in constraints
    assert constraints["corporate_actions_identity_key"] == {"symbol", "action_type", "action_date", "source"}
    assert "unrelated_unq_constraint" in constraints
    assert "idx_corp_actions_identity" not in indexes


def test_postgres_migration_test_d_idempotency() -> None:
    """
    Test D — Running the migration twice is successful and leaves the same canonical constraint.
    """
    import os
    import pytest
    from database.connection import connect, initialize_database, is_postgresql_url

    pg_url = os.getenv("POSTGRES_TEST_URL") or os.getenv("DATABASE_URL", "")
    if not is_postgresql_url(pg_url):
        pytest.skip("PostgreSQL test database not available for migration testing.")

    initialize_database(pg_url)
    constraints_1 = get_postgres_unique_constraints(pg_url, "corporate_actions")

    initialize_database(pg_url)
    constraints_2 = get_postgres_unique_constraints(pg_url, "corporate_actions")

    assert constraints_1 == constraints_2
    assert "corporate_actions_identity_key" in constraints_2


def test_postgres_migration_test_e_enforces_uniqueness() -> None:
    """
    Test E — The final canonical identity still enforces uniqueness for (symbol, action_type, action_date, source).
    """
    import os
    import pytest
    from database.connection import connect, initialize_database, is_postgresql_url

    pg_url = os.getenv("POSTGRES_TEST_URL") or os.getenv("DATABASE_URL", "")
    if not is_postgresql_url(pg_url):
        pytest.skip("PostgreSQL test database not available for migration testing.")

    initialize_database(pg_url)

    with connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM corporate_actions WHERE symbol = 'TESTMIG';")
            cur.execute(
                """
                INSERT INTO corporate_actions (symbol, action_type, action_date, ratio, cash_amount, source, record_hash, created_at)
                VALUES ('TESTMIG', 'split', '2024-01-01', '2:1', NULL, 'fmp', 'hash1', 'now');
                """
            )
        conn.commit()

        import psycopg.errors
        with pytest.raises(psycopg.errors.UniqueViolation) as exc_info:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO corporate_actions (symbol, action_type, action_date, ratio, cash_amount, source, record_hash, created_at)
                    VALUES ('TESTMIG', 'split', '2024-01-01', '3:1', NULL, 'fmp', 'hash2', 'now');
                    """
                )

        assert exc_info.value.diag.constraint_name == "corporate_actions_identity_key"
        assert exc_info.value.diag.table_name == "corporate_actions"


def test_postgres_migration_partial_unique_index_survives() -> None:
    """
    Regression test: A partial unique index on (symbol, action_type, action_date, source)
    with a WHERE clause MUST NOT be deleted by migration.
    """
    import os
    import pytest
    from database.connection import connect, initialize_database, is_postgresql_url

    pg_url = os.getenv("POSTGRES_TEST_URL") or os.getenv("DATABASE_URL", "")
    if not is_postgresql_url(pg_url):
        pytest.skip("PostgreSQL test database not available for migration testing.")

    with connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS corporate_actions CASCADE;")
            cur.execute(
                """
                CREATE TABLE corporate_actions (
                    id BIGSERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_date TEXT NOT NULL,
                    ratio TEXT,
                    cash_amount DOUBLE PRECISION,
                    source TEXT NOT NULL,
                    raw_payload TEXT,
                    record_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX partial_ca_idx
                ON corporate_actions (symbol, action_type, action_date, source)
                WHERE cash_amount IS NOT NULL;
                """
            )
        conn.commit()

    initialize_database(pg_url)

    indexes = get_postgres_indexes(pg_url, "corporate_actions")
    constraints = get_postgres_unique_constraints(pg_url, "corporate_actions")

    assert "partial_ca_idx" in indexes
    assert "corporate_actions_identity_key" in constraints


def test_postgres_migration_included_columns_unique_index_survives() -> None:
    """
    Regression test: A unique index with key columns plus included non-key columns
    MUST NOT be classified as the legacy identity index and MUST survive.
    """
    import os
    import pytest
    from database.connection import connect, initialize_database, is_postgresql_url

    pg_url = os.getenv("POSTGRES_TEST_URL") or os.getenv("DATABASE_URL", "")
    if not is_postgresql_url(pg_url):
        pytest.skip("PostgreSQL test database not available for migration testing.")

    with connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS corporate_actions CASCADE;")
            cur.execute(
                """
                CREATE TABLE corporate_actions (
                    id BIGSERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    action_type TEXT NOT NULL,
                    action_date TEXT NOT NULL,
                    ratio TEXT,
                    cash_amount DOUBLE PRECISION,
                    source TEXT NOT NULL,
                    raw_payload TEXT,
                    record_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX extended_ca_idx
                ON corporate_actions (symbol, action_type, action_date, source)
                INCLUDE (cash_amount);
                """
            )
        conn.commit()

    initialize_database(pg_url)

    indexes = get_postgres_indexes(pg_url, "corporate_actions")
    constraints = get_postgres_unique_constraints(pg_url, "corporate_actions")

    assert "extended_ca_idx" in indexes
    assert "corporate_actions_identity_key" in constraints
