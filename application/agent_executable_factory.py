from __future__ import annotations

from application.agent_executable import AgentExecutable
from application.agent_runner import AgentRunner


def create_agent_executable(
    runner: AgentRunner,
) -> AgentExecutable:
    """
    Create the final executable boundary around an existing agent runner.

    Construction only. The agent is not started.
    """

    if runner is None:
        raise ValueError("runner is required")

    return AgentExecutable(runner=runner)
