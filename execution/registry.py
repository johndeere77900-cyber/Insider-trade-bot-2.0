"""
Execution-adapter registry for Insider Trade Bot.

This module provides controlled registration and retrieval of execution
adapters.

It keeps execution-provider selection separate from research, risk, and
strategy components.
"""

from __future__ import annotations

from execution.interface import (
    ExecutionAdapter,
)


class ExecutionRegistryError(
    Exception
):
    """Base exception for execution-registry failures."""


class ExecutionAdapterRegistry:
    """
    Registry of explicitly configured execution adapters.

    An adapter must be registered before it can be retrieved by name.
    """

    def __init__(self) -> None:
        self._adapters: dict[
            str,
            ExecutionAdapter,
        ] = {}

    @staticmethod
    def _normalize_name(
        name: str,
    ) -> str:
        """
        Normalize an adapter name.
        """

        normalized = str(
            name
        ).strip().lower()

        if not normalized:
            raise ExecutionRegistryError(
                "Adapter name cannot be empty."
            )

        return normalized

    def register(
        self,
        name: str,
        adapter: ExecutionAdapter,
    ) -> None:
        """
        Register an execution adapter.

        Existing names cannot be silently replaced.
        """

        normalized_name = self._normalize_name(
            name
        )

        if not isinstance(
            adapter,
            ExecutionAdapter,
        ):
            raise TypeError(
                "adapter must implement ExecutionAdapter."
            )

        if normalized_name in self._adapters:
            raise ExecutionRegistryError(
                f"Execution adapter '{normalized_name}' "
                "is already registered."
            )

        self._adapters[
            normalized_name
        ] = adapter

    def get(
        self,
        name: str,
    ) -> ExecutionAdapter:
        """
        Retrieve a registered execution adapter.
        """

        normalized_name = self._normalize_name(
            name
        )

        adapter = self._adapters.get(
            normalized_name
        )

        if adapter is None:
            raise ExecutionRegistryError(
                f"Execution adapter '{normalized_name}' "
                "is not registered."
            )

        return adapter

    def contains(
        self,
        name: str,
    ) -> bool:
        """
        Check whether an adapter is registered.
        """

        normalized_name = self._normalize_name(
            name
        )

        return normalized_name in self._adapters

    def list_names(
        self,
    ) -> tuple[str, ...]:
        """
        Return registered adapter names.
        """

        return tuple(
            self._adapters.keys()
        )

    def unregister(
        self,
        name: str,
    ) -> None:
        """
        Remove a registered adapter.

        This only removes the local registry entry. It does not terminate
        or modify any external broker/exchange session.
        """

        normalized_name = self._normalize_name(
            name
        )

        if normalized_name not in self._adapters:
            raise ExecutionRegistryError(
                f"Execution adapter '{normalized_name}' "
                "is not registered."
            )

        del self._adapters[
            normalized_name
  ]
