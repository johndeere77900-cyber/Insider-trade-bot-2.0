from __future__ import annotations

from typing import Any, Mapping

from application.agent_runtime_application import AgentRuntimeApplication


class AgentApplicationError(RuntimeError):
    """Base error for the top-level agent application."""


class AgentApplication:
    """
    Final application-facing wrapper around the assembled runtime.

    This layer deliberately contains no trading, research, ingestion, or
    strategy logic. It exposes the runtime as a single application boundary.
    """

    def __init__(self, runtime: AgentRuntimeApplication) -> None:
        if runtime is None:
            raise ValueError("runtime is required")

        self._runtime = runtime

    @property
    def runtime(self) -> AgentRuntimeApplication:
        return self._runtime

    def start(self) -> Any:
        return self._runtime.start()

    def run(self) -> Any:
        return self._runtime.run()

    def stop(self) -> Any:
        return self._runtime.stop()

    def wait(self, timeout: float | None = None) -> bool:
        return self._runtime.wait(timeout)

    def status(self) -> Any:
        return self._runtime.status()

    def health(self) -> Any:
        return self._runtime.health()

    def handle(self, request: Any) -> Any:
        return self._runtime.handle(request)

    def metadata(self) -> Mapping[str, Any]:
        return self._runtime.metadata()
