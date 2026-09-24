from __future__ import annotations

from typing import Any, Mapping

from application.agent_runtime_assembly import (
    AgentRuntimeAssembly,
    assemble_agent_runtime,
)


class AgentRuntimeBootstrapError(RuntimeError):
    """Base error for runtime bootstrap operations."""


class AgentRuntimeBootstrap:
    """
    Bootstrap boundary for constructing the complete agent runtime.

    This class assembles the runtime but does not start it automatically.
    """

    def __init__(
        self,
        agent: Any,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if agent is None:
            raise ValueError("agent is required")

        self._agent = agent
        self._metadata = dict(metadata or {})
        self._assembly: AgentRuntimeAssembly | None = None

    @property
    def agent(self) -> Any:
        return self._agent

    @property
    def metadata(self) -> Mapping[str, Any]:
        return dict(self._metadata)

    @property
    def assembly(self) -> AgentRuntimeAssembly:
        if self._assembly is None:
            raise AgentRuntimeBootstrapError(
                "Agent runtime has not been bootstrapped"
            )

        return self._assembly

    def build(self) -> AgentRuntimeAssembly:
        if self._assembly is None:
            self._assembly = assemble_agent_runtime(self._agent)

        return self._assembly

    def start(self) -> Any:
        return self.build().start()

    def stop(self) -> Any:
        if self._assembly is None:
            return None

        return self._assembly.stop()

    def restart(self) -> Any:
        return self.build().restart()

    def status(self) -> Any:
        return self.build().status()

    def health_check(self) -> Any:
        return self.build().health_check()

    def handle(self, request: Any) -> Any:
        return self.build().handle(request)
