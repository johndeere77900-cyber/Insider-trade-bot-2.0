"""
Application assembly.

Builds the complete application-layer request path from the already-created
services without starting external interfaces.
"""

from __future__ import annotations

from typing import Any

from application.command_parser import ApplicationCommandParser
from application.command_service import ApplicationCommandService
from application.controller import ApplicationController
from application.facade import ApplicationFacade
from application.registry import ApplicationRegistry


def assemble_application(
    registry: ApplicationRegistry,
) -> ApplicationFacade:
    """
    Assemble the public application facade.

    External interfaces should depend on the returned facade rather than
    constructing application services directly.
    """

    if registry is None:
        raise ValueError("registry is required.")

    parser = ApplicationCommandParser()

    command_service = ApplicationCommandService(
        registry=registry,
    )

    controller = ApplicationController(
        command_parser=parser,
        command_service=command_service,
    )

    return ApplicationFacade(
        controller=controller,
  )
