"""
Application entrypoint coordinator.

Provides the final application-level callable that a future CLI, service
launcher, or main.py can use without knowing the internal assembly details.
"""

from __future__ import annotations

from typing import Any, Optional

from application.configuration import ApplicationConfiguration
from application.lifecycle import ApplicationLifecycle
from application.registry import ApplicationRegistry
from application.runtime import ApplicationRuntime
from application.startup import ApplicationStartup


class ApplicationEntrypoint:
    """High-level entrypoint for Insider Trade Bot 2.0."""

    def __init__(
        self,
        *,
        configuration: ApplicationConfiguration,
        registry: ApplicationRegistry,
        health_service: Optional[Any] = None,
        shutdown_service: Optional[Any] = None,
    ) -> None:
        if configuration is None:
            raise ValueError("configuration is required.")

        if registry is None:
            raise ValueError("registry is required.")

        startup = ApplicationStartup(
            configuration=configuration,
        )

        runtime = startup.initialize(
            registry=registry,
        )

        self.lifecycle = ApplicationLifecycle(
            startup=startup,
            runtime=runtime,
            health=health_service,
            shutdown=shutdown_service,
        )

    @property
    def runtime(self) -> ApplicationRuntime:
        """Return the application runtime."""

        return self.lifecycle.runtime

    def start(self) -> None:
        """Start the application runtime."""

        self.lifecycle.start()

    def stop(self) -> None:
        """Stop the application runtime."""

        self.lifecycle.stop()

    def health(self) -> dict[str, Any]:
        """Return application health information."""

        return self.lifecycle.health_check()
