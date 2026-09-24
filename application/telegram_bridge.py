"""
Telegram application bridge.

Connects the existing Telegram interface to the application facade without
duplicating research, signal, backtest, portfolio, or trading business logic.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from application.context import ApplicationContext
from application.facade import ApplicationFacade
from application.result import ApplicationResult


class TelegramApplicationBridge:
    """Bridge between Telegram requests and the application layer."""

    def __init__(self, facade: ApplicationFacade) -> None:
        if facade is None:
            raise ValueError("facade is required.")

        self.facade = facade

    def handle(
        self,
        *,
        command: str,
        parameters: Optional[Mapping[str, Any]] = None,
        request_id: str,
        user_id: Optional[str],
    ) -> ApplicationResult:
        """Handle a Telegram-originated application request."""

        context = ApplicationContext(
            request_id=request_id,
            source="telegram",
            user_id=user_id,
            metadata={
                "interface": "telegram",
            },
        )

        return self.facade.handle(
            command,
            parameters=parameters,
            context=context,
        )

    def status(
        self,
        *,
        request_id: str,
        user_id: Optional[str],
    ) -> ApplicationResult:
        """Retrieve application status through Telegram."""

        return self.handle(
            command="status",
            request_id=request_id,
            user_id=user_id,
        )

    def research(
        self,
        *,
        parameters: Optional[Mapping[str, Any]],
        request_id: str,
        user_id: Optional[str],
    ) -> ApplicationResult:
        """Submit a Telegram research request."""

        return self.handle(
            command="research",
            parameters=parameters,
            request_id=request_id,
            user_id=user_id,
        )

    def signal(
        self,
        *,
        parameters: Optional[Mapping[str, Any]],
        request_id: str,
        user_id: Optional[str],
    ) -> ApplicationResult:
        """Submit a Telegram signal request."""

        return self.handle(
            command="signal",
            parameters=parameters,
            request_id=request_id,
            user_id=user_id,
        )

    def backtest(
        self,
        *,
        parameters: Optional[Mapping[str, Any]],
        request_id: str,
        user_id: Optional[str],
    ) -> ApplicationResult:
        """Submit a Telegram backtesting request."""

        return self.handle(
            command="backtest",
            parameters=parameters,
            request_id=request_id,
            user_id=user_id,
        )

    def portfolio(
        self,
        *,
        request_id: str,
        user_id: Optional[str],
    ) -> ApplicationResult:
        """Request portfolio status through Telegram."""

        return self.handle(
            command="portfolio",
            request_id=request_id,
            user_id=user_id,
      )
