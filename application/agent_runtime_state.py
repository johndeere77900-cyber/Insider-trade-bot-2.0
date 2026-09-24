"""
Runtime state for Insider Trade Bot 2.0.

This module tracks lifecycle state only. It does not contain trading,
research, market, or database state.
"""

from __future__ import annotations

from enum import Enum


class AgentRuntimeState(str, Enum):
    """Allowed top-level runtime states."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


class AgentRuntimeStateMachine:
    """Small state machine for controlled agent lifecycle transitions."""

    _ALLOWED_TRANSITIONS = {
        AgentRuntimeState.CREATED: {
            AgentRuntimeState.STARTING,
            AgentRuntimeState.FAILED,
        },
        AgentRuntimeState.STARTING: {
            AgentRuntimeState.RUNNING,
            AgentRuntimeState.FAILED,
        },
        AgentRuntimeState.RUNNING: {
            AgentRuntimeState.STOPPING,
            AgentRuntimeState.FAILED,
        },
        AgentRuntimeState.STOPPING: {
            AgentRuntimeState.STOPPED,
            AgentRuntimeState.FAILED,
        },
        AgentRuntimeState.STOPPED: {
            AgentRuntimeState.STARTING,
            AgentRuntimeState.FAILED,
        },
        AgentRuntimeState.FAILED: {
            AgentRuntimeState.STARTING,
            AgentRuntimeState.STOPPED,
        },
    }

    def __init__(
        self,
        initial_state: AgentRuntimeState = AgentRuntimeState.CREATED,
    ) -> None:
        self._state = initial_state

    @property
    def state(self) -> AgentRuntimeState:
        """Return the current runtime state."""
        return self._state

    def transition(self, new_state: AgentRuntimeState) -> AgentRuntimeState:
        """Transition to a permitted state."""
        if new_state == self._state:
            return self._state

        allowed = self._ALLOWED_TRANSITIONS.get(self._state, set())

        if new_state not in allowed:
            raise ValueError(
                f"Invalid runtime transition: "
                f"{self._state.value} -> {new_state.value}"
            )

        self._state = new_state
        return self._state

    def is_running(self) -> bool:
        """Return whether the runtime is operational."""
        return self._state is AgentRuntimeState.RUNNING

    def is_terminal(self) -> bool:
        """Return whether the runtime is stopped."""
        return self._state is AgentRuntimeState.STOPPED

    def to_dict(self) -> dict[str, str]:
        """Return a serializable state representation."""
        return {
            "state": self._state.value,
  }
