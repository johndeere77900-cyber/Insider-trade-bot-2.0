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
