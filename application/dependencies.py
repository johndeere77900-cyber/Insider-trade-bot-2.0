"""
Application dependency container.

Keeps shared infrastructure dependencies together so the application can be
assembled and replaced cleanly during integration and testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ApplicationDependencies:
    """Shared dependencies used by the application."""

    database: Optional[Any] = None
    audit: Optional[Any] = None
    health: Optional[Any] = None
    observability: Optional[Any] = None
    metrics: Optional[Any] = None
    execution_service: Optional[Any] = None
    data_services: Optional[Any] = None
    research_services: Optional[Any] = None
    signal_services: Optional[Any] = None
    backtest_services: Optional[Any] = None
    outcome_services: Optional[Any] = None
    portfolio: Optional[Any] = None

    def require(self, name: str) -> Any:
        """
        Return a dependency that must exist.

        Raises:
            RuntimeError: if the requested dependency is not configured.
        """

        if not name.strip():
            raise ValueError("Dependency name is required.")

        value = getattr(self, name, None)

        if value is None:
            raise RuntimeError(
                f"Required application dependency is not configured: {name}"
            )

        return value
