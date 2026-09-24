from __future__ import annotations

from application.agent_runtime_health import AgentRuntimeHealth
from application.agent_runtime_lifecycle import AgentRuntimeLifecycle
from application.agent_runtime_service import AgentRuntimeService


def create_agent_runtime_lifecycle(
    service: AgentRuntimeService,
    health: AgentRuntimeHealth,
) -> AgentRuntimeLifecycle:
    """
    Create the runtime lifecycle coordinator.

    Construction only. No startup or shutdown operation is performed.
    """

    if service is None:
        raise ValueError("service is required")

    if health is None:
        raise ValueError("health is required")

    return AgentRuntimeLifecycle(
        service=service,
        health=health,
    )
