"""
Application startup coordinator.

Coordinates validation and construction of the application runtime without
automatically starting external interfaces or live trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from application.assembly import assemble_application
from application.configuration import ApplicationConfiguration
from application.registry import ApplicationRegistry
from application.runtime import ApplicationRuntime


@dataclass
class ApplicationStartup:
    """Coordinates application initialization."""

    configuration: ApplicationConfiguration

    def initialize(
        self,
        *,
        registry: ApplicationRegistry,
    ) -> ApplicationRuntime:
        """
        Validate configuration and create the application runtime.

        Initialization does not start Telegram polling, market-data polling,
        or live trading.
        """

        self.configuration.validate()

        if registry is None:
            raise ValueError("registry is required.")

        # Ensure the application facade can be assembled before runtime use.
        assemble_application(registry)

        return ApplicationRuntime.create(registry)
