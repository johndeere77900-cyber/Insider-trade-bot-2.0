from __future__ import annotations

from typing import Any, Mapping

from application.agent_runtime_application import AgentRuntimeApplication
from application.agent_runtime_runner_factory import (
    create_agent_runtime_runner,
)


def create_agent_runtime_application(
    agent: Any,
    metadata: Mapping[str, Any] | None = None,
) -> AgentRuntimeApplication:
    """
    Create the top-level runtime application boundary.

    Construction only. The agent is not started.
    """

    if agent is None:
        raise ValueError("agent is required")

    runner = create_agent_runtime_runner(
        agent=agent,
        metadata=metadata,
    )

    return AgentRuntimeApplication(runner=runner)
