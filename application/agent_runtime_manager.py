from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any, Mapping

from application.agent_runtime_controller import AgentRuntimeController
from application.agent_runtime_state import AgentRuntimeState


class AgentRuntimeManagerError(RuntimeError):
    """Base error for runtime-manager operations."""


class AgentRuntimeManagerNotStartedError(AgentRuntimeManagerError):
    """Raised when an operation requires a running agent."""


@dataclass(frozen=True)
class AgentRuntimeManagerStatus:
    """Immutable runtime-manager status snapshot."""

    state: str
    running: bool
    healthy: bool
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "running": self.running,
            "healthy": self.healthy,
            "details": dict(self.details),
        }


class AgentRuntimeManager:
    """
    Coordinates the agent runtime controller at the manager boundary.

    This class does not implement business logic. It provides a single
    lifecycle/status boundary for higher-level application components.
    """

    def __init__(self, controller: AgentRuntimeController) -> None:
        if controller is None:
            raise ValueError("controller is required")

        self._controller = controller
        self._lock = RLock()

    @property
    def controller(self) -> AgentRuntimeController:
        return self._controller

    def start(self) -> AgentRuntimeManagerStatus:
        with self._lock:
            self._controller.start()
            return self.status()

    def stop(self) -> AgentRuntimeManagerStatus:
        with self._lock:
            self._controller.stop()
            return self.status()

    def is_running(self) -> bool:
        with self._lock:
            return self._controller.is_running()

    def state(self) -> AgentRuntimeState:
        with self._lock:
            return self._controller.state()

    def status(self) -> AgentRuntimeManagerStatus:
        with self._lock:
            state = self._controller.state()
            running = self._controller.is_running()
            health = self._controller.health()

            healthy = self._extract_health_value(
                health,
                default=running and state == AgentRuntimeState.RUNNING,
            )

            details = self._normalize_details(health)

            return AgentRuntimeManagerStatus(
                state=state.value,
                running=running,
                healthy=healthy,
                details=details,
            )

    def health(self) -> Mapping[str, Any]:
        with self._lock:
            health = self._controller.health()
            return self._normalize_details(health)

    def require_running(self) -> None:
        with self._lock:
            if not self._controller.is_running():
                raise AgentRuntimeManagerNotStartedError(
                    "Agent runtime is not running"
                )

    def handle(self, request: Any) -> Any:
        self.require_running()
        return self._controller.handle(request)

    @staticmethod
    def _extract_health_value(
        health: Any,
        *,
        default: bool,
    ) -> bool:
        if isinstance(health, bool):
            return health

        if isinstance(health, Mapping):
            value = health.get("healthy")
            if isinstance(value, bool):
                return value

            value = health.get("ok")
            if isinstance(value, bool):
                return value

        value = getattr(health, "healthy", None)
        if isinstance(value, bool):
            return value

        value = getattr(health, "ok", None)
        if isinstance(value, bool):
            return value

        return default

    @staticmethod
    def _normalize_details(health: Any) -> dict[str, Any]:
        if health is None:
            return {}

        if isinstance(health, Mapping):
            return dict(health)

        to_dict = getattr(health, "to_dict", None)
        if callable(to_dict):
            result = to_dict()
            if isinstance(result, Mapping):
                return dict(result)

        if hasattr(health, "__dict__"):
            return dict(vars(health))

        return {"value": health}
