from __future__ import annotations

from unittest.mock import MagicMock, patch

from data.corporate_actions_client import CorporateActionsClient
from data.corporate_actions_loader import CorporateActionsLoader
from database.connection import initialize_database


def test_corporate_actions_client_can_be_created() -> None:
    client = CorporateActionsClient()

    assert client is not None


def test_corporate_actions_client_accepts_configuration() -> None:
    client = CorporateActionsClient(
        api_key="test-key",
        base_url="https://example.test",
    )

    assert client is not None


def test_corporate_actions_loader_can_be_created() -> None:
    loader = CorporateActionsLoader()

    assert loader is not None


def test_corporate_actions_loader_accepts_client() -> None:
    client = CorporateActionsClient(
        api_key="test-key",
        base_url="https://example.test",
    )

    loader = CorporateActionsLoader(client=client)

    assert loader is not None


def test_postgres_migration_logic_preserves_unrelated_constraints() -> None:
    """
    Unit test verifying that when initializing database on PostgreSQL,
    unrelated UNIQUE constraints returned from pg_constraint catalog query are NOT dropped.
    """
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

    mock_cursor.fetchall.side_effect = [
        [("unrelated_idx_key", ["created_at"])],  # pg_constraint query for corporate_actions
        [],  # pg_index query for corporate_actions
    ]

    with patch("database.connection.connect", return_value=mock_conn):
        with patch("database.connection.is_postgresql_url", return_value=True):
            initialize_database("postgresql://user:pass@localhost:5432/testdb")

    executed_sql = [call[0][0] for call in mock_cursor.execute.call_args_list if call[0]]

    for sql in executed_sql:
        if isinstance(sql, str):
            assert "unrelated_idx_key" not in sql
            assert "DROP CONSTRAINT" not in sql

    assert any(isinstance(sql, str) and "ADD CONSTRAINT corporate_actions_identity_key" in sql for sql in executed_sql)
