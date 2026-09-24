from __future__ import annotations

from application.agent_runtime_manager import AgentRuntimeManager
from application.agent_runtime_service import AgentRuntimeService


def create_agent_runtime_service(
    manager: AgentRuntimeManager,
) -> AgentRuntimeService:
    """
    Create the high-level runtime service around an existing manager.

    Construction only. The runtime is not started.
    """

    if manager is None:
        raise ValueError("manager is required")

    return AgentRuntimeService(manager)
