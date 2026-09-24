"""
Application factory.

Creates the application service and keeps dependency assembly in one place.
"""

from __future__ import annotations

from typing import Optional

from application.service import ApplicationService
from backtesting.engine import BacktestEngine
from outcomes.engine import OutcomeEngine
from research.event_study import EventStudyEngine
from research.performance import ResearchPerformance
from signals.signal_engine import SignalEngine
from trading.portfolio import Portfolio


def create_application_service(
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
) -> ApplicationService:
    """
    Build the application service.

    Dependencies are injected rather than created implicitly. This keeps
    the application layer testable and prevents external interfaces from
    constructing domain components themselves.
    """

    return ApplicationService(
        environment=environment,
        paper_trading_enabled=paper_trading_enabled,
        live_trading_enabled=live_trading_enabled,
        historical_data_available=historical_data_available,
        event_study_engine=event_study_engine,
        signal_engine=signal_engine,
        backtest_engine=backtest_engine,
        outcome_engine=outcome_engine,
        research_performance=research_performance,
        portfolio=portfolio,
)
