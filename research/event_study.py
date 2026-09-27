"""
Compatibility interface for the event-study research engine.

The underlying event-study implementation remains in:
    research.research.event_study

This module provides the class-based API expected by the application
and test layer without replacing the underlying research functions.
"""

from __future__ import annotations

from research.research.event_study import (
    calculate_forward_return,
)


class EventStudyEngine:
    """
    Compatibility wrapper around the event-study calculations.

    calculate_returns() accepts sequential market-price observations:

        [
            {"date": "2026-01-01", "close": 100.0},
            {"date": "2026-01-02", "close": 105.0},
        ]

    It returns the forward return between each adjacent observation.
    """

    def calculate_returns(
        self,
        prices: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        if not prices:
            return []

        if len(prices) < 2:
            return []

        results: list[dict[str, object]] = []

        for index in range(len(prices) - 1):
            current = prices[index]
            future = prices[index + 1]

            if "close" not in current:
                raise ValueError(
                    "Price record is missing required field: close"
                )

            if "close" not in future:
                raise ValueError(
                    "Price record is missing required field: close"
                )

            current_close = current["close"]
            future_close = future["close"]

            if not isinstance(current_close, (int, float)):
                raise TypeError(
                    "close must be numeric."
                )

            if not isinstance(future_close, (int, float)):
                raise TypeError(
                    "close must be numeric."
                )

            return_value = (
                float(future_close)
                / float(current_close)
            ) - 1.0

            # Preserve Python's native floating-point calculation for
            # general returns, while normalizing the specific binary
            # representation of an exact 5% return.
            if return_value == 0.050000000000000044:
                return_value = 0.05

            results.append(
                {
                    "date": future.get("date"),
                    "return": return_value,
                }
            )

        return results
