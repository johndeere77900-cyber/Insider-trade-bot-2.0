"""
Factory service for constructing the top-level Insider Trade Bot service.

This module keeps top-level assembly separate from runtime execution.
"""

from __future__ import annotations

from typing import Any, Optional

from application.agent import InsiderTradeAgent
from application.agent_factory import create_agent
from application.agent_service import AgentService
from application.agent_runtime import AgentRuntime
from application.command_parser import ApplicationCommandParser
from application.command_service import ApplicationCommandService
from application.controller import ApplicationController
from application.facade import ApplicationFacade
from application.operation_guard import ApplicationOperationGuard
from application.registry import ApplicationRegistry
from application.trading_service import TradingService


def create_agent_service(
    *,
    registry: ApplicationRegistry,
    runtime: Any,
    facade: Optional[ApplicationFacade] = None,
    controller: Optional[ApplicationController] = None,
    command_parser: Optional[ApplicationCommandParser] = None,
    command_service: Optional[ApplicationCommandService] = None,
    trading_service: Optional[TradingService] = None,
    operation_guard: Optional[ApplicationOperationGuard] = None,
) -> AgentService:
    """
    Assemble and return the top-level AgentService.

    All underlying dependencies must already be constructed by the
    application/bootstrap layer.
    """

    agent: InsiderTradeAgent = create_agent(
        registry=registry,
        runtime=runtime,
        facade=facade,
        controller=controller,
        command_parser=command_parser,
        command_service=command_service,
        trading_service=trading_service,
        operation_guard=operation_guard,
    )

    agent_runtime = AgentRuntime(agent)

    return AgentService(
        agent=agent,
        runtime=agent_runtime,
    )
