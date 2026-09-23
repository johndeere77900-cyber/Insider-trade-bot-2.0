"""
Telegram request router for Insider Trade Bot 2.0.

The router maps Telegram commands to application-level handlers.
It does not contain research, trading, risk, or database business logic.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .parser import ParsedCommand


CommandHandler = Callable[[ParsedCommand, Any], Any]


@dataclass(frozen=True)
class RouteResult:
    """Result of routing a Telegram command."""

    handled: bool
    command: str
    result: Any = None
    error: str | None = None


class TelegramRouter:
    """Route parsed Telegram commands to registered handlers."""

    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}

    def register(
        self,
        command: str,
        handler: CommandHandler,
    ) -> None:
        """Register or replace a handler for a command."""
        if not isinstance(command, str):
            raise TypeError("Telegram command must be a string.")

        normalized = command.strip().lower().lstrip("/")

        if not normalized:
            raise ValueError("Telegram command cannot be empty.")

        if not normalized.replace("_", "").isalnum():
            raise ValueError(
                f"Invalid Telegram command name: {command!r}"
            )

        if not callable(handler):
            raise TypeError("Telegram command handler must be callable.")

        self._handlers[normalized] = handler

    def unregister(self, command: str) -> None:
        """Remove a registered command handler if present."""
        normalized = command.strip().lower().lstrip("/")
        self._handlers.pop(normalized, None)

    def has_handler(self, command: str) -> bool:
        """Return whether a command has a registered handler."""
        normalized = command.strip().lower().lstrip("/")
        return normalized in self._handlers

    def commands(self) -> tuple[str, ...]:
        """Return registered command names in deterministic order."""
        return tuple(sorted(self._handlers))

    def route(
        self,
        parsed_command: ParsedCommand,
        context: Any = None,
    ) -> RouteResult:
        """Route a parsed command to its registered handler."""
        command = parsed_command.name.strip().lower()

        handler = self._handlers.get(command)

        if handler is None:
            return RouteResult(
                handled=False,
                command=command,
                error=f"Unknown Telegram command: /{command}",
            )

        try:
            result = handler(parsed_command, context)

            return RouteResult(
                handled=True,
                command=command,
                result=result,
            )

        except Exception as exc:
            return RouteResult(
                handled=True,
                command=command,
                error=str(exc) or exc.__class__.__name__,
          )
