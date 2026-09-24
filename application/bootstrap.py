"""
Application bootstrap.

Centralizes creation of the application's service registry without starting
Telegram, trading, or other external interfaces automatically.
"""

from __future__ import annotations

from typing import Any, Optional

from application.factory import create_application_service
from application.registry import ApplicationRegistry
from application.trading_service import TradingService


def bootstrap_application(
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
    portfolio: Any = None,
    execution_service: Any = None,
) -> ApplicationRegistry:
    """
    Build the application's service registry.

    No external network polling, live trading, or Telegram startup occurs
    here. This function only assembles dependencies.
    """

    application_service = create_application_service(
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

    trading_service: Optional[TradingService] = None

    if execution_service is not None:
        trading_service = TradingService(
            execution_service=execution_service,
            paper_trading_enabled=paper_trading_enabled,
            live_trading_enabled=live_trading_enabled,
        )

    return ApplicationRegistry(
        application=application_service,
        trading=trading_service,
  )
