"""
Application-level service layer.

Provides one internal interface for Telegram and other external interfaces
to access the agent's core capabilities without duplicating business logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from backtesting.engine import BacktestEngine
from outcomes.engine import OutcomeEngine
from research.event_study import EventStudyEngine
from research.performance import ResearchPerformance
from signals.signal_engine import SignalEngine
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

    This class coordinates existing domain components. It does not replace
    their business logic and does not directly execute live trades.
    """

    def __init__(
        self,
        *,
        environment: str = "development",
        paper_trading_enabled: bool = True,
        live_trading_enabled: bool = False,
        historical_data_available: bool = False,
        event_study_engine: Optional[EventStudyEngine] = None,
        signal_engine: Optional[SignalEngine] = None,
        backtest_engine: Optional[BacktestEngine] = None,
        outcome_engine: Optional[OutcomeEngine] = None,
        research_performance: Optional[ResearchPerformance] = None,
        portfolio: Optional[Portfolio] = None,
    ) -> None:
        self.environment = environment
        self.paper_trading_enabled = paper_trading_enabled
        self.live_trading_enabled = live_trading_enabled
        self.historical_data_available = historical_data_available

        self.event_study_engine = event_study_engine
        self.signal_engine = signal_engine
        self.backtest_engine = backtest_engine
        self.outcome_engine = outcome_engine
        self.research_performance = research_performance
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
        Run an event-study research request through the configured engine.

        The method intentionally fails clearly when the required engine has
        not yet been connected.
        """

        if self.event_study_engine is None:
            return {
                "status": "unavailable",
                "reason": "Research engine is not connected.",
            }

        if events is None:
            events = []

        result = self.event_study_engine.run(
            events=events,
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
        """Generate signals through the configured signal engine."""

        if self.signal_engine is None:
            return {
                "status": "unavailable",
                "reason": "Signal engine is not connected.",
            }

        if transactions is None:
            transactions = []

        result = self.signal_engine.generate(
            transactions=transactions,
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
        """Run a backtest through the configured backtesting engine."""

        if self.backtest_engine is None:
            return {
                "status": "unavailable",
                "reason": "Backtesting engine is not connected.",
            }

        if signals is None:
            signals = []

        result = self.backtest_engine.run(
            signals=signals,
            **kwargs,
        )

        return {
            "status": "completed",
            "result": result,
        }

    def portfolio_status(self) -> Mapping[str, Any]:
        """Return the current portfolio state when a portfolio is connected."""

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
        """Process outcome records through the configured outcome engine."""

        if self.outcome_engine is None:
            return {
                "status": "unavailable",
                "reason": "Outcome engine is not connected.",
            }

        if records is None:
            records = []

        result = self.outcome_engine.process(
            records=records,
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
        """Calculate research performance through the performance component."""

        if self.research_performance is None:
            return {
                "status": "unavailable",
                "reason": "Research performance component is not connected.",
            }

        if records is None:
            records = []

        if hasattr(self.research_performance, "calculate"):
            result = self.research_performance.calculate(
                records=records,
                **kwargs,
            )
        elif hasattr(self.research_performance, "evaluate"):
            result = self.research_performance.evaluate(
                records=records,
                **kwargs,
            )
        else:
            return {
                "status": "unavailable",
                "reason": "Research performance component has no supported calculation method.",
            }

        return {
            "status": "completed",
            "result": result,
  }
