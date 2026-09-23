"""
Telegram message models for Insider Trade Bot 2.0.

These models keep Telegram-specific message data separate from the agent's
core business logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class TelegramUser:
    """Normalized Telegram user information."""

    user_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


@dataclass(frozen=True)
class TelegramMessage:
    """Normalized incoming Telegram message."""

    message_id: int
    chat_id: int
    user: TelegramUser
    text: str
    received_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def command_text(self) -> str:
        """Return normalized message text."""
        return self.text.strip()


@dataclass(frozen=True)
class TelegramResponse:
    """Normalized response that can be sent back through Telegram."""

    text: str
    chat_id: int
    parse_mode: str | None = None
    reply_to_message_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Telegram response text cannot be empty.")

        if not isinstance(self.chat_id, int):
            raise TypeError("Telegram chat_id must be an integer.")
