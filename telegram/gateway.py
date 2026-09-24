"""
Telegram gateway for Insider Trade Bot 2.0.

The gateway connects the Telegram API client to the internal message
processor. It is the final Telegram-facing boundary before requests enter
the application layer.
"""

from __future__ import annotations

import logging
from typing import Any

from .adapter import TelegramAdapter, TelegramAdapterError
from .client import TelegramClient, TelegramClientError
from .context import TelegramRequestContext
from .message_processor import TelegramMessageProcessor


class TelegramGateway:
    """Receive, process, and respond to Telegram messages."""

    def __init__(
        self,
        client: TelegramClient,
        adapter: TelegramAdapter,
        processor: TelegramMessageProcessor,
        logger: logging.Logger | None = None,
    ) -> None:
        self.client = client
        self.adapter = adapter
        self.processor = processor
        self.logger = logger or logging.getLogger(
            "insider_trade_bot.telegram.gateway"
        )

    def handle_update(
        self,
        update: dict[str, Any],
    ) -> bool:
        """
        Process one raw Telegram update.

        Returns True when the update was successfully handled or safely
        ignored, and False when processing failed.
        """
        try:
            message = self.adapter.normalize_update(update)

        except TelegramAdapterError as exc:
            self.logger.error(
                "Unable to normalize Telegram update: %s",
                exc,
            )
            return False

        if message is None:
            return True

        context = TelegramRequestContext(
            user=message.user,
            chat_id=message.chat_id,
            message_id=message.message_id,
            received_at=message.received_at,
        )

        try:
            response = self.processor.process(
                message,
                context=context,
            )

            self.adapter.send_response(response)

        except TelegramClientError as exc:
            self.logger.error(
                "Unable to send Telegram response: %s",
                exc,
            )
            return False

        except Exception:
            self.logger.exception(
                "Unexpected Telegram gateway failure."
            )
            return False

        return True

    def handle_updates(
        self,
        updates: list[dict[str, Any]],
    ) -> int:
        """
        Process multiple Telegram updates.

        Returns the number of successfully handled updates.
        """
        if not isinstance(updates, list):
            raise TypeError("Telegram updates must be a list.")

        handled = 0

        for update in updates:
            if self.handle_update(update):
                handled += 1

        return handled
