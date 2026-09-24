from __future__ import annotations

from typing import Any, Mapping

from application.agent_application import AgentApplication
from application.agent_application_entrypoint import (
    AgentApplicationEntrypoint,
)


def create_agent_application_entrypoint(
    application: AgentApplication,
) -> AgentApplicationEntrypoint:
    """
    Create the process-facing entrypoint around an existing application.

    Construction only. The application is not started.
    """

    if application is None:
        raise ValueError("application is required")

    return AgentApplicationEntrypoint(application=application)
