"""
Telegram command parser for Insider Trade Bot 2.0.

This module only interprets the Telegram message format.
It does not execute research, trading, database, or other business logic.
"""

from __future__ import annotations

from dataclasses import dataclass
import shlex


@dataclass(frozen=True)
class ParsedCommand:
    """Normalized command extracted from a Telegram message."""

    name: str
    arguments: tuple[str, ...]
    raw_text: str

    @property
    def argument_text(self) -> str:
        """Return the arguments as a single string."""
        return " ".join(self.arguments)


class TelegramCommandParser:
    """Parse Telegram commands and ordinary natural-language messages."""

    def parse(self, text: str) -> ParsedCommand:
        """
        Parse a Telegram message.

        Supported command syntax:
            /start
            /help
            /status
            /research AAPL
            /signal AAPL
            /backtest AAPL
            /portfolio

        Ordinary text is returned as the special command ``message``.
        """
        if text is None:
            raise ValueError("Telegram message text cannot be None.")

        raw_text = text.strip()

        if not raw_text:
            raise ValueError("Telegram message text cannot be empty.")

        if not raw_text.startswith("/"):
            return ParsedCommand(
                name="message",
                arguments=(raw_text,),
                raw_text=raw_text,
            )

        try:
            tokens = shlex.split(raw_text)
        except ValueError as exc:
            raise ValueError(
                "Telegram command contains invalid quoting."
            ) from exc

        if not tokens:
            raise ValueError("Telegram command cannot be empty.")

        command_token = tokens[0][1:]

        if not command_token:
            raise ValueError("Telegram command name cannot be empty.")

        # Telegram may send commands with a bot username suffix:
        # /status@MyBot
        command_name = command_token.split("@", 1)[0].lower()

        if not command_name.replace("_", "").isalnum():
            raise ValueError(
                f"Invalid Telegram command name: {command_name!r}"
            )

        return ParsedCommand(
            name=command_name,
            arguments=tuple(tokens[1:]),
            raw_text=raw_text,
      )
