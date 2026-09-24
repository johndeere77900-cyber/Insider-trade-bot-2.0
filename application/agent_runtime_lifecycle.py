from __future__ import annotations

from application.agent_runtime_health import (
    AgentRuntimeHealth,
    AgentRuntimeHealthReport,
)
from application.agent_runtime_manager import AgentRuntimeManagerStatus
from application.agent_runtime_service import AgentRuntimeService


class AgentRuntimeLifecycleError(RuntimeError):
    """Base error for runtime lifecycle operations."""


class AgentRuntimeLifecycle:
    """
    Coordinates runtime startup, shutdown, and health verification.

    This component owns lifecycle orchestration only. It does not contain
    trading, research, data-ingestion, or strategy logic.
    """

    def __init__(
        self,
        service: AgentRuntimeService,
        health: AgentRuntimeHealth,
    ) -> None:
        if service is None:
            raise ValueError("service is required")

        if health is None:
            raise ValueError("health is required")

        self._service = service
        self._health = health

    @property
    def service(self) -> AgentRuntimeService:
        return self._service

    @property
    def health(self) -> AgentRuntimeHealth:
        return self._health

    def start(self) -> AgentRuntimeHealthReport:
        self._service.start()
        return self._health.require_healthy()

    def stop(self) -> AgentRuntimeManagerStatus:
        return self._service.stop()

    def restart(self) -> AgentRuntimeHealthReport:
        self._service.stop()
        self._service.start()
        return self._health.require_healthy()

    def status(self) -> AgentRuntimeManagerStatus:
        return self._service.status()

    def health_check(self) -> AgentRuntimeHealthReport:
        return self._health.check()

    def require_running(self) -> None:
        self._service.require_running()
