"""
Execution service for Insider Trade Bot.

This module coordinates:
    signal
        -> risk approval
        -> execution safety gate
        -> execution adapter

It does not contain strategy logic and does not bypass the safety layers.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models import Signal
from execution.interface import (
    ExecutionAdapter,
    ExecutionRequest,
    ExecutionResult,
)
from execution.safety import (
    ExecutionSafetyGate,
)
from risk.controls import (
    RiskCheckResult,
)


@dataclass(frozen=True)
class ExecutionServiceResult:
    """
    Complete result of one execution-service operation.
    """

    request: ExecutionRequest
    execution: ExecutionResult


class ExecutionServiceError(Exception):
    """Base exception for execution-service failures."""


class ExecutionService:
    """
    Controlled execution coordinator.

    The service cannot bypass the execution-safety gate.
    """

    def __init__(
        self,
        *,
        adapter: ExecutionAdapter,
        safety_gate: ExecutionSafetyGate,
    ) -> None:
        if not isinstance(
            adapter,
            ExecutionAdapter,
        ):
            raise TypeError(
                "adapter must implement ExecutionAdapter."
            )

        if not isinstance(
            safety_gate,
            ExecutionSafetyGate,
        ):
            raise TypeError(
                "safety_gate must be an ExecutionSafetyGate."
            )

        self.adapter = adapter
        self.safety_gate = safety_gate

    def execute(
        self,
        *,
        signal: Signal,
        risk_result: RiskCheckResult,
        request: ExecutionRequest,
    ) -> ExecutionServiceResult:
        """
        Pass an execution request through the safety gate and then to the
        configured execution adapter.
        """

        gate_result = self.safety_gate.evaluate(
            signal=signal,
            risk_result=risk_result,
            request=request,
        )

        self.safety_gate.require_approval(
            gate_result
        )

        try:
            execution_result = self.adapter.execute(
                request
            )
        except Exception as exc:
            raise ExecutionServiceError(
                f"Execution adapter failed: {exc}"
            ) from exc

        return ExecutionServiceResult(
            request=request,
            execution=execution_result,
        )

    def cancel(
        self,
        client_order_id: str,
    ) -> ExecutionResult:
        """
        Cancel an order through the configured execution adapter.
        """

        normalized_id = str(
            client_order_id
        ).strip()

        if not normalized_id:
            raise ValueError(
                "client_order_id cannot be empty."
            )

        try:
            return self.adapter.cancel(
                normalized_id
            )
        except Exception as exc:
            raise ExecutionServiceError(
                f"Execution cancellation failed: {exc}"
            ) from exc

    def get_status(
        self,
        client_order_id: str,
    ) -> ExecutionResult:
        """
        Retrieve execution status through the configured adapter.
        """

        normalized_id = str(
            client_order_id
        ).strip()

        if not normalized_id:
            raise ValueError(
                "client_order_id cannot be empty."
            )

        try:
            return self.adapter.get_status(
                normalized_id
            )
        except Exception as exc:
            raise ExecutionServiceError(
                f"Execution status lookup failed: {exc}"
            ) from exc
