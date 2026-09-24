"""
Loader for top-level Insider Trade Bot configuration.

The loader converts environment-style values into AgentConfiguration while
keeping configuration validation centralized in the configuration object.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

from application.agent_configuration import AgentConfiguration


class AgentConfigurationLoader:
    """Loads AgentConfiguration from environment variables."""

    def __init__(
        self,
        *,
        environment: Optional[Mapping[str, str]] = None,
    ) -> None:
        self._environment = (
            dict(environment)
            if environment is not None
            else dict(os.environ)
        )

    def load(self) -> AgentConfiguration:
        """Build and validate configuration from the environment."""

        configuration = AgentConfiguration(
            name=self._get(
                "INSIDER_AGENT_NAME",
                "Insider Trade Bot 2.0",
            ),
            environment=self._get(
                "APP_ENVIRONMENT",
                "development",
            ),
            enabled=self._get_bool(
                "INSIDER_AGENT_ENABLED",
                True,
            ),
            strict_mode=self._get_bool(
                "STRICT_MODE",
                True,
            ),
            paper_trading_enabled=self._get_bool(
                "PAPER_TRADING_ENABLED",
                True,
            ),
            live_trading_enabled=self._get_bool(
                "LIVE_TRADING_ENABLED",
                False,
            ),
            telegram_enabled=self._get_bool(
                "TELEGRAM_ENABLED",
                False,
            ),
        )

        configuration.validate()

        return configuration

    def _get(
        self,
        key: str,
        default: str,
    ) -> str:
        value = self._environment.get(key)

        if value is None or not value.strip():
            return default

        return value.strip()

    def _get_bool(
        self,
        key: str,
        default: bool,
    ) -> bool:
        value = self._environment.get(key)

        if value is None or not value.strip():
            return default

        normalized = value.strip().lower()

        if normalized in {"1", "true", "yes", "on", "enabled"}:
            return True

        if normalized in {"0", "false", "no", "off", "disabled"}:
            return False

        raise ValueError(
            f"Invalid boolean value for {key}: {value!r}"
      )
