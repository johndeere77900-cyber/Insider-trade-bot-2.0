from __future__ import annotations

from typing import Any, Mapping

from application.agent_application import AgentApplication
from application.agent_runtime_application_factory import (
    create_agent_runtime_application,
)


def create_agent_application(
    agent: Any,
    metadata: Mapping[str, Any] | None = None,
) -> AgentApplication:
    """
    Create the top-level agent application.

    Construction only. The agent is not started.
    """

    if agent is None:
        raise ValueError("agent is required")

    runtime_application = create_agent_runtime_application(
        agent=agent,
        metadata=metadata,
    )

    return AgentApplication(runtime=runtime_application)
