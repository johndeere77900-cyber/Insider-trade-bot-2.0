from __future__ import annotations

from typing import Any, Mapping

from application.agent_application import AgentApplication


class AgentApplicationEntrypointError(RuntimeError):
    """Base error for application entrypoint operations."""


class AgentApplicationEntrypoint:
    """
    Process-facing boundary for the complete Insider Trade Bot application.

    This class keeps process startup/shutdown separate from the underlying
    application and agent business logic.
    """

    def __init__(
        self,
        application: AgentApplication,
    ) -> None:
        if application is None:
            raise ValueError("application is required")

        self._application = application

    @property
    def application(self) -> AgentApplication:
        return self._application

    def start(self) -> Any:
        return self._application.start()

    def run(self) -> Any:
        return self._application.run()

    def stop(self) -> Any:
        return self._application.stop()

    def wait(self, timeout: float | None = None) -> bool:
        return self._application.wait(timeout)

    def status(self) -> Any:
        return self._application.status()

    def health(self) -> Any:
        return self._application.health()

    def handle(self, request: Any) -> Any:
        return self._application.handle(request)

    def metadata(self) -> Mapping[str, Any]:
        return self._application.metadata()
