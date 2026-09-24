from __future__ import annotations

from typing import Any

from application.agent_runtime_controller import AgentRuntimeController
from application.agent_runtime_interface import AgentRuntimeInterface
from application.agent_runtime_manager import AgentRuntimeManager
from application.agent_runtime_service import AgentRuntimeService
from application.agent_runtime import AgentRuntime


def create_agent_runtime_stack(agent: Any) -> dict[str, Any]:
    """
    Build the runtime control stack around an existing agent.

    Construction order:
        AgentRuntime
        -> AgentRuntimeController
        -> AgentRuntimeManager
        -> AgentRuntimeService
        -> AgentRuntimeInterface

    The factory only assembles components. It does not start the agent.
    """

    if agent is None:
        raise ValueError("agent is required")

    runtime = AgentRuntime(agent)
    controller = AgentRuntimeController(runtime)
    manager = AgentRuntimeManager(controller)
    service = AgentRuntimeService(manager)
    interface = AgentRuntimeInterface(service)

    return {
        "runtime": runtime,
        "controller": controller,
        "manager": manager,
        "service": service,
        "interface": interface,
    }
