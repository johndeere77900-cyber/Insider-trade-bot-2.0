from __future__ import annotations

from application.agent_runtime_registry import AgentRuntimeRegistry


def create_agent_runtime_registry() -> AgentRuntimeRegistry:
    """
    Create an empty runtime registry.

    The registry does not create or start an agent. A runtime bundle must
    be explicitly registered after construction.
    """

    return AgentRuntimeRegistry()
