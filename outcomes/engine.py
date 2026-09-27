"""
Signal-outcome evaluation engine for Insider Trade Bot.

This module provides:
1. The production signal-outcome evaluation functions.
2. OutcomeEngine compatibility API used by the application/test layer.

It does not place trades and does not modify the original signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class SignalOutcome:
    signal_key: str
    symbol: str
    signal_date: str
    outcome_date: str
    signal_price: float
    outcome_price: float
    return_pct: float
    evaluation_periods: int


class OutcomeEvaluationError(Exception):
    """Raised when a signal outcome cannot be evaluated."""


def _validate_price(price: float, field_name: str) -> None:
    if not isinstance(price, (int, float)):
        raise OutcomeEvaluationError(f"{field_name} must be numeric.")

    if price <= 0:
        raise OutcomeEvaluationError(
            f"{field_name} must be greater than zero."
        )


def _ordered_prices(
    prices: Mapping[str, float],
) -> list[tuple[str, float]]:
    if not prices:
        raise OutcomeEvaluationError(
            "At least one market-price observation is required."
        )

    result: list[tuple[str, float]] = []

    for date, price in prices.items():
        normalized_date = str(date).strip()

        if not normalized_date:
            raise OutcomeEvaluationError(
                "Market-price dates cannot be empty."
            )

        _validate_price(price, "market price")

        result.append(
            (
                normalized_date,
                float(price),
            )
        )

    result.sort(key=lambda item: item[0])

    return result


def calculate_return_pct(
    signal_price: float,
    outcome_price: float,
) -> float:
    _validate_price(signal_price, "signal_price")
    _validate_price(outcome_price, "outcome_price")

    return ((outcome_price / signal_price) - 1.0) * 100.0


def find_outcome_observation(
    prices: Mapping[str, float],
    signal_date: str,
    evaluation_periods: int,
) -> tuple[str, float]:
    if evaluation_periods < 1:
        raise OutcomeEvaluationError(
            "evaluation_periods must be at least 1."
        )

    normalized_signal_date = str(signal_date).strip()

    if not normalized_signal_date:
        raise OutcomeEvaluationError(
            "signal_date cannot be empty."
        )

    ordered = _ordered_prices(prices)

    future_observations = [
        item
        for item in ordered
        if item[0] > normalized_signal_date
    ]

    if len(future_observations) < evaluation_periods:
        raise OutcomeEvaluationError(
            "Insufficient market-price observations "
            f"after signal date {normalized_signal_date} "
            f"for evaluation period {evaluation_periods}."
        )

    return future_observations[evaluation_periods - 1]


def evaluate_signal(
    *,
    signal_key: str,
    symbol: str,
    signal_date: str,
    signal_price: float,
    prices: Mapping[str, float],
    evaluation_periods: int,
) -> SignalOutcome:
    normalized_signal_key = str(signal_key).strip()

    if not normalized_signal_key:
        raise OutcomeEvaluationError(
            "signal_key cannot be empty."
        )

    normalized_symbol = str(symbol).strip()

    if not normalized_symbol:
        raise OutcomeEvaluationError(
            "symbol cannot be empty."
        )

    normalized_signal_date = str(signal_date).strip()

    if not normalized_signal_date:
        raise OutcomeEvaluationError(
            "signal_date cannot be empty."
        )

    _validate_price(signal_price, "signal_price")

    outcome_date, outcome_price = find_outcome_observation(
        prices,
        normalized_signal_date,
        evaluation_periods,
    )

    return_pct = calculate_return_pct(
        signal_price,
        outcome_price,
    )

    return SignalOutcome(
        signal_key=normalized_signal_key,
        symbol=normalized_symbol,
        signal_date=normalized_signal_date,
        outcome_date=outcome_date,
        signal_price=float(signal_price),
        outcome_price=float(outcome_price),
        return_pct=return_pct,
        evaluation_periods=evaluation_periods,
    )


def outcome_to_dict(
    outcome: SignalOutcome,
) -> dict[str, object]:
    return {
        "signal_key": outcome.signal_key,
        "symbol": outcome.symbol,
        "signal_date": outcome.signal_date,
        "outcome_date": outcome.outcome_date,
        "signal_price": outcome.signal_price,
        "outcome_price": outcome.outcome_price,
        "return_pct": outcome.return_pct,
        "evaluation_periods": outcome.evaluation_periods,
    }


class OutcomeEngine:
    """
    Compatibility wrapper for the application/test layer.

    The lower-level production API remains available through
    evaluate_signal() and the other functions above.
    """

    def evaluate(
        self,
        outcomes: list[Mapping[str, object]],
    ) -> dict[str, object]:
        """
        Evaluate simple entry/exit outcome records.

        Expected input format:

            [
                {
                    "entry_price": 100.0,
                    "exit_price": 110.0,
                }
            ]

        The return value provides a stable summary containing the
        evaluated count and individual returns.
        """

        if not outcomes:
            return {
                "outcome_count": 0,
                "total_return": 0.0,
                "outcomes": [],
            }

        evaluated: list[dict[str, float]] = []
        total_return = 0.0

        for outcome in outcomes:
            if "entry_price" not in outcome:
                raise OutcomeEvaluationError(
                    "entry_price is required."
                )

            if "exit_price" not in outcome:
                raise OutcomeEvaluationError(
                    "exit_price is required."
                )

            entry_price = outcome["entry_price"]
            exit_price = outcome["exit_price"]

            _validate_price(
                entry_price,  # type: ignore[arg-type]
                "entry_price",
            )

            _validate_price(
                exit_price,  # type: ignore[arg-type]
                "exit_price",
            )

            return_value = (
                float(exit_price) / float(entry_price)
            ) - 1.0

            total_return += return_value

            evaluated.append(
                {
                    "entry_price": float(entry_price),
                    "exit_price": float(exit_price),
                    "return": return_value,
                }
            )

        return {
            "outcome_count": len(evaluated),
            "total_return": total_return,
            "outcomes": evaluated,
    }
