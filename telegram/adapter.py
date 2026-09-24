"""
Telegram update adapter for Insider Trade Bot 2.0.

This module converts raw Telegram Bot API updates into the internal
TelegramMessage model and sends normalized Telegram responses back through
the Telegram client.

It does not contain research, trading, risk, or execution logic.
"""

from __future__ import annotations

from typing import Any

from .client import TelegramClient
from .messages import TelegramMessage, TelegramResponse, TelegramUser


class TelegramAdapterError(RuntimeError):
    """Raised when a Telegram update cannot be normalized."""


class TelegramAdapter:
    """Translate between Telegram API payloads and internal models."""

    def __init__(self, client: TelegramClient) -> None:
        self.client = client

    def normalize_update(
        self,
        update: dict[str, Any],
    ) -> TelegramMessage | None:
        """
        Convert a Telegram update into a TelegramMessage.

        Updates that do not contain a normal text message are ignored by
        returning None.
        """
        if not isinstance(update, dict):
            raise TelegramAdapterError(
                "Telegram update must be a dictionary."
            )

        message = update.get("message")

        if not isinstance(message, dict):
            return None

        message_id = message.get("message_id")
        chat = message.get("chat")
        user = message.get("from")
        text = message.get("text")

        if not isinstance(message_id, int):
            raise TelegramAdapterError(
                "Telegram message ID is missing or invalid."
            )

        if not isinstance(chat, dict):
            raise TelegramAdapterError(
                "Telegram chat information is missing."
            )

        chat_id = chat.get("id")

        if not isinstance(chat_id, int):
            raise TelegramAdapterError(
                "Telegram chat ID is missing or invalid."
            )

        if not isinstance(user, dict):
            raise TelegramAdapterError(
                "Telegram user information is missing."
            )

        user_id = user.get("id")

        if not isinstance(user_id, int):
            raise TelegramAdapterError(
                "Telegram user ID is missing or invalid."
            )

        if not isinstance(text, str):
            return None

        telegram_user = TelegramUser(
            user_id=user_id,
            username=self._optional_string(user.get("username")),
            first_name=self._optional_string(user.get("first_name")),
            last_name=self._optional_string(user.get("last_name")),
        )

        return TelegramMessage(
            message_id=message_id,
            chat_id=chat_id,
            user=telegram_user,
            text=text,
        )

    def send_response(
        self,
        response: TelegramResponse,
    ) -> dict[str, Any]:
        """Send a normalized Telegram response."""
        return self.client.send_message(
            chat_id=response.chat_id,
            text=response.text,
            parse_mode=response.parse_mode,
            reply_to_message_id=response.reply_to_message_id,
        )

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        """Return a cleaned optional string."""
        if value is None:
            return None

        if not isinstance(value, str):
            return str(value)

        value = value.strip()

        return value or None
