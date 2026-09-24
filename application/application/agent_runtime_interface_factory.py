from __future__ import annotations

from application.agent_runtime_interface import AgentRuntimeInterface
from application.agent_runtime_service import AgentRuntimeService


def create_agent_runtime_interface(
    service: AgentRuntimeService,
) -> AgentRuntimeInterface:
    """
    Create the external runtime interface around an existing service.

    Construction only. The runtime is not started.
    """

    if service is None:
        raise ValueError("service is required")

    return AgentRuntimeInterface(service)
