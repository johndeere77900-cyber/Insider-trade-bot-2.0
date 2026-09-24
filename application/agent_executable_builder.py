from __future__ import annotations

from typing import Any, Mapping

from application.agent_application_entrypoint_factory import (
    create_agent_application_entrypoint,
)
from application.agent_executable import AgentExecutable
from application.agent_process_factory import create_agent_process
from application.agent_runner_factory import create_agent_runner


class AgentExecutableBuilderError(RuntimeError):
    """Base error for executable construction operations."""


def build_agent_executable(
    agent: Any,
    metadata: Mapping[str, Any] | None = None,
) -> AgentExecutable:
    """
    Assemble the complete executable boundary around an existing agent.

    Construction is performed in layers:

        agent
        -> application entrypoint
        -> process
        -> runner
        -> executable

    The returned executable is not started.
    """

    if agent is None:
        raise ValueError("agent is required")

    entrypoint = create_agent_application_entrypoint(
        application=agent,
    )

    process = create_agent_process(entrypoint)

    runner = create_agent_runner(
        entrypoint=entrypoint,
    )

    executable = AgentExecutable(runner=runner)

    return executable
