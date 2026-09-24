from __future__ import annotations

from typing import Any, Mapping

from application.agent_executable import AgentExecutable
from application.agent_executable_builder import build_agent_executable


class AgentLaunchError(RuntimeError):
    """Base error for agent launch operations."""


def create_agent_launch(
    agent: Any,
    metadata: Mapping[str, Any] | None = None,
) -> AgentExecutable:
    """
    Assemble the executable launch boundary around an existing agent.

    Construction only. The agent is not started automatically.
    """

    if agent is None:
        raise ValueError("agent is required")

    return build_agent_executable(
        agent=agent,
        metadata=metadata,
    )
