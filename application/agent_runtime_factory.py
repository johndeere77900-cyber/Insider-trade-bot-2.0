"""
Factory for constructing the top-level agent runtime components.
"""

from __future__ import annotations

from typing import Any

from application.agent import InsiderTradeAgent
from application.agent_health import AgentHealth
from application.agent_interface import AgentInterface
from application.agent_lifecycle import AgentLifecycle
from application.agent_manager import AgentManager
from application.agent_observability import AgentObservability
from application.agent_runtime import AgentRuntime
from application.agent_service import AgentService


def create_agent_runtime(
    *,
    agent: InsiderTradeAgent,
) -> tuple[
    AgentRuntime,
    AgentService,
    AgentInterface,
    AgentHealth,
    AgentLifecycle,
    AgentManager,
    AgentObservability,
]:
    """
    Assemble the complete top-level runtime boundary around an agent.

    The supplied agent must already have its application dependencies
    assembled.
    """

    runtime = AgentRuntime(agent)

    service = AgentService(
        agent=agent,
        runtime=runtime,
    )

    interface = AgentInterface(service)

    health = AgentHealth(interface)

    lifecycle = AgentLifecycle(
        interface=interface,
        health=health,
    )

    manager = AgentManager(
        service=service,
        interface=interface,
        health=health,
        lifecycle=lifecycle,
    )

    observability = AgentObservability(
        manager=manager,
        health=health,
    )

    return (
        runtime,
        service,
        interface,
        health,
        lifecycle,
        manager,
        observability,
  )
