"""
Factory for constructing the top-level Insider Trade Bot agent.
"""

from __future__ import annotations

from typing import Any, Optional

from application.agent import InsiderTradeAgent
from application.command_parser import ApplicationCommandParser
from application.command_service import ApplicationCommandService
from application.controller import ApplicationController
from application.facade import ApplicationFacade
from application.operation_guard import ApplicationOperationGuard
from application.registry import ApplicationRegistry
from application.trading_service import TradingService


def create_agent(
    *,
    registry: ApplicationRegistry,
    runtime: Any,
    facade: Optional[ApplicationFacade] = None,
    controller: Optional[ApplicationController] = None,
    command_parser: Optional[ApplicationCommandParser] = None,
    command_service: Optional[ApplicationCommandService] = None,
    trading_service: Optional[TradingService] = None,
    operation_guard: Optional[ApplicationOperationGuard] = None,
) -> InsiderTradeAgent:
    """
    Construct the top-level agent from already-created application
    components.

    This factory deliberately does not create domain services itself.
    Dependency construction remains the responsibility of the application
    bootstrap/runtime layer.
    """

    return InsiderTradeAgent(
        registry=registry,
        runtime=runtime,
        facade=facade,
        controller=controller,
        command_parser=command_parser,
        command_service=command_service,
        trading_service=trading_service,
        operation_guard=operation_guard,
  )
