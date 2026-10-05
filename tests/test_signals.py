from __future__ import annotations

import pytest

from core.models import Signal
from signals.signal_engine import SignalEngine
from signals.signal_repository import (
    count_signals,
    get_signal,
    list_signals,
    store_signal,
)


def test_signal_engine_returns_no_signal_for_insufficient_history() -> None:
    engine = SignalEngine()

    result = engine.generate_signal(
        symbol="AAPL",
        event_returns=[0.05, -0.01],
    )

    assert result is not None
    assert result.get("signal") in {
        None,
        "NO_SIGNAL",
        "INSUFFICIENT_DATA",
    }


def test_signal_engine_processes_sufficient_history() -> None:
    engine = SignalEngine()

    event_returns = [0.05] * 40

    result = engine.generate_signal(
        symbol="AAPL",
        event_returns=event_returns,
    )

    assert result is not None
    assert result.get("symbol") == "AAPL"
    assert "signal" in result
    assert "positive_rate" in result
    assert "mean_return" in result


def test_signal_repository_sqlite(tmp_path) -> None:
    db_file = tmp_path / "signals_test.db"
    db_url = f"sqlite:///{db_file}"

    sig1 = Signal(
        signal_key="SIG_AAPL_001",
        symbol="AAPL",
        signal_date="2026-01-15",
        signal_type="BULLISH",
        score=0.85,
        rationale="Cluster insider buying",
        methodology_version="2.0",
    )

    # Store first signal
    assert store_signal(db_url, sig1) is True
    assert count_signals(db_url) == 1

    # Duplicate signal is ignored (ON CONFLICT / INSERT OR IGNORE)
    assert store_signal(db_url, sig1) is False
    assert count_signals(db_url) == 1

    fetched = get_signal(db_url, "SIG_AAPL_001")
    assert fetched is not None
    assert fetched.symbol == "AAPL"
    assert fetched.score == 0.85

    sig2 = Signal(
        signal_key="SIG_MSFT_001",
        symbol="MSFT",
        signal_date="2026-01-16",
        signal_type="BEARISH",
        score=0.75,
        rationale="Insider sale",
        methodology_version="2.0",
    )
    assert store_signal(db_url, sig2) is True
    assert count_signals(db_url) == 2

    listed = list_signals(db_url, symbol="AAPL")
    assert len(listed) == 1
    assert listed[0].signal_key == "SIG_AAPL_001"


def test_signal_repository_postgresql_sql_path(monkeypatch, tmp_path) -> None:
    # Test PostgreSQL query generation path
    pg_url = "postgresql://user:pass@localhost:5432/testdb"

    from signals import signal_repository

    assert signal_repository._placeholder(pg_url) == "%s"

    sig = Signal(
        signal_key="SIG_TEST_001",
        symbol="TEST",
        signal_date="2026-01-15",
        signal_type="BULLISH",
        score=0.9,
        rationale="Test",
        methodology_version="2.0",
    )

    # Mock connect to verify PostgreSQL query formulation without actual PG server
    executed_queries = []

    class MockCursor:
        def __init__(self):
            self.rowcount = 1

        def execute(self, query, params=None):
            executed_queries.append((query, params))

        def fetchone(self):
            return ("SIG_TEST_001", "TEST", "2026-01-15", "BULLISH", 0.9, "Test", "2.0")

        def fetchall(self):
            return [("SIG_TEST_001", "TEST", "2026-01-15", "BULLISH", 0.9, "Test", "2.0")]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    class MockConnection:
        def cursor(self):
            return MockCursor()

        def execute(self, query, params=None):
            executed_queries.append((query, params))
            return MockCursor()

        def commit(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr("signals.signal_repository.connect", lambda url: MockConnection())
    monkeypatch.setattr("signals.signal_repository.initialize_database", lambda url: None)

    res = store_signal(pg_url, sig)
    assert res is True
    assert "%s" in executed_queries[0][0]
    assert "ON CONFLICT (signal_key) DO NOTHING" in executed_queries[0][0]

    fetched = get_signal(pg_url, "SIG_TEST_001")
    assert fetched is not None
    assert fetched.symbol == "TEST"

    listed = list_signals(pg_url, symbol="TEST")
    assert len(listed) == 1
    assert listed[0].symbol == "TEST"
