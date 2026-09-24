"""
Controlled runtime lifecycle for Insider Trade Bot 2.0.
"""

from __future__ import annotations

from typing import Any

from application.agent_runtime import AgentRuntime
from application.agent_runtime_state import (
    AgentRuntimeState,
    AgentRuntimeStateMachine,
)


class AgentRuntimeController:
    """
    Controls the runtime lifecycle while keeping the underlying agent
    responsible for its actual application startup and shutdown.
    """

    def __init__(
        self,
        *,
        runtime: AgentRuntime,
        state_machine: AgentRuntimeStateMachine | None = None,
    ) -> None:
        self._runtime = runtime
        self._state_machine = (
            state_machine or AgentRuntimeStateMachine()
        )

    @property
    def runtime(self) -> AgentRuntime:
        """Return the managed runtime."""
        return self._runtime

    @property
    def state_machine(self) -> AgentRuntimeStateMachine:
        """Return the lifecycle state machine."""
        return self._state_machine

    def start(self) -> dict[str, Any]:
        """Start the runtime through a controlled state transition."""

        current = self._state_machine.state

        if current is AgentRuntimeState.RUNNING:
            return self.status()

        self._state_machine.transition(AgentRuntimeState.STARTING)

        try:
            self._runtime.start()
            self._state_machine.transition(AgentRuntimeState.RUNNING)
        except Exception:
            self._state_machine.transition(AgentRuntimeState.FAILED)
            raise

        return self.status()

    def stop(self) -> dict[str, Any]:
        """Stop the runtime through a controlled state transition."""

        current = self._state_machine.state

        if current is AgentRuntimeState.STOPPED:
            return self.status()

        if current is not AgentRuntimeState.RUNNING:
            raise RuntimeError(
                f"Cannot stop runtime from state: {current.value}"
            )

        self._state_machine.transition(AgentRuntimeState.STOPPING)

        try:
            self._runtime.stop()
            self._state_machine.transition(AgentRuntimeState.STOPPED)
        except Exception:
            self._state_machine.transition(AgentRuntimeState.FAILED)
            raise

        return self.status()

    def status(self) -> dict[str, Any]:
        """Return controller and runtime status."""
        return {
            "state": self._state_machine.state.value,
            "runtime_running": self._runtime.is_running(),
            "runtime": self._runtime.status().to_dict(),
        }

    def health(self) -> dict[str, Any]:
        """Return runtime health information."""
        return self._runtime.health()
