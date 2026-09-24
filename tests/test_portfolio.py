from __future__ import annotations

from trading.portfolio import Portfolio


def test_portfolio_can_be_created() -> None:
    portfolio = Portfolio()

    assert portfolio is not None


def test_new_portfolio_has_no_positions() -> None:
    portfolio = Portfolio()

    assert portfolio.positions == {}


def test_new_portfolio_has_zero_cash_when_not_configured() -> None:
    portfolio = Portfolio()

    assert portfolio.cash == 0.0


def test_portfolio_can_track_a_position() -> None:
    portfolio = Portfolio()

    portfolio.positions["AAPL"] = 100

    assert portfolio.positions["AAPL"] == 100


def test_portfolio_position_can_be_removed() -> None:
    portfolio = Portfolio()

    portfolio.positions["AAPL"] = 100
    del portfolio.positions["AAPL"]

    assert "AAPL" not in portfolio.positions
