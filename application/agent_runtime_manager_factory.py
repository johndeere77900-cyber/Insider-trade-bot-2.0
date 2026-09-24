from __future__ import annotations

from application.agent_runtime_controller import AgentRuntimeController
from application.agent_runtime_manager import AgentRuntimeManager
from application.agent_runtime import AgentRuntime


def create_agent_runtime_manager(agent: object) -> AgentRuntimeManager:
    """
    Create an AgentRuntimeManager around an existing agent.

    Construction only. The returned runtime is not started.
    """

    if agent is None:
        raise ValueError("agent is required")

    runtime = AgentRuntime(agent)
    controller = AgentRuntimeController(runtime)

    return AgentRuntimeManager(controller)
