"""
Application-level service layer.

Provides one internal interface for Telegram and other external interfaces
to access the agent's core capabilities without duplicating business logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from backtesting.engine import run_backtest
from outcomes.engine import evaluate_signal
from research.performance import summarize_outcomes
from research.research.event_study import run_event_study
from signals.signal_engine import create_signal_batch
from trading.portfolio import Portfolio


@dataclass(frozen=True)
class ApplicationStatus:
    """Current high-level application status."""

    name: str
    environment: str
    paper_trading_enabled: bool
    live_trading_enabled: bool
    historical_data_available: bool
    status: str = "operational"


class ApplicationService:
    """
    Unified application service.

    This class coordinates the actual function-based domain components.
    It does not directly execute live trades.
    """

    def __init__(
        self,
        *,
        environment: str = "development",
        paper_trading_enabled: bool = True,
        live_trading_enabled: bool = False,
        historical_data_available: bool = False,
        event_study_engine: Any = None,
        signal_engine: Any = None,
        backtest_engine: Any = None,
        outcome_engine: Any = None,
        research_performance: Any = None,
        portfolio: Optional[Portfolio] = None,
    ) -> None:
        self.environment = environment
        self.paper_trading_enabled = paper_trading_enabled
        self.live_trading_enabled = live_trading_enabled
        self.historical_data_available = historical_data_available

        self.event_study_engine = (
            event_study_engine
            if event_study_engine is not None
            else run_event_study
        )

        self.signal_engine = (
            signal_engine
            if signal_engine is not None
            else create_signal_batch
        )

        self.backtest_engine = (
            backtest_engine
            if backtest_engine is not None
            else run_backtest
        )

        self.outcome_engine = (
            outcome_engine
            if outcome_engine is not None
            else evaluate_signal
        )

        self.research_performance = (
            research_performance
            if research_performance is not None
            else summarize_outcomes
        )

        self.portfolio = portfolio

    def status(self) -> Mapping[str, Any]:
        """Return a safe high-level application status."""

        return ApplicationStatus(
            name="Insider Trade Bot 2.0",
            environment=self.environment,
            paper_trading_enabled=self.paper_trading_enabled,
            live_trading_enabled=self.live_trading_enabled,
            historical_data_available=self.historical_data_available,
        ).__dict__.copy()

    def research(
        self,
        *,
        events: Optional[Sequence[Mapping[str, Any]]] = None,
        **kwargs: Any,
    ) -> Mapping[str, Any]:
        """
        Run an event-study research request.

        The underlying research function is called only when a research
        request is explicitly made.
        """

        if events is None:
            events = []

        try:
            result = self.event_study_engine(
                events=events,
                **kwargs,
            )
        except TypeError:
            result = self.event_study_engine(
                events,
                **kwargs,
            )

        return {
            "status": "completed",
            "result": result,
        }

    def signal(
        self,
        *,
        transactions: Optional[Sequence[Mapping[str, Any]]] = None,
        **kwargs: Any,
    ) -> Mapping[str, Any]:
        """Generate signals through the configured signal component."""

        if transactions is None:
            transactions = []

        try:
            result = self.signal_engine(
                transactions=transactions,
                **kwargs,
            )
        except TypeError:
            result = self.signal_engine(
                transactions,
                **kwargs,
            )

        return {
            "status": "completed",
            "result": result,
        }

    def backtest(
        self,
        *,
        signals: Optional[Sequence[Mapping[str, Any]]] = None,
        **kwargs: Any,
    ) -> Mapping[str, Any]:
        """Run a backtest through the configured backtesting function."""

        if signals is None:
            signals = []

        try:
            result = self.backtest_engine(
                signals=signals,
                **kwargs,
            )
        except TypeError:
            result = self.backtest_engine(
                signals,
                **kwargs,
            )

        return {
            "status": "completed",
            "result": result,
        }

    def portfolio_status(self) -> Mapping[str, Any]:
        """Return the current portfolio state when connected."""

        if self.portfolio is None:
            return {
                "status": "unavailable",
                "reason": "Portfolio service is not connected.",
            }

        if hasattr(self.portfolio, "snapshot"):
            result = self.portfolio.snapshot()
        elif hasattr(self.portfolio, "to_dict"):
            result = self.portfolio.to_dict()
        else:
            result = {
                "portfolio": repr(self.portfolio),
            }

        return {
            "status": "available",
            "result": result,
        }

    def outcomes(
        self,
        *,
        records: Optional[Sequence[Mapping[str, Any]]] = None,
        **kwargs: Any,
    ) -> Mapping[str, Any]:
        """Process outcome records through the outcome component."""

        if records is None:
            records = []

        try:
            result = self.outcome_engine(
                records=records,
                **kwargs,
            )
        except TypeError:
            result = self.outcome_engine(
                records,
                **kwargs,
            )

        return {
            "status": "completed",
            "result": result,
        }

    def performance(
        self,
        *,
        records: Optional[Sequence[Mapping[str, Any]]] = None,
        **kwargs: Any,
    ) -> Mapping[str, Any]:
        """Calculate research performance."""

        if records is None:
            records = []

        try:
            result = self.research_performance(
                records=records,
                **kwargs,
            )
        except TypeError:
            result = self.research_performance(
                records,
                **kwargs,
            )

        return {
            "status": "completed",
            "result": result,
    }
