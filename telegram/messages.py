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


@dataclass(frozen=True, init=False)
class TelegramMessage:
    """
    Normalized incoming Telegram message.

    The model supports both the current structured representation and the
    legacy constructor used by the existing application/test layer.

    Supported forms:

        TelegramMessage(
            message_id=1,
            chat_id=123,
            user=TelegramUser(user_id=123),
            text="research AAPL",
        )

    and:

        TelegramMessage(
            user_id="123456",
            chat_id="123456",
            text="research AAPL",
        )
    """

    message_id: int
    chat_id: int
    user: TelegramUser
    text: str
    received_at: datetime

    def __init__(
        self,
        *,
        message_id: int | None = None,
        chat_id: int | str,
        user: TelegramUser | None = None,
        user_id: int | str | None = None,
        text: str,
        received_at: datetime | None = None,
    ) -> None:
        if user is None and user_id is None:
            raise TypeError(
                "Either user or user_id must be provided."
            )

        if user is not None and not isinstance(
            user,
            TelegramUser,
        ):
            raise TypeError(
                "user must be a TelegramUser instance."
            )

        normalized_chat_id = int(
            chat_id
        )

        if user is None:
            normalized_user_id = int(
                user_id
            )
            user = TelegramUser(
                user_id=normalized_user_id
            )

        if message_id is None:
            message_id = 0

        if not isinstance(
            message_id,
            int,
        ):
            raise TypeError(
                "Telegram message_id must be an integer."
            )

        if not isinstance(
            text,
            str,
        ):
            raise TypeError(
                "Telegram message text must be a string."
            )

        if not text.strip():
            raise ValueError(
                "Telegram message text cannot be empty."
            )

        if received_at is None:
            received_at = datetime.now(
                timezone.utc
            )

        object.__setattr__(
            self,
            "message_id",
            message_id,
        )

        object.__setattr__(
            self,
            "chat_id",
            normalized_chat_id,
        )

        object.__setattr__(
            self,
            "user",
            user,
        )

        object.__setattr__(
            self,
            "text",
            text,
        )

        object.__setattr__(
            self,
            "received_at",
            received_at,
        )

    @property
    def user_id(self) -> str:
        """
        Return the Telegram user ID as a string for compatibility with
        the command/authentication layer.
        """

        return str(
            self.user.user_id
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
            raise ValueError(
                "Telegram response text cannot be empty."
            )

        if not isinstance(
            self.chat_id,
            int,
        ):
            raise TypeError(
                "Telegram chat_id must be an integer."
            )
