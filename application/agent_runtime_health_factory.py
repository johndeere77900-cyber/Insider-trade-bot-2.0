from __future__ import annotations

from application.agent_runtime_health import AgentRuntimeHealth
from application.agent_runtime_service import AgentRuntimeService


def create_agent_runtime_health(
    service: AgentRuntimeService,
) -> AgentRuntimeHealth:
    """
    Create the runtime health boundary around an existing runtime service.

    Construction only. No runtime lifecycle operation is performed.
    """

    if service is None:
        raise ValueError("service is required")

    return AgentRuntimeHealth(service)
