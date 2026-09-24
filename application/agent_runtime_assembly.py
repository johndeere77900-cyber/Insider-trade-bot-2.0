from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.agent_runtime_bundle import (
    AgentRuntimeBundle,
    create_agent_runtime_bundle,
)
from application.agent_runtime_registry import AgentRuntimeRegistry
from application.agent_runtime_registry_factory import (
    create_agent_runtime_registry,
)


class AgentRuntimeAssemblyError(RuntimeError):
    """Base error for runtime assembly operations."""


@dataclass(frozen=True)
class AgentRuntimeAssembly:
    """
    Complete assembly boundary for the agent runtime.

    This object combines the runtime bundle with its registry. Construction
    does not start the agent.
    """

    bundle: AgentRuntimeBundle
    registry: AgentRuntimeRegistry

    def start(self) -> Any:
        return self.bundle.start()

    def stop(self) -> Any:
        return self.bundle.stop()

    def restart(self) -> Any:
        return self.bundle.restart()

    def status(self) -> Any:
        return self.bundle.status()

    def health_check(self) -> Any:
        return self.bundle.health_check()

    def handle(self, request: Any) -> Any:
        return self.bundle.handle(request)


def assemble_agent_runtime(agent: Any) -> AgentRuntimeAssembly:
    """
    Assemble and register the complete runtime for an existing agent.

    The returned runtime remains stopped until start() is explicitly called.
    """

    if agent is None:
        raise ValueError("agent is required")

    bundle = create_agent_runtime_bundle(agent)
    registry = create_agent_runtime_registry()
    registry.register(bundle)

    return AgentRuntimeAssembly(
        bundle=bundle,
        registry=registry,
  )
