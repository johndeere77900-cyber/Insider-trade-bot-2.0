"""
Telegram-specific error types for Insider Trade Bot 2.0.

These exceptions provide clear boundaries between Telegram interface
failures and the underlying agent's business logic.
"""

from __future__ import annotations


class TelegramError(RuntimeError):
    """Base exception for Telegram interface failures."""


class TelegramAuthenticationError(TelegramError):
    """Raised when Telegram authentication or authorization fails."""


class TelegramConfigurationError(TelegramError):
    """Raised when Telegram configuration is invalid."""


class TelegramParsingError(TelegramError):
    """Raised when an incoming Telegram message cannot be parsed."""


class TelegramRoutingError(TelegramError):
    """Raised when a Telegram request cannot be routed."""


class TelegramTransportError(TelegramError):
    """Raised when communication with Telegram fails."""


class TelegramResponseError(TelegramError):
    """Raised when a Telegram response cannot be delivered."""
