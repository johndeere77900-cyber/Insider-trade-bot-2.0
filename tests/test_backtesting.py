from __future__ import annotations

from backtesting.engine import BacktestEngine


def test_backtest_engine_can_run_basic_trades() -> None:
    engine = BacktestEngine()

    trades = [
        {
            "entry_price": 100.0,
            "exit_price": 110.0,
        },
        {
            "entry_price": 200.0,
            "exit_price": 190.0,
        },
    ]

    result = engine.run(trades)

    assert result is not None
    assert "total_return" in result
    assert "trade_count" in result
    assert result["trade_count"] == 2


def test_backtest_engine_handles_empty_trades() -> None:
    engine = BacktestEngine()

    result = engine.run([])

    assert result is not None
    assert result["trade_count"] == 0


def test_backtest_engine_calculates_trade_returns() -> None:
    engine = BacktestEngine()

    trades = [
        {
            "entry_price": 100.0,
            "exit_price": 110.0,
        },
    ]

    result = engine.run(trades)

    assert result["trade_count"] == 1
    assert result["total_return"] == 0.10
