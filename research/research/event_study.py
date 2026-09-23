"""
Event-study research engine for Insider Trade Bot.

This module provides deterministic event-study calculations using historical
market prices. It does not generate trading orders and does not authorize
live trading.

The engine calculates forward returns from an event date and summarizes
those returns across a collection of events.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import Iterable, Mapping


@dataclass(frozen=True)
class EventReturn:
    """
    Forward return observed after a research event.
    """

    event_key: str
    symbol: str
    event_date: str

    horizon_days: int

    event_price: float
    future_price: float

    return_pct: float


@dataclass(frozen=True)
class EventStudySummary:
    """
    Aggregate statistics for a collection of event returns.
    """

    event_count: int

    horizon_days: int

    mean_return_pct: float | None
    median_return_pct: float | None

    positive_event_count: int
    negative_event_count: int
    zero_return_event_count: int

    positive_event_rate_pct: float | None


def _validate_price(
    price: float,
    field_name: str,
) -> None:
    """
    Validate a market price used by the event-study engine.
    """

    if not isinstance(price, (int, float)):
        raise TypeError(
            f"{field_name} must be numeric."
        )

    if price <= 0:
        raise ValueError(
            f"{field_name} must be greater than zero."
        )


def _sorted_prices(
    prices: Mapping[str, float],
) -> list[tuple[str, float]]:
    """
    Normalize and validate a date-to-price mapping.

    Date strings are expected to use a lexicographically sortable format,
    such as YYYY-MM-DD.
    """

    if not prices:
        raise ValueError(
            "At least one market price is required."
        )

    normalized: list[tuple[str, float]] = []

    for date, price in prices.items():
        normalized_date = str(date).strip()

        if not normalized_date:
            raise ValueError(
                "Market-price dates cannot be empty."
            )

        _validate_price(
            price,
            "market price",
        )

        normalized.append(
            (
                normalized_date,
                float(price),
            )
        )

    normalized.sort(
        key=lambda item: item[0]
    )

    return normalized


def calculate_forward_return(
    event_price: float,
    future_price: float,
) -> float:
    """
    Calculate a simple percentage return.

    Formula:

        ((future_price / event_price) - 1) * 100
    """

    _validate_price(
        event_price,
        "event_price",
    )

    _validate_price(
        future_price,
        "future_price",
    )

    return (
        (future_price / event_price) - 1.0
    ) * 100.0


def find_horizon_price(
    prices: Mapping[str, float],
    event_date: str,
    horizon_days: int,
) -> tuple[str, float]:
    """
    Find the market price at a specified number of observations after
    the event date.

    The horizon is measured in available market-price observations rather
    than calendar days. This avoids incorrectly assuming that every
    calendar day has a market-price record.

    Example:

        horizon_days=1

    means the first available market observation after the event date.
    """

    if horizon_days < 1:
        raise ValueError(
            "horizon_days must be at least 1."
        )

    normalized_event_date = str(
        event_date
    ).strip()

    if not normalized_event_date:
        raise ValueError(
            "event_date cannot be empty."
        )

    ordered_prices = _sorted_prices(
        prices
    )

    future_prices = [
        item
        for item in ordered_prices
        if item[0] > normalized_event_date
    ]

    if len(future_prices) < horizon_days:
        raise ValueError(
            "Insufficient market-price observations "
            f"after event date {normalized_event_date} "
            f"for horizon {horizon_days}."
        )

    return future_prices[
        horizon_days - 1
    ]


def calculate_event_return(
    *,
    event_key: str,
    symbol: str,
    event_date: str,
    event_price: float,
    prices: Mapping[str, float],
    horizon_days: int,
) -> EventReturn:
    """
    Calculate the forward return for one research event.
    """

    normalized_event_date = str(
        event_date
    ).strip()

    if not normalized_event_date:
        raise ValueError(
            "event_date cannot be empty."
        )

    normalized_symbol = str(
        symbol
    ).strip()

    if not normalized_symbol:
        raise ValueError(
            "symbol cannot be empty."
        )

    normalized_event_key = str(
        event_key
    ).strip()

    if not normalized_event_key:
        raise ValueError(
            "event_key cannot be empty."
        )

    _validate_price(
        event_price,
        "event_price",
    )

    future_date, future_price = find_horizon_price(
        prices,
        normalized_event_date,
        horizon_days,
    )

    return_pct = calculate_forward_return(
        event_price,
        future_price,
    )

    return EventReturn(
        event_key=normalized_event_key,
        symbol=normalized_symbol,
        event_date=normalized_event_date,
        horizon_days=horizon_days,
        event_price=float(event_price),
        future_price=float(future_price),
        return_pct=return_pct,
    )


def summarize_event_returns(
    event_returns: Iterable[EventReturn],
) -> EventStudySummary:
    """
    Summarize a collection of event returns.

    All event returns must use the same horizon.
    """

    records = list(event_returns)

    if not records:
        return EventStudySummary(
            event_count=0,
            horizon_days=0,
            mean_return_pct=None,
            median_return_pct=None,
            positive_event_count=0,
            negative_event_count=0,
            zero_return_event_count=0,
            positive_event_rate_pct=None,
        )

    horizon_days = records[0].horizon_days

    if horizon_days < 1:
        raise ValueError(
            "Event-return horizon must be at least 1."
        )

    for record in records:
        if record.horizon_days != horizon_days:
            raise ValueError(
                "All event returns must use the same horizon."
            )

    returns = [
        float(record.return_pct)
        for record in records
    ]

    positive_count = sum(
        1
        for value in returns
        if value > 0
    )

    negative_count = sum(
        1
        for value in returns
        if value < 0
    )

    zero_count = sum(
        1
        for value in returns
        if value == 0
    )

    positive_rate = (
        positive_count / len(returns)
    ) * 100.0

    return EventStudySummary(
        event_count=len(records),
        horizon_days=horizon_days,
        mean_return_pct=mean(returns),
        median_return_pct=median(returns),
        positive_event_count=positive_count,
        negative_event_count=negative_count,
        zero_return_event_count=zero_count,
        positive_event_rate_pct=positive_rate,
    )


def run_event_study(
    events: Iterable[dict[str, object]],
    horizon_days: int,
) -> tuple[
    list[EventReturn],
    EventStudySummary,
]:
    """
    Run an event study over normalized event inputs.

    Each event must contain:

        event_key
        symbol
        event_date
        event_price
        prices

    The prices field must be a mapping of date -> market price.

    Events for which the requested horizon cannot be calculated are not
    silently substituted with another horizon. Instead, the function
    raises an error so incomplete research is visible to the caller.
    """

    if horizon_days < 1:
        raise ValueError(
            "horizon_days must be at least 1."
        )

    results: list[EventReturn] = []

    for event in events:
        try:
            event_key = str(
                event["event_key"]
            )
            symbol = str(
                event["symbol"]
            )
            event_date = str(
                event["event_date"]
            )
            event_price = float(
                event["event_price"]
            )

            prices = event["prices"]

        except KeyError as exc:
            raise ValueError(
                f"Event is missing required field: {exc.args[0]}"
            ) from exc

        if not isinstance(
            prices,
            Mapping,
        ):
            raise TypeError(
                "Event 'prices' must be a date-to-price mapping."
            )

        result = calculate_event_return(
            event_key=event_key,
            symbol=symbol,
            event_date=event_date,
            event_price=event_price,
            prices=prices,
            horizon_days=horizon_days,
        )

        results.append(result)

    summary = summarize_event_returns(
        results
    )

    return results, summary
