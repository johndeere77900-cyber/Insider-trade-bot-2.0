"""
Application runtime.

Owns the assembled application facade and provides controlled startup and
shutdown state without automatically starting external interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from application.assembly import assemble_application
from application.facade import ApplicationFacade
from application.registry import ApplicationRegistry


@dataclass
class ApplicationRuntime:
    """Runtime container for the assembled application."""

    registry: ApplicationRegistry
    facade: ApplicationFacade
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    running: bool = False

    @classmethod
    def create(
        cls,
        registry: ApplicationRegistry,
    ) -> "ApplicationRuntime":
        """Create a runtime from an application registry."""

        if registry is None:
            raise ValueError("registry is required.")

        facade = assemble_application(registry)

        return cls(
            registry=registry,
            facade=facade,
        )

    def start(self) -> None:
        """Mark the application runtime as started."""

        if self.running:
            return

        self.started_at = datetime.now(timezone.utc)
        self.stopped_at = None
        self.running = True

    def stop(self) -> None:
        """Stop the application runtime."""

        if not self.running:
            return

        self.stopped_at = datetime.now(timezone.utc)
        self.running = False

    def is_running(self) -> bool:
        """Return whether the application runtime is currently running."""

        return self.running

    def status(self) -> dict[str, object]:
        """Return runtime state."""

        return {
            "running": self.running,
            "started_at": (
                self.started_at.isoformat()
                if self.started_at is not None
                else None
            ),
            "stopped_at": (
                self.stopped_at.isoformat()
                if self.stopped_at is not None
                else None
            ),
        }
