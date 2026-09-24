from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from application.agent_runtime_service import AgentRuntimeService


class AgentRuntimeHealthError(RuntimeError):
    """Base error for runtime health operations."""


@dataclass(frozen=True)
class AgentRuntimeHealthReport:
    """Immutable health report for the running agent runtime."""

    healthy: bool
    running: bool
    state: str
    checked_at: datetime
    details: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "running": self.running,
            "state": self.state,
            "checked_at": self.checked_at.isoformat(),
            "details": dict(self.details),
        }


class AgentRuntimeHealth:
    """
    Health-check boundary for the agent runtime.

    This component observes runtime state only. It does not start, stop,
    modify, or execute trading operations.
    """

    def __init__(self, service: AgentRuntimeService) -> None:
        if service is None:
            raise ValueError("service is required")

        self._service = service

    @property
    def service(self) -> AgentRuntimeService:
        return self._service

    def check(self) -> AgentRuntimeHealthReport:
        status = self._service.status()

        checked_at = datetime.now(timezone.utc)

        details = dict(status.details)
        details["status_snapshot"] = status.to_dict()

        return AgentRuntimeHealthReport(
            healthy=status.healthy,
            running=status.running,
            state=status.state,
            checked_at=checked_at,
            details=details,
        )

    def is_healthy(self) -> bool:
        return self.check().healthy

    def require_healthy(self) -> AgentRuntimeHealthReport:
        report = self.check()

        if not report.healthy:
            raise AgentRuntimeHealthError(
                f"Agent runtime is unhealthy: state={report.state}"
            )

        return report
