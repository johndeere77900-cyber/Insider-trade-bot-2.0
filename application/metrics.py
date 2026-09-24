"""
Application metrics.

Provides a lightweight in-process metrics collector for operational
measurement. It does not make trading or research decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Mapping


@dataclass(frozen=True)
class MetricSnapshot:
    """Immutable snapshot of a metric."""

    name: str
    count: int
    total: float


class ApplicationMetrics:
    """Thread-safe in-process application metrics collector."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: dict[str, int] = {}
        self._totals: dict[str, float] = {}

    def increment(
        self,
        name: str,
        value: int = 1,
    ) -> None:
        """Increment a named counter."""

        normalized = self._normalize_name(name)

        if value < 0:
            raise ValueError("Counter increment cannot be negative.")

        with self._lock:
            self._counts[normalized] = (
                self._counts.get(normalized, 0) + value
            )

    def observe(
        self,
        name: str,
        value: float,
    ) -> None:
        """Record a numeric observation."""

        normalized = self._normalize_name(name)

        with self._lock:
            self._totals[normalized] = (
                self._totals.get(normalized, 0.0) + float(value)
            )

    def snapshot(self) -> Mapping[str, MetricSnapshot]:
        """Return a point-in-time snapshot of all collected metrics."""

        with self._lock:
            names = set(self._counts) | set(self._totals)

            return {
                name: MetricSnapshot(
                    name=name,
                    count=self._counts.get(name, 0),
                    total=self._totals.get(name, 0.0),
                )
                for name in sorted(names)
            }

    def reset(self) -> None:
        """Clear all in-process metrics."""

        with self._lock:
            self._counts.clear()
            self._totals.clear()

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Validate and normalize a metric name."""

        normalized = name.strip()

        if not normalized:
            raise ValueError("Metric name is required.")

        return normalized
