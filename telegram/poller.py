"""
Telegram long-polling loop for Insider Trade Bot 2.0.

This module receives Telegram updates, passes them through the Telegram
service layer, and sends responses back to Telegram.

It does not contain business logic.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .adapter import TelegramAdapter, TelegramAdapterError
from .client import TelegramClient, TelegramClientError
from .service import TelegramService


class TelegramPoller:
    """Run the Telegram update-processing loop."""

    def __init__(
        self,
        client: TelegramClient,
        adapter: TelegramAdapter,
        service: TelegramService,
        polling_timeout_seconds: int = 30,
        logger: logging.Logger | None = None,
        retry_delay_seconds: int = 5,
    ) -> None:
        if polling_timeout_seconds <= 0:
            raise ValueError(
                "Telegram polling timeout must be greater than zero."
            )

        if retry_delay_seconds < 0:
            raise ValueError(
                "Telegram retry delay cannot be negative."
            )

        self.client = client
        self.adapter = adapter
        self.service = service
        self.polling_timeout_seconds = polling_timeout_seconds
        self.retry_delay_seconds = retry_delay_seconds
        self.logger = logger or logging.getLogger(
            "insider_trade_bot.telegram.poller"
        )

        self._running = False
        self._offset: int | None = None

    @property
    def running(self) -> bool:
        """Return whether the polling loop is active."""
        return self._running

    @property
    def offset(self) -> int | None:
        """Return the next Telegram update offset."""
        return self._offset

    def stop(self) -> None:
        """Request that the polling loop stop."""
        self._running = False

    def run(self) -> None:
        """
        Start the Telegram long-polling loop.

        The loop continues until stop() is called or an external exception
        terminates the process.
        """
        if self._running:
            return

        self._running = True

        self.logger.info("Telegram polling started.")

        try:
            while self._running:
                try:
                    updates = self.client.get_updates(
                        offset=self._offset,
                        timeout=self.polling_timeout_seconds,
                    )

                    self._process_updates(updates)

                except TelegramClientError as exc:
                    self.logger.error(
                        "Telegram API error: %s",
                        exc,
                    )

                    if self._running and self.retry_delay_seconds:
                        time.sleep(self.retry_delay_seconds)

                except Exception:
                    self.logger.exception(
                        "Unexpected Telegram polling error."
                    )

                    if self._running and self.retry_delay_seconds:
                        time.sleep(self.retry_delay_seconds)

        finally:
            self._running = False
            self.logger.info("Telegram polling stopped.")

    def process_updates(
        self,
        updates: list[dict[str, Any]],
    ) -> None:
        """
        Process a supplied update list.

        This public method is useful for controlled execution and integrated
        testing without starting an infinite polling loop.
        """
        self._process_updates(updates)

    def _process_updates(
        self,
        updates: list[dict[str, Any]],
    ) -> None:
        """Process a batch of Telegram updates."""
        if not isinstance(updates, list):
            raise TypeError("Telegram updates must be provided as a list.")

        for update in updates:
            self._process_update(update)

    def _process_update(
        self,
        update: dict[str, Any],
    ) -> None:
        """Process one Telegram update."""
        update_id = update.get("update_id")

        try:
            message = self.adapter.normalize_update(update)

        except TelegramAdapterError as exc:
            self.logger.error(
                "Invalid Telegram update: %s",
                exc,
            )
            self._advance_offset(update_id)
            return

        if message is None:
            self._advance_offset(update_id)
            return

        try:
            result = self.service.process(message)

            self.adapter.send_response(result.response)

        except TelegramClientError:
            self.logger.exception(
                "Failed to send Telegram response."
            )

        except Exception:
            self.logger.exception(
                "Failed to process Telegram message."
            )

        finally:
            self._advance_offset(update_id)

    def _advance_offset(
        self,
        update_id: Any,
    ) -> None:
        """Advance the polling offset after an update has been handled."""
        if not isinstance(update_id, int):
            return

        next_offset = update_id + 1

        if self._offset is None or next_offset > self._offset:
            self._offset = next_offset
