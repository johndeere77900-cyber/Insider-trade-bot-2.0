"""
Execution-safety gate for Insider Trade Bot.

This module is the final local safety boundary before an execution adapter
may receive an order.

It does not submit orders itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models import Signal
from execution.interface import ExecutionRequest
from risk.controls import RiskCheckResult


@dataclass(frozen=True)
class ExecutionGateResult:
    """
    Result of the final execution-safety evaluation.
    """

    approved: bool

    reasons: tuple[str, ...]


class ExecutionSafetyError(Exception):
    """Base exception for execution-safety failures."""


class ExecutionSafetyGate:
    """
    Final safety gate for execution requests.

    The gate requires:
        - a valid signal,
        - an approved risk result,
        - an explicit live-execution enablement,
        - a valid execution request.
    """

    def __init__(
        self,
        *,
        live_execution_enabled: bool = False,
    ) -> None:
        self.live_execution_enabled = (
            live_execution_enabled
        )

    def evaluate(
        self,
        *,
        signal: Signal,
        risk_result: RiskCheckResult,
        request: ExecutionRequest,
    ) -> ExecutionGateResult:
        """
        Evaluate whether an execution request may pass the local safety
        boundary.

        No external execution occurs here.
        """

        reasons: list[str] = []

        if not isinstance(
            signal,
            Signal,
        ):
            raise TypeError(
                "signal must be a Signal instance."
            )

        if not isinstance(
            risk_result,
            RiskCheckResult,
        ):
            raise TypeError(
                "risk_result must be a RiskCheckResult."
            )

        if not isinstance(
            request,
            ExecutionRequest,
        ):
            raise TypeError(
                "request must be an ExecutionRequest."
            )

        if not self.live_execution_enabled:
            reasons.append(
                "Live execution is disabled."
            )

        if not risk_result.approved:
            reasons.append(
                "Risk controls did not approve the proposed order."
            )

        if not signal.signal_key.strip():
            reasons.append(
                "Signal key is empty."
            )

        if not signal.symbol.strip():
            reasons.append(
                "Signal symbol is empty."
            )

        if not request.client_order_id.strip():
            reasons.append(
                "Client order ID is empty."
            )

        if not request.symbol.strip():
            reasons.append(
                "Execution symbol is empty."
            )

        if (
            request.symbol.strip().upper()
            != signal.symbol.strip().upper()
        ):
            reasons.append(
                "Execution symbol does not match the signal symbol."
            )

        if request.side not in {
            "buy",
            "sell",
        }:
            reasons.append(
                "Execution side must be 'buy' or 'sell'."
            )

        if request.quantity <= 0:
            reasons.append(
                "Execution quantity must be greater than zero."
            )

        if request.reference_price <= 0:
            reasons.append(
                "Execution reference price must be greater than zero."
            )

        return ExecutionGateResult(
            approved=not reasons,
            reasons=tuple(reasons),
        )

    def require_approval(
        self,
        result: ExecutionGateResult,
    ) -> None:
        """
        Stop execution when the safety gate has not approved the request.
        """

        if not isinstance(
            result,
            ExecutionGateResult,
        ):
            raise TypeError(
                "result must be an ExecutionGateResult."
            )

        if result.approved:
            return

        raise ExecutionSafetyError(
            "Execution safety gate rejected the request: "
            + "; ".join(
                result.reasons
            )
    )
