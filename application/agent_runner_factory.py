from __future__ import annotations

from application.agent_application_entrypoint import (
    AgentApplicationEntrypoint,
)
from application.agent_process_factory import create_agent_process
from application.agent_runner import AgentRunner


def create_agent_runner(
    entrypoint: AgentApplicationEntrypoint,
) -> AgentRunner:
    """
    Create the final process runner around an application entrypoint.

    Construction only. The agent is not started.
    """

    if entrypoint is None:
        raise ValueError("entrypoint is required")

    process = create_agent_process(entrypoint)

    return AgentRunner(process=process)
