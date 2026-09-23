"""
Telegram response formatter for Insider Trade Bot 2.0.

This module converts internal results and errors into safe, readable
Telegram responses. It does not perform business logic or trading actions.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


class TelegramFormatter:
    """Format agent results for Telegram."""

    MAX_MESSAGE_LENGTH = 4096

    def success(
        self,
        result: Any,
        title: str | None = None,
    ) -> str:
        """Format a successful agent result."""
        body = self._format_value(result)

        if title:
            body = f"{title.strip()}\n\n{body}"

        return self._limit(body)

    def error(
        self,
        message: str,
        title: str = "Error",
    ) -> str:
        """Format an error response."""
        clean_message = str(message).strip() or "An unexpected error occurred."

        return self._limit(
            f"{title}\n\n{clean_message}"
        )

    def unauthorized(self) -> str:
        """Return the standard unauthorized response."""
        return (
            "Access denied.\n\n"
            "This Telegram account is not authorized to use the bot."
        )

    def unknown_command(self, command: str) -> str:
        """Return a response for an unrecognized command."""
        normalized = command.strip()

        if not normalized.startswith("/"):
            normalized = f"/{normalized}"

        return (
            f"Unknown command: {normalized}\n\n"
            "Use /help to see the available commands."
        )

    def empty_result(self, message: str = "No result was returned.") -> str:
        """Format an empty-result response."""
        return self._limit(message.strip() or "No result was returned.")

    def _format_value(self, value: Any) -> str:
        """Convert common Python result types into readable text."""
        if value is None:
            return "No result was returned."

        if isinstance(value, str):
            return value.strip() or "No result was returned."

        if isinstance(value, bool):
            return "Yes" if value else "No"

        if isinstance(value, (int, float)):
            return str(value)

        if is_dataclass(value):
            return self._format_mapping(asdict(value))

        if isinstance(value, dict):
            return self._format_mapping(value)

        if isinstance(value, (list, tuple)):
            if not value:
                return "No results."

            return "\n".join(
                f"{index}. {self._format_value(item)}"
                for index, item in enumerate(value, start=1)
            )

        return str(value)

    def _format_mapping(self, value: dict[Any, Any]) -> str:
        """Format a mapping as simple key-value lines."""
        if not value:
            return "No data."

        lines: list[str] = []

        for key, item in value.items():
            label = self._humanize_key(str(key))
            formatted_item = self._format_value(item)

            if "\n" in formatted_item:
                lines.append(f"{label}:\n{formatted_item}")
            else:
                lines.append(f"{label}: {formatted_item}")

        return "\n".join(lines)

    @staticmethod
    def _humanize_key(key: str) -> str:
        """Convert snake_case keys into readable labels."""
        return key.replace("_", " ").strip().title()

    def _limit(self, text: str) -> str:
        """
        Limit output to Telegram's message size.

        The text is truncated rather than silently exceeding the API limit.
        """
        clean_text = text.strip()

        if len(clean_text) <= self.MAX_MESSAGE_LENGTH:
            return clean_text

        suffix = "\n\n[Response truncated.]"
        available = self.MAX_MESSAGE_LENGTH - len(suffix)

        return clean_text[:available].rstrip() + suffix
