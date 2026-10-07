"""
Historical backtesting engine for Insider Trade Bot.

This module evaluates stored signal candidates against historical market
prices with capital allocation, cost modeling (fees & slippage), and maximum drawdown tracking.
It performs simulation only. It does not submit orders and has no
connection to the live-trading execution path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class BacktestTrade:
    """One simulated portfolio trade with explicit execution details and cost accounting."""

    trade_id: str
    symbol: str
    side: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    quantity: float
    fees: float = 0.0
    slippage: float = 0.0


@dataclass(frozen=True)
class BacktestResult:
    """Complete summary result of portfolio-aware backtest execution."""

    initial_capital: float
    ending_capital: float
    total_return_pct: float
    trade_count: int
    winning_trades: int
    losing_trades: int
    max_drawdown_pct: float
    total_fees: float
    total_slippage: float


def _validate_positive(value: float, name: str) -> float:
    if not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric.")
    val = float(value)
    if val <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return val


def execute_portfolio_backtest(
    trades: Sequence[BacktestTrade | Mapping[str, object]],
    *,
    initial_capital: float = 100000.0,
    allow_overlapping_symbol_positions: bool = False,
) -> BacktestResult:
    """
    Execute portfolio-aware chronological backtest simulation.

    Rules:
    1. Validate chronological ordering (entry_date <= exit_date).
    2. Validate positive prices, positive quantity, valid side ("buy" or "sell").
    3. Calculate gross and net P&L with fees and slippage.
    4. Track cash/equity curve and calculate maximum drawdown percentage.
    5. Never calculate total return by simply summing percentage returns.
    6. Reject overlapping trades for the same symbol unless explicitly allowed.
    """
    cap = _validate_positive(initial_capital, "initial_capital")

    if not trades:
        return BacktestResult(
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
            t = BacktestTrade(
                trade_id=str(item.get("trade_id") or f"trade_{idx}"),
                symbol=str(item["symbol"]).strip().upper(),
                side=str(item.get("side", "buy")).strip().lower(),
                entry_date=str(item["entry_date"]).strip(),
                exit_date=str(item["exit_date"]).strip(),
                entry_price=float(item["entry_price"]),
                exit_price=float(item["exit_price"]),
                quantity=float(item.get("quantity", 1.0)),
                fees=float(item.get("fees", 0.0)),
                slippage=float(item.get("slippage", 0.0)),
            )
        else:
            raise TypeError(f"Trade item {idx} must be BacktestTrade or Mapping.")

        # Validations
        if t.entry_date > t.exit_date:
            raise ValueError(f"Trade '{t.trade_id}' entry_date '{t.entry_date}' is after exit_date '{t.exit_date}'.")
        _validate_positive(t.entry_price, f"Trade '{t.trade_id}' entry_price")
        _validate_positive(t.exit_price, f"Trade '{t.trade_id}' exit_price")
        _validate_positive(t.quantity, f"Trade '{t.trade_id}' quantity")
        if t.side not in {"buy", "sell"}:
            raise ValueError(f"Trade '{t.trade_id}' side must be 'buy' or 'sell'.")
        if t.fees < 0 or t.slippage < 0:
            raise ValueError(f"Trade '{t.trade_id}' fees and slippage cannot be negative.")

        normalized_trades.append(t)

    # Sort trades chronologically by entry_date then exit_date
    normalized_trades.sort(key=lambda x: (x.entry_date, x.exit_date))

    # Reject overlapping positions for the same symbol unless allowed
    if not allow_overlapping_symbol_positions:
        active_symbol_exits: dict[str, str] = {}
        for t in normalized_trades:
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
        # Long position P&L = quantity * (exit_price - entry_price) - fees - slippage
        # Short position P&L = quantity * (entry_price - exit_price) - fees - slippage
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

    return BacktestResult(
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
    """Compatibility wrapper function for executing portfolio backtest."""
    return execute_portfolio_backtest(
        trades,
        initial_capital=initial_capital,
        allow_overlapping_symbol_positions=allow_overlapping_symbol_positions,
    )


class BacktestEngine:
    """
    Compatibility interface for trade-list backtesting.
    """

    def run(
        self,
        trades: Iterable[Mapping[str, object]],
    ) -> dict[str, object]:
        """Run trades and return dictionary-based results."""
        records = list(trades)

        if not records:
            return {
                "total_return": 0.0,
                "trade_count": 0,
                "trade_returns": [],
            }

        trade_returns: list[float] = []

        for index, trade in enumerate(records):
            if "entry_price" not in trade:
                raise ValueError(f"Trade {index} is missing entry_price.")
            if "exit_price" not in trade:
                raise ValueError(f"Trade {index} is missing exit_price.")

            entry_price = float(trade["entry_price"])
            exit_price = float(trade["exit_price"])

            _validate_positive(entry_price, "entry_price")
            _validate_positive(exit_price, "exit_price")

            trade_return = round((exit_price / entry_price) - 1.0, 10)
            trade_returns.append(trade_return)

        return {
            "total_return": round(sum(trade_returns), 10),
            "trade_count": len(trade_returns),
            "trade_returns": trade_returns,
        }
