"""
Historical backtesting engine for Insider Trade Bot.

This module evaluates stored signal candidates against historical market prices.
It provides portfolio cash/equity P&L accounting, capital tracking, cost modeling
(fees & slippage), and maximum drawdown tracking.

It performs simulation only. It does not submit orders and has no connection
to the live-trading execution path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class BacktestTrade:
    """One simulated trade with explicit execution details and cost accounting."""

    signal_key: str = ""
    symbol: str = ""

    entry_date: str = ""
    exit_date: str = ""

    entry_price: float = 0.0
    exit_price: float = 0.0

    return_pct: float = 0.0
    holding_periods: int = 1

    # Portfolio-aware attributes
    trade_id: str = ""
    side: str = "buy"
    quantity: float = 1.0
    fees: float = 0.0
    slippage: float = 0.0


@dataclass(frozen=True)
class BacktestSummary:
    """Aggregate results from a trade-list or portfolio backtest run."""

    trade_count: int

    total_return_pct: float | None
    mean_trade_return_pct: float | None

    winning_trade_count: int
    losing_trade_count: int
    zero_return_trade_count: int

    win_rate_pct: float | None

    average_holding_periods: float | None = None


@dataclass(frozen=True)
class BacktestResult:
    """Complete summary result of backtest execution."""

    trades: tuple[BacktestTrade, ...]
    summary: BacktestSummary

    # Portfolio-aware summary fields
    initial_capital: float = 100000.0
    ending_capital: float = 100000.0
    total_return_pct: float = 0.0
    trade_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    max_drawdown_pct: float = 0.0
    total_fees: float = 0.0
    total_slippage: float = 0.0


def _validate_price(price: float, field_name: str) -> float:
    if not isinstance(price, (int, float)):
        raise TypeError(f"{field_name} must be numeric.")
    val = float(price)
    if val <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return val


def _ordered_prices(prices: Mapping[str, float]) -> list[tuple[str, float]]:
    if not prices:
        raise ValueError("At least one market price is required.")

    result: list[tuple[str, float]] = []
    for date, price in prices.items():
        normalized_date = str(date).strip()
        if not normalized_date:
            raise ValueError("Price dates cannot be empty.")
        _validate_price(price, "market price")
        result.append((normalized_date, float(price)))

    result.sort(key=lambda item: item[0])
    return result


def calculate_return_pct(entry_price: float, exit_price: float) -> float:
    _validate_price(entry_price, "entry_price")
    _validate_price(exit_price, "exit_price")
    return ((exit_price / entry_price) - 1.0) * 100.0


def find_exit_observation(
    prices: Mapping[str, float],
    entry_date: str,
    holding_periods: int,
) -> tuple[str, float]:
    if holding_periods < 1:
        raise ValueError("holding_periods must be at least 1.")

    normalized_entry_date = str(entry_date).strip()
    if not normalized_entry_date:
        raise ValueError("entry_date cannot be empty.")

    ordered = _ordered_prices(prices)
    future_observations = [
        item for item in ordered if item[0] > normalized_entry_date
    ]

    if len(future_observations) < holding_periods:
        raise ValueError(
            "Insufficient historical market observations "
            f"after entry date {normalized_entry_date} "
            f"for holding period {holding_periods}."
        )

    return future_observations[holding_periods - 1]


def simulate_trade(
    *,
    signal_key: str,
    symbol: str,
    entry_date: str,
    entry_price: float,
    prices: Mapping[str, float],
    holding_periods: int,
) -> BacktestTrade:
    normalized_signal_key = str(signal_key).strip()
    if not normalized_signal_key:
        raise ValueError("signal_key cannot be empty.")

    normalized_symbol = str(symbol).strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol cannot be empty.")

    normalized_entry_date = str(entry_date).strip()
    if not normalized_entry_date:
        raise ValueError("entry_date cannot be empty.")

    _validate_price(entry_price, "entry_price")

    exit_date, exit_price = find_exit_observation(
        prices, normalized_entry_date, holding_periods
    )

    return_pct = calculate_return_pct(entry_price, exit_price)

    return BacktestTrade(
        signal_key=normalized_signal_key,
        symbol=normalized_symbol,
        entry_date=normalized_entry_date,
        exit_date=exit_date,
        entry_price=float(entry_price),
        exit_price=float(exit_price),
        return_pct=return_pct,
        holding_periods=holding_periods,
        trade_id=normalized_signal_key,
        side="buy",
        quantity=1.0,
        fees=0.0,
        slippage=0.0,
    )


def summarize_trades(trades: Iterable[BacktestTrade]) -> BacktestSummary:
    records = list(trades)

    if not records:
        return BacktestSummary(
            trade_count=0,
            total_return_pct=0.0,
            mean_trade_return_pct=None,
            winning_trade_count=0,
            losing_trade_count=0,
            zero_return_trade_count=0,
            win_rate_pct=None,
            average_holding_periods=None,
        )

    returns = [float(trade.return_pct) for trade in records]
    holding_periods = [trade.holding_periods for trade in records]

    winning_count = sum(1 for value in returns if value > 0)
    losing_count = sum(1 for value in returns if value < 0)
    zero_count = sum(1 for value in returns if value == 0)

    return BacktestSummary(
        trade_count=len(records),
        total_return_pct=sum(returns),
        mean_trade_return_pct=(sum(returns) / len(records)),
        winning_trade_count=winning_count,
        losing_trade_count=losing_count,
        zero_return_trade_count=zero_count,
        win_rate_pct=(winning_count / len(records)) * 100.0,
        average_holding_periods=(sum(holding_periods) / len(holding_periods)),
    )


def execute_portfolio_backtest(
    trades: Sequence[BacktestTrade | Mapping[str, object]],
    *,
    initial_capital: float = 100000.0,
    allow_overlapping_symbol_positions: bool = False,
) -> BacktestResult:
    """
    Execute portfolio-aware chronological backtest simulation.

    Fees and slippage are absolute currency costs that reduce net P&L.
    Total return is calculated strictly from ending capital vs initial capital:
        ((ending_capital / initial_capital) - 1.0) * 100.0
    """
    cap = _validate_price(initial_capital, "initial_capital")

    if not trades:
        empty_summary = BacktestSummary(
            trade_count=0,
            total_return_pct=0.0,
            mean_trade_return_pct=None,
            winning_trade_count=0,
            losing_trade_count=0,
            zero_return_trade_count=0,
            win_rate_pct=None,
        )
        return BacktestResult(
            trades=(),
            summary=empty_summary,
            initial_capital=cap,
            ending_capital=cap,
            total_return_pct=0.0,
            trade_count=0,
            winning_trades=0,
            losing_trades=0,
            max_drawdown_pct=0.0,
            total_fees=0.0,
            total_slippage=0.0,
        )

    normalized_trades: list[BacktestTrade] = []
    for idx, item in enumerate(trades):
        if isinstance(item, BacktestTrade):
            t = item
        elif isinstance(item, Mapping):
            e_price = float(item["entry_price"])
            ex_price = float(item["exit_price"])
            ret_pct = calculate_return_pct(e_price, ex_price)
            t = BacktestTrade(
                signal_key=str(item.get("signal_key") or item.get("trade_id") or f"trade_{idx}"),
                trade_id=str(item.get("trade_id") or item.get("signal_key") or f"trade_{idx}"),
                symbol=str(item.get("symbol", "UNKNOWN")).strip().upper(),
                side=str(item.get("side", "buy")).strip().lower(),
                entry_date=str(item.get("entry_date", "2024-01-01")).strip(),
                exit_date=str(item.get("exit_date", "2024-01-02")).strip(),
                entry_price=e_price,
                exit_price=ex_price,
                return_pct=ret_pct,
                holding_periods=int(item.get("holding_periods", 1)),
                quantity=float(item.get("quantity", 1.0)),
                fees=float(item.get("fees", 0.0)),
                slippage=float(item.get("slippage", 0.0)),
            )
        else:
            raise TypeError(f"Trade item {idx} must be BacktestTrade or Mapping.")

        # Validations
        if t.entry_date > t.exit_date:
            raise ValueError(f"Trade '{t.trade_id}' entry_date '{t.entry_date}' is after exit_date '{t.exit_date}'.")
        _validate_price(t.entry_price, f"Trade '{t.trade_id}' entry_price")
        _validate_price(t.exit_price, f"Trade '{t.trade_id}' exit_price")
        _validate_price(t.quantity, f"Trade '{t.trade_id}' quantity")
        if t.side not in {"buy", "sell"}:
            raise ValueError(f"Trade '{t.trade_id}' side must be 'buy' or 'sell'.")
        if t.fees < 0:
            raise ValueError(f"Trade '{t.trade_id}' fees cannot be negative.")
        if t.slippage < 0:
            raise ValueError(f"Trade '{t.trade_id}' slippage cannot be negative.")

        normalized_trades.append(t)

    # Sort trades chronologically
    normalized_trades.sort(key=lambda x: (x.entry_date, x.exit_date))

    if not allow_overlapping_symbol_positions:
        active_symbol_exits: dict[str, str] = {}
        for t in normalized_trades:
            if not t.symbol:
                continue
            last_exit = active_symbol_exits.get(t.symbol)
            if last_exit is not None and t.entry_date < last_exit:
                raise ValueError(
                    f"Overlapping position detected for symbol {t.symbol}: "
                    f"trade entry {t.entry_date} is before prior position exit {last_exit}."
                )
            active_symbol_exits[t.symbol] = max(last_exit or "", t.exit_date)

    current_cash = cap
    peak_equity = cap
    max_drawdown = 0.0

    winning_count = 0
    losing_count = 0
    total_fees_accum = 0.0
    total_slippage_accum = 0.0

    for t in normalized_trades:
        if t.side == "buy":
            gross_pnl = t.quantity * (t.exit_price - t.entry_price)
        else:
            gross_pnl = t.quantity * (t.entry_price - t.exit_price)

        cost = t.fees + t.slippage
        net_pnl = gross_pnl - cost

        total_fees_accum += t.fees
        total_slippage_accum += t.slippage

        current_cash += net_pnl

        if net_pnl > 0:
            winning_count += 1
        elif net_pnl < 0:
            losing_count += 1

        if current_cash > peak_equity:
            peak_equity = current_cash

        dd = (peak_equity - current_cash) / peak_equity * 100.0 if peak_equity > 0 else 0.0
        if dd > max_drawdown:
            max_drawdown = dd

    total_ret_pct = ((current_cash / cap) - 1.0) * 100.0

    summary = summarize_trades(normalized_trades)

    return BacktestResult(
        trades=tuple(normalized_trades),
        summary=summary,
        initial_capital=cap,
        ending_capital=current_cash,
        total_return_pct=total_ret_pct,
        trade_count=len(normalized_trades),
        winning_trades=winning_count,
        losing_trades=losing_count,
        max_drawdown_pct=max_drawdown,
        total_fees=total_fees_accum,
        total_slippage=total_slippage_accum,
    )


def run_backtest(
    trades: Sequence[BacktestTrade | Mapping[str, object]],
    *,
    initial_capital: float = 100000.0,
    allow_overlapping_symbol_positions: bool = False,
) -> BacktestResult:
    """
    Run a collection of historical trade simulations.

    When trades supply full trade specs (or trade dicts), computes portfolio-aware
    backtest result using capital tracking.
    """
    if not trades:
        return execute_portfolio_backtest([], initial_capital=initial_capital)

    first_item = list(trades)[0]
    if isinstance(first_item, Mapping) and "prices" in first_item and "holding_periods" in first_item:
        # Classical trade simulation mode
        results: list[BacktestTrade] = []
        for index, trade in enumerate(trades):
            try:
                signal_key = str(trade["signal_key"])
                symbol = str(trade["symbol"])
                entry_date = str(trade["entry_date"])
                entry_price = float(trade["entry_price"])
                prices = trade["prices"]
                holding_periods = int(trade["holding_periods"])
            except KeyError as exc:
                raise ValueError(
                    f"Backtest trade {index} is missing required field: {exc.args[0]}"
                ) from exc

            if not isinstance(prices, Mapping):
                raise TypeError(
                    f"Backtest trade {index} 'prices' must be a date-to-price mapping."
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

        return execute_portfolio_backtest(
            results,
            initial_capital=initial_capital,
            allow_overlapping_symbol_positions=allow_overlapping_symbol_positions,
        )

    return execute_portfolio_backtest(
        trades,
        initial_capital=initial_capital,
        allow_overlapping_symbol_positions=allow_overlapping_symbol_positions,
    )


class BacktestEngine:
    """
    Compatibility interface for trade-list backtesting.

    Delegates to portfolio-aware capital calculations rather than summing trade percentages.
    """

    def run(
        self,
        trades: Iterable[Mapping[str, object]],
    ) -> dict[str, object]:
        records = list(trades)

        if not records:
            return {
                "total_return": 0.0,
                "trade_count": 0,
                "trade_returns": [],
            }

        trade_returns: list[float] = []
        parsed_trades: list[dict[str, object]] = []

        for index, trade in enumerate(records):
            if "entry_price" not in trade:
                raise ValueError(f"Trade {index} is missing entry_price.")
            if "exit_price" not in trade:
                raise ValueError(f"Trade {index} is missing exit_price.")

            entry_price = float(trade["entry_price"])
            exit_price = float(trade["exit_price"])

            _validate_price(entry_price, "entry_price")
            _validate_price(exit_price, "exit_price")

            trade_return = round((exit_price / entry_price) - 1.0, 10)
            trade_returns.append(trade_return)

            parsed_trades.append({
                "trade_id": f"trade_{index}",
                "symbol": str(trade.get("symbol", "UNKNOWN")),
                "side": str(trade.get("side", "buy")),
                "entry_date": str(trade.get("entry_date", f"2024-01-{(index%20)+1:02d}")),
                "exit_date": str(trade.get("exit_date", f"2024-01-{(index%20)+2:02d}")),
                "entry_price": entry_price,
                "exit_price": exit_price,
                "quantity": float(trade.get("quantity", 1.0)),
                "fees": float(trade.get("fees", 0.0)),
                "slippage": float(trade.get("slippage", 0.0)),
            })

        # Delegate total return calculation to portfolio capital outcome
        res = execute_portfolio_backtest(parsed_trades, initial_capital=100000.0, allow_overlapping_symbol_positions=True)
        portfolio_total_return_decimal = res.total_return_pct / 100.0

        return {
            "total_return": round(portfolio_total_return_decimal, 10),
            "trade_count": len(trade_returns),
            "trade_returns": trade_returns,
        }
