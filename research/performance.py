"""
Historical performance-analysis layer for Insider Trade Bot.

This module aggregates stored signal outcomes into descriptive historical
statistics.

It does not predict future returns, rank securities, or authorize trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median
from typing import Iterable, Mapping


@dataclass(frozen=True)
class PerformanceSummary:
    """
    Descriptive statistics for a collection of signal outcomes.
    """

    outcome_count: int

    mean_return_pct: float | None
    median_return_pct: float | None

    positive_count: int
    negative_count: int
    zero_count: int

    positive_rate_pct: float | None

    best_return_pct: float | None
    worst_return_pct: float | None


class PerformanceAnalysisError(Exception):
    """Raised when performance analysis input is invalid."""


def _extract_return(
    outcome: Mapping[str, object],
) -> float:
    """
    Extract and validate return_pct from one outcome.
    """

    if "return_pct" in outcome:
        value = outcome["return_pct"]

    else:
        result = outcome.get("result")

        if not isinstance(result, Mapping):
            raise PerformanceAnalysisError(
                "Outcome has no valid result payload."
            )

        value = result.get("return_pct")

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PerformanceAnalysisError(
            "return_pct must be numeric."
        )

    return float(value)


def summarize_outcomes(
    outcomes: Iterable[Mapping[str, object]],
) -> PerformanceSummary:
    """
    Calculate descriptive statistics across signal outcomes.
    """

    records = list(outcomes)

    if not records:
        return PerformanceSummary(
            outcome_count=0,
            mean_return_pct=None,
            median_return_pct=None,
            positive_count=0,
            negative_count=0,
            zero_count=0,
            positive_rate_pct=None,
            best_return_pct=None,
            worst_return_pct=None,
        )

    returns = [
        _extract_return(outcome)
        for outcome in records
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

    return PerformanceSummary(
        outcome_count=len(returns),
        mean_return_pct=mean(returns),
        median_return_pct=median(returns),
        positive_count=positive_count,
        negative_count=negative_count,
        zero_count=zero_count,
        positive_rate_pct=(
            positive_count / len(returns)
        ) * 100.0,
        best_return_pct=max(returns),
        worst_return_pct=min(returns),
    )


def compare_performance_periods(
    first_period: Iterable[Mapping[str, object]],
    second_period: Iterable[Mapping[str, object]],
) -> dict[str, PerformanceSummary]:
    """
    Produce independent summaries for two historical periods.

    No winner or ranking is assigned. The caller receives the two
    descriptive summaries for independent interpretation.
    """

    return {
        "first_period": summarize_outcomes(first_period),
        "second_period": summarize_outcomes(second_period),
    }


class ResearchPerformance:
    """
    Compatibility interface for the application factory.

    The underlying performance calculations remain function-based.
    This class exposes them through a small object-oriented interface
    expected by the application layer.
    """

    def summarize(
        self,
        outcomes: Iterable[Mapping[str, object]],
    ) -> PerformanceSummary:
        """Summarize historical signal outcomes."""

        return summarize_outcomes(outcomes)

    def analyze(
        self,
        outcomes: Iterable[Mapping[str, object]],
    ) -> PerformanceSummary:
        """Alias for summarize() for application compatibility."""

        return summarize_outcomes(outcomes)

    def compare(
        self,
        first_period: Iterable[Mapping[str, object]],
        second_period: Iterable[Mapping[str, object]],
    ) -> dict[str, PerformanceSummary]:
        """Compare two periods descriptively without ranking them."""

        return compare_performance_periods(
            first_period,
            second_period,
)
