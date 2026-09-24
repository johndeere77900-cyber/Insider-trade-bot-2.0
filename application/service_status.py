"""
Application service status reporting.

Provides a consolidated, non-destructive status view of the major services.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional


class ApplicationServiceStatus:
    """Reports configured application service availability."""

    def __init__(
        self,
        *,
        application_service: Any,
        trading_service: Optional[Any] = None,
    ) -> None:
        if application_service is None:
            raise ValueError("application_service is required.")

        self.application_service = application_service
        self.trading_service = trading_service

    def report(self) -> Mapping[str, Any]:
        """Return a consolidated service status report."""

        application_status = self._application_status()

        return {
            "application": application_status,
            "services": {
                "research": self._availability(
                    getattr(
                        self.application_service,
                        "event_study_engine",
                        None,
                    )
                ),
                "signals": self._availability(
                    getattr(
                        self.application_service,
                        "signal_engine",
                        None,
                    )
                ),
                "backtesting": self._availability(
                    getattr(
                        self.application_service,
                        "backtest_engine",
                        None,
                    )
                ),
                "outcomes": self._availability(
                    getattr(
                        self.application_service,
                        "outcome_engine",
                        None,
                    )
                ),
                "performance": self._availability(
                    getattr(
                        self.application_service,
                        "research_performance",
                        None,
                    )
                ),
                "portfolio": self._availability(
                    getattr(
                        self.application_service,
                        "portfolio",
                        None,
                    )
                ),
                "trading": self._availability(
                    self.trading_service
                ),
            },
        }

    def _application_status(self) -> Mapping[str, Any]:
        """Safely retrieve the application status."""

        try:
            return dict(self.application_service.status())
        except Exception as exc:
            return {
                "status": "unavailable",
                "reason": str(exc),
            }

    @staticmethod
    def _availability(component: Any) -> str:
        """Return a simple availability state for a component."""

        if component is None:
            return "not_configured"

        return "configured"
