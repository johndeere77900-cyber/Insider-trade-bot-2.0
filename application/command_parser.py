"""
Application command parser.

Converts simple external command payloads into normalized application
command objects.
"""

from __future__ import annotations

from typing import Any, Mapping

from application.commands import (
    ApplicationCommand,
    BacktestCommand,
    PortfolioCommand,
    ResearchCommand,
    SignalCommand,
    StatusCommand,
    TradeCommand,
)
from application.errors import ApplicationRequestError


class ApplicationCommandParser:
    """Parse interface-independent command payloads."""

    _COMMANDS = {
        "research": ResearchCommand,
        "signal": SignalCommand,
        "backtest": BacktestCommand,
        "portfolio": PortfolioCommand,
        "status": StatusCommand,
        "trade": TradeCommand,
    }

    def parse(
        self,
        name: str,
        *,
        parameters: Mapping[str, Any] | None = None,
        request_id: str | None = None,
        user_id: str | None = None,
        source: str = "unknown",
    ) -> ApplicationCommand:
        """Create a normalized command from a command name and parameters."""

        normalized_name = name.strip().lower()

        if not normalized_name:
            raise ApplicationRequestError("Command name is required.")

        command_class = self._COMMANDS.get(normalized_name)

        if command_class is None:
            raise ApplicationRequestError(
                f"Unsupported command: {normalized_name}"
            )

        payload = dict(parameters or {})

        return command_class(
            parameters=payload,
            request_id=request_id,
            user_id=user_id,
            source=source,
      )
