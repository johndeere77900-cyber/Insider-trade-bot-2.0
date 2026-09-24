"""
Application service registry.

Provides a single container for application-level services so external
interfaces can access them without constructing or owning domain services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from application.service import ApplicationService
from application.trading_service import TradingService


@dataclass
class ApplicationRegistry:
    """Container for services exposed by the application."""

    application: ApplicationService
    trading: Optional[TradingService] = None

    def get_application(self) -> ApplicationService:
        """Return the primary application service."""
        return self.application

    def get_trading(self) -> TradingService:
        """
        Return the trading service.

        Raises:
            RuntimeError: if trading has not been configured.
        """
        if self.trading is None:
            raise RuntimeError("Trading service is not configured.")

        return self.trading
