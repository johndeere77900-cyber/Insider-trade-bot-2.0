"""
Telegram request context for Insider Trade Bot 2.0.

This module carries request-scoped information through the Telegram
interface without placing Telegram-specific state inside the core agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .messages import TelegramUser


@dataclass(frozen=True)
class TelegramRequestContext:
    """Immutable context for one Telegram request."""

    user: TelegramUser
    chat_id: int
    message_id: int
    received_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.chat_id, int):
            raise TypeError("Telegram chat_id must be an integer.")

        if not isinstance(self.message_id, int):
            raise TypeError("Telegram message_id must be an integer.")

    @property
    def user_id(self) -> int:
        """Return the Telegram user's numeric ID."""
        return self.user.user_id
