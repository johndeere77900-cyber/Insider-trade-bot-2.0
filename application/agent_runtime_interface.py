from __future__ import annotations

from typing import Any, Mapping

from application.agent_runtime_manager import AgentRuntimeManagerStatus
from application.agent_runtime_service import AgentRuntimeService


class AgentRuntimeInterfaceError(RuntimeError):
    """Base error for runtime-interface operations."""


class AgentRuntimeInterface:
    """
    External-facing interface for the agent runtime.

    Higher-level interfaces such as Telegram should communicate through
    this boundary rather than reaching directly into runtime internals.
    """

    def __init__(self, service: AgentRuntimeService) -> None:
        if service is None:
            raise ValueError("service is required")

        self._service = service

    @property
    def service(self) -> AgentRuntimeService:
        return self._service

    def start(self) -> AgentRuntimeManagerStatus:
        return self._service.start()

    def stop(self) -> AgentRuntimeManagerStatus:
        return self._service.stop()

    def restart(self) -> AgentRuntimeManagerStatus:
        return self._service.restart()

    def status(self) -> AgentRuntimeManagerStatus:
        return self._service.status()

    def health(self) -> Mapping[str, Any]:
        return self._service.health()

    def is_running(self) -> bool:
        return self._service.is_running()

    def handle(self, request: Any) -> Any:
        return self._service.handle(request)
