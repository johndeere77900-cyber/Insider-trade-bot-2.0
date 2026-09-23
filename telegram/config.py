"""
Telegram configuration for Insider Trade Bot 2.0.

Telegram credentials and access-control settings are loaded from
environment variables so secrets are not stored in source code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


class TelegramConfigurationError(ValueError):
    """Raised when required Telegram configuration is missing or invalid."""


@dataclass(frozen=True)
class TelegramSettings:
    """Immutable Telegram interface configuration."""

    bot_token: str
    allowed_user_ids: tuple[int, ...]
    enabled: bool = True
    polling_timeout_seconds: int = 30
    request_timeout_seconds: int = 30


def _parse_bool(value: str | None, default: bool) -> bool:
    """Parse a boolean environment value."""
    if value is None:
        return default

    normalized = value.strip().lower()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"0", "false", "no", "off"}:
        return False

    raise TelegramConfigurationError(
        f"Invalid boolean value: {value!r}"
    )


def _parse_user_ids(value: str | None) -> tuple[int, ...]:
    """Parse comma-separated Telegram numeric user IDs."""
    if not value:
        return ()

    user_ids: list[int] = []

    for raw_id in value.split(","):
        raw_id = raw_id.strip()

        if not raw_id:
            continue

        try:
            user_id = int(raw_id)
        except ValueError as exc:
            raise TelegramConfigurationError(
                f"Invalid Telegram user ID: {raw_id!r}"
            ) from exc

        user_ids.append(user_id)

    return tuple(dict.fromkeys(user_ids))


def load_telegram_settings() -> TelegramSettings:
    """
    Load Telegram configuration from environment variables.

    Required:
        TELEGRAM_BOT_TOKEN

    Optional:
        TELEGRAM_ALLOWED_USER_IDS
        TELEGRAM_ENABLED
        TELEGRAM_POLLING_TIMEOUT_SECONDS
        TELEGRAM_REQUEST_TIMEOUT_SECONDS
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    enabled = _parse_bool(
        os.getenv("TELEGRAM_ENABLED"),
        default=True,
    )

    if enabled and not bot_token:
        raise TelegramConfigurationError(
            "TELEGRAM_BOT_TOKEN is required when Telegram is enabled."
        )

    allowed_user_ids = _parse_user_ids(
        os.getenv("TELEGRAM_ALLOWED_USER_IDS")
    )

    try:
        polling_timeout = int(
            os.getenv("TELEGRAM_POLLING_TIMEOUT_SECONDS", "30")
        )
        request_timeout = int(
            os.getenv("TELEGRAM_REQUEST_TIMEOUT_SECONDS", "30")
        )
    except ValueError as exc:
        raise TelegramConfigurationError(
            "Telegram timeout settings must be integers."
        ) from exc

    if polling_timeout <= 0:
        raise TelegramConfigurationError(
            "TELEGRAM_POLLING_TIMEOUT_SECONDS must be greater than zero."
        )

    if request_timeout <= 0:
        raise TelegramConfigurationError(
            "TELEGRAM_REQUEST_TIMEOUT_SECONDS must be greater than zero."
        )

    return TelegramSettings(
        bot_token=bot_token,
        allowed_user_ids=allowed_user_ids,
        enabled=enabled,
        polling_timeout_seconds=polling_timeout,
        request_timeout_seconds=request_timeout,
  )
