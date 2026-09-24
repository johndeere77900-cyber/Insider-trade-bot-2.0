from __future__ import annotations

from typing import Any, Mapping

from application.agent_runtime_bootstrap import AgentRuntimeBootstrap
from application.agent_runtime_entrypoint import AgentRuntimeEntrypoint


def create_agent_runtime_entrypoint(
    agent: Any,
    metadata: Mapping[str, Any] | None = None,
) -> AgentRuntimeEntrypoint:
    """
    Create the process-facing runtime entrypoint.

    Construction only. The agent is not started.
    """

    if agent is None:
        raise ValueError("agent is required")

    bootstrap = AgentRuntimeBootstrap(
        agent=agent,
        metadata=metadata,
    )

    return AgentRuntimeEntrypoint(bootstrap)
