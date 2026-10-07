"""
Unit tests for backtesting portfolio engine, capital tracking, costs, and drawdown.
"""

from __future__ import annotations

import pytest

from backtesting.engine import (
    BacktestEngine,
    BacktestResult,
    BacktestTrade,
    execute_portfolio_backtest,
)


def test_portfolio_backtest_capital_equity_drawdown_and_costs() -> None:
    trades = [
        BacktestTrade(
            trade_id="t1",
            symbol="AAPL",
            side="buy",
            entry_date="2024-01-02",
            exit_date="2024-01-05",
            entry_price=100.0,
            exit_price=110.0,
            quantity=100.0,
            fees=10.0,
            slippage=5.0,
        ),
        BacktestTrade(
            trade_id="t2",
            symbol="AAPL",
            side="buy",
            entry_date="2024-01-10",
            exit_date="2024-01-15",
            entry_price=110.0,
            exit_price=90.0,
            quantity=100.0,
            fees=10.0,
            slippage=5.0,
        ),
    ]

    res = execute_portfolio_backtest(trades, initial_capital=100000.0)

    # Trade 1 P&L = 100 * (110 - 100) - 15 = +985 -> cash = 100,985 (peak)
    # Trade 2 P&L = 100 * (90 - 110) - 15 = -2,015 -> cash = 98,970
    # Drawdown = (100,985 - 98,970) / 100,985 = 1.9953%
    assert res.initial_capital == 100000.0
    assert res.ending_capital == 98970.0
    assert res.total_return_pct == pytest.approx(-1.03)
    assert res.trade_count == 2
    assert res.winning_trades == 1
    assert res.losing_trades == 1
    assert res.total_fees == 20.0
    assert res.total_slippage == 10.0
    assert res.max_drawdown_pct == pytest.approx(1.99534584344)


def test_portfolio_backtest_rejects_overlapping_symbol_positions() -> None:
    trades = [
        BacktestTrade(
            trade_id="t1",
            symbol="AAPL",
            side="buy",
            entry_date="2024-01-02",
            exit_date="2024-01-10",
            entry_price=100.0,
            exit_price=110.0,
            quantity=10.0,
        ),
        BacktestTrade(
            trade_id="t2",
            symbol="AAPL",
            side="buy",
            entry_date="2024-01-05",  # Overlaps t1!
            exit_date="2024-01-12",
            entry_price=105.0,
            exit_price=115.0,
            quantity=10.0,
        ),
    ]

    with pytest.raises(ValueError, match="Overlapping position detected"):
        execute_portfolio_backtest(trades)


def test_backtest_compatibility_engine_wrapper() -> None:
    engine = BacktestEngine()
    res = engine.run([
        {"entry_price": 100.0, "exit_price": 110.0},
        {"entry_price": 200.0, "exit_price": 190.0},
    ])

    assert res["trade_count"] == 2
    assert res["trade_returns"] == [0.10, -0.05]
    assert res["total_return"] == 0.05
