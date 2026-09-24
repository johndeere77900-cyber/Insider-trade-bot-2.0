"""
Application controller.

Provides the single request entry point used by external interfaces.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from application.command_parser import ApplicationCommandParser
from application.command_service import ApplicationCommandService
from application.context import ApplicationContext
from application.result import ApplicationResult


class ApplicationController:
    """Coordinates command parsing and command execution."""

    def __init__(
        self,
        *,
        command_parser: ApplicationCommandParser,
        command_service: ApplicationCommandService,
    ) -> None:
        if command_parser is None:
            raise ValueError("command_parser is required.")

        if command_service is None:
            raise ValueError("command_service is required.")

        self.command_parser = command_parser
        self.command_service = command_service

    def handle(
        self,
        *,
        command: str,
        parameters: Optional[Mapping[str, Any]] = None,
        context: Optional[ApplicationContext] = None,
    ) -> ApplicationResult:
        """Parse and execute one application command."""

        request_id = context.request_id if context else None
        user_id = context.user_id if context else None
        source = context.source if context else "unknown"

        parsed_command = self.command_parser.parse(
            command,
            parameters=parameters,
            request_id=request_id,
            user_id=user_id,
            source=source,
        )

        return self.command_service.execute(
            parsed_command,
            context=context,
      )
