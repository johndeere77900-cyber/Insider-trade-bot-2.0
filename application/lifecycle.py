"""
Application lifecycle coordinator.

Provides one controlled lifecycle boundary for initialization, startup,
health checking, and shutdown.
"""

from __future__ import annotations

from typing import Any, Optional

from application.health import ApplicationHealth
from application.runtime import ApplicationRuntime
from application.shutdown import ApplicationShutdown
from application.startup import ApplicationStartup


class ApplicationLifecycle:
    """Coordinates the application runtime lifecycle."""

    def __init__(
        self,
        *,
        startup: ApplicationStartup,
        runtime: ApplicationRuntime,
        health: Optional[ApplicationHealth] = None,
        shutdown: Optional[ApplicationShutdown] = None,
    ) -> None:
        if startup is None:
            raise ValueError("startup is required.")

        if runtime is None:
            raise ValueError("runtime is required.")

        self.startup = startup
        self.runtime = runtime
        self.health = health
        self.shutdown_service = shutdown or ApplicationShutdown(
            runtime=runtime
        )

    def start(self) -> ApplicationRuntime:
        """Start the application runtime."""

        self.runtime.start()
        return self.runtime

    def health_check(self) -> dict[str, Any]:
        """Run the configured health check."""

        if self.health is None:
            return {
                "status": "unknown",
                "reason": "Health service is not configured.",
            }

        return dict(self.health.check())

    def stop(self) -> None:
        """Stop the application and release registered resources."""

        self.shutdown_service.shutdown()
