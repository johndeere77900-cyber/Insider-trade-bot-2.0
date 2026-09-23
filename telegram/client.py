"""
Telegram Bot API client for Insider Trade Bot 2.0.

This module handles communication with Telegram's Bot API only.
Application business logic remains outside the client.
"""

from __future__ import annotations

from typing import Any
from urllib import error, parse, request
import json


class TelegramClientError(RuntimeError):
    """Raised when communication with Telegram fails."""


class TelegramClient:
    """Minimal dependency-free Telegram Bot API client."""

    def __init__(
        self,
        bot_token: str,
        request_timeout_seconds: int = 30,
    ) -> None:
        if not bot_token or not bot_token.strip():
            raise ValueError("Telegram bot token cannot be empty.")

        if request_timeout_seconds <= 0:
            raise ValueError(
                "Telegram request timeout must be greater than zero."
            )

        self._bot_token = bot_token.strip()
        self._timeout = request_timeout_seconds
        self._base_url = (
            f"https://api.telegram.org/bot{self._bot_token}"
        )

    def get_me(self) -> dict[str, Any]:
        """Return information about the configured Telegram bot."""
        return self._request("getMe")

    def get_updates(
        self,
        offset: int | None = None,
        timeout: int = 30,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Retrieve pending Telegram updates using long polling.

        The returned value is always a list of update dictionaries.
        """
        if timeout < 0:
            raise ValueError("Telegram polling timeout cannot be negative.")

        if not 1 <= limit <= 100:
            raise ValueError("Telegram update limit must be between 1 and 100.")

        params: dict[str, Any] = {
            "timeout": timeout,
            "limit": limit,
        }

        if offset is not None:
            params["offset"] = offset

        result = self._request(
            "getUpdates",
            params=params,
            timeout_override=timeout + self._timeout,
        )

        updates = result.get("result", [])

        if not isinstance(updates, list):
            raise TelegramClientError(
                "Telegram returned an invalid update payload."
            )

        return updates

    def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> dict[str, Any]:
        """Send a text message to a Telegram chat."""
        if not isinstance(chat_id, int):
            raise TypeError("Telegram chat_id must be an integer.")

        if not text or not text.strip():
            raise ValueError("Telegram message text cannot be empty.")

        if len(text) > 4096:
            raise ValueError(
                "Telegram message exceeds the 4096-character limit."
            )

        params: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
        }

        if parse_mode:
            params["parse_mode"] = parse_mode

        if reply_to_message_id is not None:
            params["reply_parameters"] = json.dumps(
                {
                    "message_id": reply_to_message_id,
                }
            )

        return self._request(
            "sendMessage",
            params=params,
        )

    def _request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout_override: int | None = None,
    ) -> dict[str, Any]:
        """Perform a Telegram Bot API request."""
        url = f"{self._base_url}/{method}"

        encoded_params = parse.urlencode(
            params or {},
            doseq=True,
        ).encode("utf-8")

        http_request = request.Request(
            url,
            data=encoded_params,
            method="POST",
        )

        timeout = (
            timeout_override
            if timeout_override is not None
            else self._timeout
        )

        try:
            with request.urlopen(
                http_request,
                timeout=timeout,
            ) as response:
                raw_body = response.read().decode("utf-8")

        except error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                body = ""

            raise TelegramClientError(
                f"Telegram API HTTP error {exc.code}: {body}"
            ) from exc

        except error.URLError as exc:
            raise TelegramClientError(
                f"Telegram API connection failed: {exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise TelegramClientError(
                "Telegram API request timed out."
            ) from exc

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise TelegramClientError(
                "Telegram API returned invalid JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise TelegramClientError(
                "Telegram API returned an invalid response."
            )

        if payload.get("ok") is not True:
            description = payload.get(
                "description",
                "Unknown Telegram API error.",
            )

            raise TelegramClientError(
                str(description)
            )

        return payload
