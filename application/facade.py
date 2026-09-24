"""
Application facade.

Provides a compact public interface for external entry points while keeping
command parsing, routing, and execution behind the application layer.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from application.context import ApplicationContext
from application.controller import ApplicationController
from application.result import ApplicationResult


class ApplicationFacade:
    """Primary interface for external callers."""

    def __init__(self, controller: ApplicationController) -> None:
        if controller is None:
            raise ValueError("controller is required.")

        self.controller = controller

    def handle(
        self,
        command: str,
        *,
        parameters: Optional[Mapping[str, Any]] = None,
        context: Optional[ApplicationContext] = None,
    ) -> ApplicationResult:
        """Handle a normalized application command."""

        return self.controller.handle(
            command=command,
            parameters=parameters,
            context=context,
        )

    def status(
        self,
        *,
        context: Optional[ApplicationContext] = None,
    ) -> ApplicationResult:
        """Return application status."""

        return self.handle(
            "status",
            context=context,
        )

    def research(
        self,
        *,
        parameters: Optional[Mapping[str, Any]] = None,
        context: Optional[ApplicationContext] = None,
    ) -> ApplicationResult:
        """Submit a research request."""

        return self.handle(
            "research",
            parameters=parameters,
            context=context,
        )

    def signal(
        self,
        *,
        parameters: Optional[Mapping[str, Any]] = None,
        context: Optional[ApplicationContext] = None,
    ) -> ApplicationResult:
        """Submit a signal-generation request."""

        return self.handle(
            "signal",
            parameters=parameters,
            context=context,
        )

    def backtest(
        self,
        *,
        parameters: Optional[Mapping[str, Any]] = None,
        context: Optional[ApplicationContext] = None,
    ) -> ApplicationResult:
        """Submit a backtesting request."""

        return self.handle(
            "backtest",
            parameters=parameters,
            context=context,
        )

    def portfolio(
        self,
        *,
        context: Optional[ApplicationContext] = None,
    ) -> ApplicationResult:
        """Request portfolio status."""

        return self.handle(
            "portfolio",
            context=context,
    )
