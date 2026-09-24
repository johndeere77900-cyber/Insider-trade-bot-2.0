"""
Telegram application assembly for Insider Trade Bot 2.0.

This module assembles the Telegram configuration, client, adapter, service,
and polling components into one application object.

It does not implement the underlying research, trading, risk, or execution
logic.
"""

from __future__ import annotations

import logging
from typing import Any

from .adapter import TelegramAdapter
from .client import TelegramClient
from .config import TelegramSettings
from .poller import TelegramPoller
from .service import TelegramService


class TelegramApplication:
    """Fully assembled Telegram interface application."""

    def __init__(
        self,
        settings: TelegramSettings,
        application_service: Any = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.settings = settings
        self.logger = logger or logging.getLogger(
            "insider_trade_bot.telegram"
        )

        self.client = TelegramClient(
            bot_token=settings.bot_token,
            request_timeout_seconds=settings.request_timeout_seconds,
        )

        self.adapter = TelegramAdapter(
            client=self.client,
        )

        self.service = TelegramService.create(
            allowed_user_ids=settings.allowed_user_ids,
            application_service=application_service,
        )

        self.poller = TelegramPoller(
            client=self.client,
            adapter=self.adapter,
            service=self.service,
            polling_timeout_seconds=settings.polling_timeout_seconds,
            logger=self.logger,
        )

    @property
    def enabled(self) -> bool:
        """Return whether the Telegram interface is enabled."""
        return self.settings.enabled

    def verify_connection(self) -> dict[str, Any]:
        """Verify that the configured Telegram bot can reach Telegram."""
        if not self.enabled:
            raise RuntimeError(
                "Telegram interface is disabled."
            )

        return self.client.get_me()

    def start(self) -> None:
        """Start Telegram polling."""
        if not self.enabled:
            self.logger.info(
                "Telegram interface is disabled; polling will not start."
            )
            return

        self.poller.run()

    def stop(self) -> None:
        """Stop Telegram polling."""
        self.poller.stop()
