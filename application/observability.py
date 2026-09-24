"""
Application observability.

Provides a small interface for recording application-level operational
events without coupling the application to a specific logging backend.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional


class ApplicationObservability:
    """Application-level operational logging helper."""

    def __init__(
        self,
        *,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.logger = logger or logging.getLogger(
            "insider_trade_bot.application"
        )

    def info(
        self,
        message: str,
        *,
        context: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Record an informational application event."""

        self.logger.info(
            "%s | context=%s",
            message,
            dict(context or {}),
        )

    def warning(
        self,
        message: str,
        *,
        context: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Record a warning application event."""

        self.logger.warning(
            "%s | context=%s",
            message,
            dict(context or {}),
        )

    def error(
        self,
        message: str,
        *,
        context: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Record an application error event."""

        self.logger.error(
            "%s | context=%s",
            message,
            dict(context or {}),
        )

    def exception(
        self,
        message: str,
        *,
        context: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Record an exception with the current exception traceback."""

        self.logger.exception(
            "%s | context=%s",
            message,
            dict(context or {}),
    )
