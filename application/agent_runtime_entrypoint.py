from __future__ import annotations

from typing import Any, Mapping

from application.agent_runtime_bootstrap import AgentRuntimeBootstrap


class AgentRuntimeEntrypointError(RuntimeError):
    """Base error for runtime entrypoint operations."""


class AgentRuntimeEntrypoint:
    """
    Process-facing entrypoint for the assembled agent runtime.

    This class provides the final runtime boundary that can later be called
    by the application's main executable without exposing construction
    details.
    """

    def __init__(
        self,
        bootstrap: AgentRuntimeBootstrap,
    ) -> None:
        if bootstrap is None:
            raise ValueError("bootstrap is required")

        self._bootstrap = bootstrap

    @property
    def bootstrap(self) -> AgentRuntimeBootstrap:
        return self._bootstrap

    def start(self) -> Any:
        return self._bootstrap.start()

    def stop(self) -> Any:
        return self._bootstrap.stop()

    def restart(self) -> Any:
        return self._bootstrap.restart()

    def status(self) -> Any:
        return self._bootstrap.status()

    def health(self) -> Any:
        return self._bootstrap.health_check()

    def handle(self, request: Any) -> Any:
        return self._bootstrap.handle(request)

    def run(self, request: Any | None = None) -> Any:
        """
        Start the runtime and optionally process one initial request.

        This method does not create an infinite loop. Long-running process
        orchestration belongs to the final application entrypoint.
        """

        self.start()

        if request is None:
            return self.status()

        return self.handle(request)

    def metadata(self) -> Mapping[str, Any]:
        return self._bootstrap.metadata
