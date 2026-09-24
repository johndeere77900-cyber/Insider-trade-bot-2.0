"""
Application shutdown coordinator.

Provides controlled shutdown of application resources without forcing
external components to implement a particular interface.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from application.runtime import ApplicationRuntime


class ApplicationShutdown:
    """Coordinates application shutdown."""

    def __init__(
        self,
        *,
        runtime: ApplicationRuntime,
        resources: Optional[Iterable[Any]] = None,
    ) -> None:
        if runtime is None:
            raise ValueError("runtime is required.")

        self.runtime = runtime
        self.resources = list(resources or [])

    def shutdown(self) -> None:
        """Stop the runtime and close registered resources."""

        errors: list[str] = []

        try:
            self.runtime.stop()
        except Exception as exc:
            errors.append(f"runtime: {exc}")

        for resource in self.resources:
            try:
                self._close_resource(resource)
            except Exception as exc:
                errors.append(f"resource: {exc}")

        if errors:
            raise RuntimeError(
                "Application shutdown completed with errors: "
                + "; ".join(errors)
            )

    @staticmethod
    def _close_resource(resource: Any) -> None:
        """Close a resource using a supported lifecycle method."""

        if resource is None:
            return

        if hasattr(resource, "close"):
            resource.close()
            return

        if hasattr(resource, "shutdown"):
            resource.shutdown()
            return

        if hasattr(resource, "stop"):
            resource.stop()
            return
