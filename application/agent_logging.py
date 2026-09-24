"""
Logging boundary for the top-level Insider Trade Bot agent.

The module provides agent-specific logging without replacing the existing
application/core logging configuration.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional


LOGGER_NAME = "insider_trade_bot.agent"


class AgentLogger:
    """Small structured-context wrapper around Python logging."""

    def __init__(
        self,
        *,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._logger = logger or logging.getLogger(LOGGER_NAME)

    @property
    def logger(self) -> logging.Logger:
        """Return the underlying logger."""
        return self._logger

    def debug(
        self,
        message: str,
        *,
        context: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self._logger.debug(
            "%s | context=%s",
            message,
            dict(context or {}),
        )

    def info(
        self,
        message: str,
        *,
        context: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self._logger.info(
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
        self._logger.warning(
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
        self._logger.error(
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
        self._logger.exception(
            "%s | context=%s",
            message,
            dict(context or {}),
  )
