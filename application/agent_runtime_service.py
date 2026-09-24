from __future__ import annotations

from typing import Any, Mapping

from application.agent_runtime_manager import (
    AgentRuntimeManager,
    AgentRuntimeManagerStatus,
)


class AgentRuntimeServiceError(RuntimeError):
    """Base error for runtime-service operations."""


class AgentRuntimeService:
    """
    High-level service boundary for controlling the running agent runtime.

    This service delegates lifecycle and request handling to
    AgentRuntimeManager and does not contain business logic.
    """

    def __init__(self, manager: AgentRuntimeManager) -> None:
        if manager is None:
            raise ValueError("manager is required")

        self._manager = manager

    @property
    def manager(self) -> AgentRuntimeManager:
        return self._manager

    def start(self) -> AgentRuntimeManagerStatus:
        return self._manager.start()

    def stop(self) -> AgentRuntimeManagerStatus:
        return self._manager.stop()

    def restart(self) -> AgentRuntimeManagerStatus:
        self._manager.stop()
        return self._manager.start()

    def is_running(self) -> bool:
        return self._manager.is_running()

    def status(self) -> AgentRuntimeManagerStatus:
        return self._manager.status()

    def health(self) -> Mapping[str, Any]:
        return self._manager.health()

    def require_running(self) -> None:
        self._manager.require_running()

    def handle(self, request: Any) -> Any:
        self.require_running()
        return self._manager.handle(request)
