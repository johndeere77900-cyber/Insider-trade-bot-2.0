"""
Factory for constructing the complete top-level agent manager.
"""

from __future__ import annotations

from typing import Any, Optional

from application.agent_factory_service import create_agent_service
from application.agent_health import AgentHealth
from application.agent_interface import AgentInterface
from application.agent_lifecycle import AgentLifecycle
from application.agent_manager import AgentManager
from application.agent_service import AgentService
from application.command_parser import ApplicationCommandParser
from application.command_service import ApplicationCommandService
from application.controller import ApplicationController
from application.facade import ApplicationFacade
from application.operation_guard import ApplicationOperationGuard
from application.registry import ApplicationRegistry
from application.trading_service import TradingService


def create_agent_manager(
    *,
    registry: ApplicationRegistry,
    runtime: Any,
    facade: Optional[ApplicationFacade] = None,
    controller: Optional[ApplicationController] = None,
    command_parser: Optional[ApplicationCommandParser] = None,
    command_service: Optional[ApplicationCommandService] = None,
    trading_service: Optional[TradingService] = None,
    operation_guard: Optional[ApplicationOperationGuard] = None,
) -> AgentManager:
    """
    Assemble the complete top-level agent manager.

    All domain and infrastructure dependencies must already be created by
    the lower-level application bootstrap process.
    """

    service: AgentService = create_agent_service(
        registry=registry,
        runtime=runtime,
        facade=facade,
        controller=controller,
        command_parser=command_parser,
        command_service=command_service,
        trading_service=trading_service,
        operation_guard=operation_guard,
    )

    interface = AgentInterface(service)
    health = AgentHealth(interface)

    lifecycle = AgentLifecycle(
        interface=interface,
        health=health,
    )

    return AgentManager(
        service=service,
        interface=interface,
        health=health,
        lifecycle=lifecycle,
)
