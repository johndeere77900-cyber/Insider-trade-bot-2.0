from __future__ import annotations

from threading import RLock
from typing import Any, Mapping

from application.agent_runtime_bundle import AgentRuntimeBundle


class AgentRuntimeRegistryError(RuntimeError):
    """Base error for runtime registry operations."""


class AgentRuntimeRegistry:
    """
    Registry for the currently assembled agent runtime bundle.

    Only one active runtime bundle is permitted in a registry instance.
    Registration does not automatically start the runtime.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._bundle: AgentRuntimeBundle | None = None

    def register(self, bundle: AgentRuntimeBundle) -> None:
        if bundle is None:
            raise ValueError("bundle is required")

        with self._lock:
            if self._bundle is not None:
                raise AgentRuntimeRegistryError(
                    "An agent runtime bundle is already registered"
                )

            self._bundle = bundle

    def replace(self, bundle: AgentRuntimeBundle) -> None:
        if bundle is None:
            raise ValueError("bundle is required")

        with self._lock:
            self._bundle = bundle

    def clear(self) -> None:
        with self._lock:
            self._bundle = None

    def is_registered(self) -> bool:
        with self._lock:
            return self._bundle is not None

    def get(self) -> AgentRuntimeBundle:
        with self._lock:
            if self._bundle is None:
                raise AgentRuntimeRegistryError(
                    "No agent runtime bundle is registered"
                )

            return self._bundle

    def status(self) -> Mapping[str, Any]:
        with self._lock:
            bundle = self.get()

            status = bundle.status()

            if hasattr(status, "to_dict"):
                return status.to_dict()

            if isinstance(status, Mapping):
                return dict(status)

            return {"status": status}
