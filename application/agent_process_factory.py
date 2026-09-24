from __future__ import annotations

from typing import Any, Mapping

from application.agent_application_entrypoint import (
    AgentApplicationEntrypoint,
)
from application.agent_process import AgentProcess


def create_agent_process(
    entrypoint: AgentApplicationEntrypoint,
) -> AgentProcess:
    """
    Create the process-level coordinator around an existing application
    entrypoint.

    Construction only. The application is not started.
    """

    if entrypoint is None:
        raise ValueError("entrypoint is required")

    return AgentProcess(entrypoint=entrypoint)
