from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.agent_runtime import AgentRuntime
from application.agent_runtime_controller import AgentRuntimeController
from application.agent_runtime_health import AgentRuntimeHealth
from application.agent_runtime_interface import AgentRuntimeInterface
from application.agent_runtime_lifecycle import AgentRuntimeLifecycle
from application.agent_runtime_manager import AgentRuntimeManager
from application.agent_runtime_service import AgentRuntimeService


@dataclass(frozen=True)
class AgentRuntimeBundle:
    """
    Complete assembled runtime-control bundle for the agent.

    The bundle contains references to the runtime layers that were created
    around the same agent instance. It does not start the runtime.
    """

    runtime: AgentRuntime
    controller: AgentRuntimeController
    manager: AgentRuntimeManager
    service: AgentRuntimeService
    interface: AgentRuntimeInterface
    health: AgentRuntimeHealth
    lifecycle: AgentRuntimeLifecycle

    def start(self) -> Any:
        return self.lifecycle.start()

    def stop(self) -> Any:
        return self.lifecycle.stop()

    def restart(self) -> Any:
        return self.lifecycle.restart()

    def status(self) -> Any:
        return self.lifecycle.status()

    def health_check(self) -> Any:
        return self.lifecycle.health_check()

    def handle(self, request: Any) -> Any:
        return self.interface.handle(request)


def create_agent_runtime_bundle(agent: Any) -> AgentRuntimeBundle:
    """
    Assemble the complete runtime-control bundle around an existing agent.

    The agent itself is not started during construction.
    """

    if agent is None:
        raise ValueError("agent is required")

    runtime = AgentRuntime(agent)
    controller = AgentRuntimeController(runtime)
    manager = AgentRuntimeManager(controller)
    service = AgentRuntimeService(manager)
    interface = AgentRuntimeInterface(service)
    health = AgentRuntimeHealth(service)
    lifecycle = AgentRuntimeLifecycle(service, health)

    return AgentRuntimeBundle(
        runtime=runtime,
        controller=controller,
        manager=manager,
        service=service,
        interface=interface,
        health=health,
        lifecycle=lifecycle,
  )
