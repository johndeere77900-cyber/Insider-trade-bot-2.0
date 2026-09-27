"""
Live execution adapter boundary for Insider Trade Bot.

This module establishes the controlled interface for a future verified
broker or exchange implementation.

No real orders are submitted by this module.
"""

from __future__ import annotations

from execution.interface import (
    ExecutionAdapter,
    ExecutionAdapterError,
    ExecutionRequest,
    ExecutionResult,
)
from execution.mode import ExecutionMode


class LiveAdapterNotConfiguredError(
    ExecutionAdapterError
):
    """
    Raised when live execution has not been connected to a verified
    broker/exchange implementation.
    """


class LiveExecutionAdapter(
    ExecutionAdapter
):
    """
    Safety placeholder for the future live broker/exchange adapter.

    This class deliberately refuses every execution operation until a
    verified provider-specific implementation replaces or extends it.

    No live network request is performed here.
    """

    def __init__(
        self,
        *,
        provider_name: str | None = None,
        configured: bool = False,
    ) -> None:
        normalized_provider = (
            str(provider_name).strip()
            if provider_name is not None
            else ""
        )

        if configured and not normalized_provider:
            raise ValueError(
                "A provider name is required when the live adapter "
                "is marked as configured."
            )

        self.provider_name = (
            normalized_provider or None
        )

        self.configured = bool(
            configured
        )

        self.mode = ExecutionMode.LIVE

    def is_enabled(
        self,
    ) -> bool:
        """
        Return whether live execution is explicitly enabled.

        The adapter is disabled by default. Creating a live adapter
        does not automatically enable live execution.
        """

        return self.configured

    def _require_configuration(
        self,
    ) -> None:
        """
        Refuse operation until a verified live provider is configured.
        """

        if not self.configured:
            raise LiveAdapterNotConfiguredError(
                "Live execution provider is not configured. "
                "No live order was submitted."
            )

        if not self.provider_name:
            raise LiveAdapterNotConfiguredError(
                "Live execution provider name is missing. "
                "No live order was submitted."
            )

    def execute(
        self,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        """
        Refuse live execution until a verified provider implementation
        exists.
        """

        if not isinstance(
            request,
            ExecutionRequest,
        ):
            raise TypeError(
                "request must be an ExecutionRequest."
            )

        self._require_configuration()

        raise LiveAdapterNotConfiguredError(
            "A provider-specific live execution implementation has not "
            "been installed. No live order was submitted."
        )

    def cancel(
        self,
        client_order_id: str,
    ) -> ExecutionResult:
        """
        Refuse live cancellation until a verified provider implementation
        exists.
        """

        normalized_id = str(
            client_order_id
        ).strip()

        if not normalized_id:
            raise ValueError(
                "client_order_id cannot be empty."
            )

        self._require_configuration()

        raise LiveAdapterNotConfiguredError(
            "A provider-specific live cancellation implementation has "
            "not been installed. No live order was submitted."
        )

    def get_status(
        self,
        client_order_id: str,
    ) -> ExecutionResult:
        """
        Refuse live status lookup until a verified provider implementation
        exists.
        """

        normalized_id = str(
            client_order_id
        ).strip()

        if not normalized_id:
            raise ValueError(
                "client_order_id cannot be empty."
            )

        self._require_configuration()

        raise LiveAdapterNotConfiguredError(
            "A provider-specific live status implementation has not "
            "been installed. No live order was submitted."
        )
