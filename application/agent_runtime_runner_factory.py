from __future__ import annotations

from typing import Any, Mapping

from application.agent_runtime_process_factory import (
    create_agent_runtime_process,
)
from application.agent_runtime_runner import AgentRuntimeRunner


def create_agent_runtime_runner(
    agent: Any,
    metadata: Mapping[str, Any] | None = None,
) -> AgentRuntimeRunner:
    """
    Create the final runtime runner around an existing agent.

    Construction only. The agent is not started.
    """

    if agent is None:
        raise ValueError("agent is required")

    process = create_agent_runtime_process(
        agent=agent,
        metadata=metadata,
    )

    return AgentRuntimeRunner(process)
