"""
Application runtime manager.

Provides controlled lifecycle management for the application runtime.
"""

from __future__ import annotations

from application.runtime import ApplicationRuntime


class ApplicationRuntimeManager:
    """Controls application runtime startup and shutdown."""

    def __init__(self, runtime: ApplicationRuntime) -> None:
        if runtime is None:
            raise ValueError("runtime is required.")

        self.runtime = runtime

    def start(self) -> ApplicationRuntime:
        """Start the application runtime."""

        self.runtime.start()
        return self.runtime

    def stop(self) -> ApplicationRuntime:
        """Stop the application runtime."""

        self.runtime.stop()
        return self.runtime

    def restart(self) -> ApplicationRuntime:
        """Stop and start the application runtime."""

        self.runtime.stop()
        self.runtime.start()
        return self.runtime

    def is_running(self) -> bool:
        """Return whether the runtime is currently running."""

        return self.runtime.running
