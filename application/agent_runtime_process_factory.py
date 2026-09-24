from __future__ import annotations

from typing import Any, Mapping

from application.agent_runtime_entrypoint_factory import (
    create_agent_runtime_entrypoint,
)
from application.agent_runtime_process import AgentRuntimeProcess


def create_agent_runtime_process(
    agent: Any,
    metadata: Mapping[str, Any] | None = None,
) -> AgentRuntimeProcess:
    """
    Create the process-level runtime coordinator.

    Construction only. The agent is not started.
    """

    if agent is None:
        raise ValueError("agent is required")

    entrypoint = create_agent_runtime_entrypoint(
        agent=agent,
        metadata=metadata,
    )

    return AgentRuntimeProcess(entrypoint)
