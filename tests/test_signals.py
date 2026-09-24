from __future__ import annotations

from signals.signal_engine import SignalEngine


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
