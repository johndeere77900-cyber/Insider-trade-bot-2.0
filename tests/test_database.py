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
