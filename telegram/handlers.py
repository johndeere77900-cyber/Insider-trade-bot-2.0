"""
Telegram command handlers for Insider Trade Bot 2.0.

Handlers translate Telegram commands into calls to an injected application
service. They do not contain research, trading, risk, database, or execution
business logic themselves.
"""

from __future__ import annotations

from typing import Any, Callable

from .formatter import TelegramFormatter
from .parser import ParsedCommand


ServiceCallable = Callable[..., Any]


class TelegramHandlers:
    """Application-facing Telegram command handlers."""

    def __init__(
        self,
        formatter: TelegramFormatter | None = None,
        service: Any = None,
    ) -> None:
        self.formatter = formatter or TelegramFormatter()
        self.service = service

    def start(
        self,
        command: ParsedCommand,
        context: Any = None,
    ) -> str:
        """Handle /start."""
        return (
            "Insider Trade Bot 2.0\n\n"
            "Telegram interface is connected.\n"
            "Use /help to see available commands."
        )

    def help(
        self,
        command: ParsedCommand,
        context: Any = None,
    ) -> str:
        """Handle /help."""
        return (
            "Available commands:\n\n"
            "/start — Start the bot\n"
            "/help — Show available commands\n"
            "/status — Show system status\n"
            "/research <query> — Run an authorized research request\n"
            "/signal <symbol> — Request signal information\n"
            "/backtest <symbol> — Request backtest information\n"
            "/portfolio — Show portfolio information\n"
        )

    def status(
        self,
        command: ParsedCommand,
        context: Any = None,
    ) -> str:
        """Handle /status."""
        result = self._call_service(
            "status",
            command=command,
            context=context,
        )

        if result is None:
            return (
                "System status\n\n"
                "Telegram interface is operational.\n"
                "Application service status is not yet connected."
            )

        return self.formatter.success(
            result,
            title="System status",
        )

    def research(
        self,
        command: ParsedCommand,
        context: Any = None,
    ) -> str:
        """Handle /research."""
        if not command.arguments:
            return (
                "Usage:\n"
                "/research <query>"
            )

        query = command.argument_text

        result = self._call_service(
            "research",
            query=query,
            command=command,
            context=context,
        )

        if result is None:
            return self.formatter.success(
                {
                    "request": query,
                    "status": "accepted",
                    "message": (
                        "Research service is not yet connected."
                    ),
                },
                title="Research",
            )

        return self.formatter.success(
            result,
            title="Research",
        )

    def signal(
        self,
        command: ParsedCommand,
        context: Any = None,
    ) -> str:
        """Handle /signal."""
        if not command.arguments:
            return (
                "Usage:\n"
                "/signal <symbol>"
            )

        symbol = command.arguments[0].upper()

        result = self._call_service(
            "signal",
            symbol=symbol,
            command=command,
            context=context,
        )

        if result is None:
            return self.formatter.success(
                {
                    "symbol": symbol,
                    "status": "not_connected",
                    "message": (
                        "Signal service is not yet connected."
                    ),
                },
                title="Signal",
            )

        return self.formatter.success(
            result,
            title=f"Signal — {symbol}",
        )

    def backtest(
        self,
        command: ParsedCommand,
        context: Any = None,
    ) -> str:
        """Handle /backtest."""
        if not command.arguments:
            return (
                "Usage:\n"
                "/backtest <symbol>"
            )

        symbol = command.arguments[0].upper()

        result = self._call_service(
            "backtest",
            symbol=symbol,
            command=command,
            context=context,
        )

        if result is None:
            return self.formatter.success(
                {
                    "symbol": symbol,
                    "status": "not_connected",
                    "message": (
                        "Backtesting service is not yet connected."
                    ),
                },
                title="Backtest",
            )

        return self.formatter.success(
            result,
            title=f"Backtest — {symbol}",
        )

    def portfolio(
        self,
        command: ParsedCommand,
        context: Any = None,
    ) -> str:
        """Handle /portfolio."""
        result = self._call_service(
            "portfolio",
            command=command,
            context=context,
        )

        if result is None:
            return self.formatter.success(
                {
                    "status": "not_connected",
                    "message": (
                        "Portfolio service is not yet connected."
                    ),
                },
                title="Portfolio",
            )

        return self.formatter.success(
            result,
            title="Portfolio",
        )

    def _call_service(
        self,
        method_name: str,
        **kwargs: Any,
    ) -> Any:
        """
        Call an application service method if one has been injected.

        Returning None when no service is connected keeps the Telegram layer
        usable during assembly without inventing business behavior.
        """
        if self.service is None:
            return None

        method = getattr(self.service, method_name, None)

        if method is None or not callable(method):
            return None

        return method(**kwargs)
