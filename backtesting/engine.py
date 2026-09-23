"""
Historical backtesting engine for Insider Trade Bot.

This module evaluates stored signal candidates against historical market
prices. It performs simulation only. It does not submit orders and has no
connection to the live-trading execution path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class BacktestTrade:
    """
    One simulated trade generated from a historical signal.
    """

    signal_key: str
    symbol: str

    entry_date: str
    exit_date: str

    entry_price: float
    exit_price: float

    return_pct: float

    holding_periods: int


@dataclass(frozen=True)
class BacktestSummary:
    """
    Aggregate results from a backtest run.
    """

    trade_count: int

    total_return_pct: float | None
    mean_trade_return_pct: float | None

    winning_trade_count: int
    losing_trade_count: int
    zero_return_trade_count: int

    win_rate_pct: float | None

    average_holding_periods: float | None


@dataclass(frozen=True)
class BacktestResult:
    """
    Complete result of a backtest execution.
    """

    trades: tuple[BacktestTrade, ...]
    summary: BacktestSummary


def _validate_price(
    price: float,
    field_name: str,
) -> None:
    """
    Validate a price used by the backtesting engine.
    """

    if not isinstance(price, (int, float)):
        raise TypeError(
            f"{field_name} must be numeric."
        )

    if price <= 0:
        raise ValueError(
            f"{field_name} must be greater than zero."
        )


def _ordered_prices(
    prices: Mapping[str, float],
) -> list[tuple[str, float]]:
    """
    Normalize a date-to-price mapping into chronological order.
    """

    if not prices:
        raise ValueError(
            "At least one market price is required."
        )

    result: list[tuple[str, float]] = []

    for date, price in prices.items():
        normalized_date = str(date).strip()

        if not normalized_date:
            raise ValueError(
                "Price dates cannot be empty."
            )

        _validate_price(
            price,
            "market price",
        )

        result.append(
            (
                normalized_date,
                float(price),
            )
        )

    result.sort(
        key=lambda item: item[0]
    )

    return result


def calculate_return_pct(
    entry_price: float,
    exit_price: float,
) -> float:
    """
    Calculate the percentage return of a simulated long position.
    """

    _validate_price(
        entry_price,
        "entry_price",
    )

    _validate_price(
        exit_price,
        "exit_price",
    )

    return (
        (exit_price / entry_price) - 1.0
    ) * 100.0


def find_exit_observation(
    prices: Mapping[str, float],
    entry_date: str,
    holding_periods: int,
) -> tuple[str, float]:
    """
    Find the historical market observation used as the exit.

    holding_periods represents available market-price observations after
    the entry date, rather than calendar days.
    """

    if holding_periods < 1:
        raise ValueError(
            "holding_periods must be at least 1."
        )

    normalized_entry_date = str(
        entry_date
    ).strip()

    if not normalized_entry_date:
        raise ValueError(
            "entry_date cannot be empty."
        )

    ordered = _ordered_prices(
        prices
    )

    future_observations = [
        item
        for item in ordered
        if item[0] > normalized_entry_date
    ]

    if len(future_observations) < holding_periods:
        raise ValueError(
            "Insufficient historical market observations "
            f"after entry date {normalized_entry_date} "
            f"for holding period {holding_periods}."
        )

    return future_observations[
        holding_periods - 1
    ]


def simulate_trade(
    *,
    signal_key: str,
    symbol: str,
    entry_date: str,
    entry_price: float,
    prices: Mapping[str, float],
    holding_periods: int,
) -> BacktestTrade:
    """
    Simulate one historical trade.
    """

    normalized_signal_key = str(
        signal_key
    ).strip()

    if not normalized_signal_key:
        raise ValueError(
            "signal_key cannot be empty."
        )

    normalized_symbol = str(
        symbol
    ).strip()

    if not normalized_symbol:
        raise ValueError(
            "symbol cannot be empty."
        )

    normalized_entry_date = str(
        entry_date
    ).strip()

    if not normalized_entry_date:
        raise ValueError(
            "entry_date cannot be empty."
        )

    _validate_price(
        entry_price,
        "entry_price",
    )

    exit_date, exit_price = find_exit_observation(
        prices,
        normalized_entry_date,
        holding_periods,
    )

    return_pct = calculate_return_pct(
        entry_price,
        exit_price,
    )

    return BacktestTrade(
        signal_key=normalized_signal_key,
        symbol=normalized_symbol,
        entry_date=normalized_entry_date,
        exit_date=exit_date,
        entry_price=float(entry_price),
        exit_price=float(exit_price),
        return_pct=return_pct,
        holding_periods=holding_periods,
    )


def summarize_trades(
    trades: Iterable[BacktestTrade],
) -> BacktestSummary:
    """
    Calculate aggregate backtest statistics.
    """

    records = list(trades)

    if not records:
        return BacktestSummary(
            trade_count=0,
            total_return_pct=None,
            mean_trade_return_pct=None,
            winning_trade_count=0,
            losing_trade_count=0,
            zero_return_trade_count=0,
            win_rate_pct=None,
            average_holding_periods=None,
        )

    returns = [
        float(trade.return_pct)
        for trade in records
    ]

    holding_periods = [
        trade.holding_periods
        for trade in records
    ]

    winning_count = sum(
        1
        for value in returns
        if value > 0
    )

    losing_count = sum(
        1
        for value in returns
        if value < 0
    )

    zero_count = sum(
        1
        for value in returns
        if value == 0
    )

    return BacktestSummary(
        trade_count=len(records),
        total_return_pct=sum(returns),
        mean_trade_return_pct=(
            sum(returns) / len(returns)
        ),
        winning_trade_count=winning_count,
        losing_trade_count=losing_count,
        zero_return_trade_count=zero_count,
        win_rate_pct=(
            winning_count / len(records)
        ) * 100.0,
        average_holding_periods=(
            sum(holding_periods)
            / len(holding_periods)
        ),
    )


def run_backtest(
    trades: Iterable[dict[str, object]],
) -> BacktestResult:
    """
    Run a collection of historical trade simulations.

    Each input trade must contain:

        signal_key
        symbol
        entry_date
        entry_price
        prices
        holding_periods
    """

    results: list[BacktestTrade] = []

    for index, trade in enumerate(trades):
        try:
            signal_key = str(
                trade["signal_key"]
            )
            symbol = str(
                trade["symbol"]
            )
            entry_date = str(
                trade["entry_date"]
            )
            entry_price = float(
                trade["entry_price"]
            )
            prices = trade["prices"]
            holding_periods = int(
                trade["holding_periods"]
            )

        except KeyError as exc:
            raise ValueError(
                f"Backtest trade {index} is missing "
                f"required field: {exc.args[0]}"
            ) from exc

        if not isinstance(
            prices,
            Mapping,
        ):
            raise TypeError(
                f"Backtest trade {index} "
                "'prices' must be a date-to-price mapping."
            )

        result = simulate_trade(
            signal_key=signal_key,
            symbol=symbol,
            entry_date=entry_date,
            entry_price=entry_price,
            prices=prices,
            holding_periods=holding_periods,
        )

        results.append(result)

    summary = summarize_trades(
        results
    )

    return BacktestResult(
        trades=tuple(results),
        summary=summary,
  )
