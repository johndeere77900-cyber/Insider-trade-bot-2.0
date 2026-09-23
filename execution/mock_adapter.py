"""
Mock execution adapter for Insider Trade Bot.

This adapter provides a completely local execution implementation for
integrated testing and paper-like execution-path verification.

It never connects to a broker, exchange, or external service.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from execution.interface import (
    ExecutionAdapter,
    ExecutionAdapterError,
    ExecutionRequest,
    ExecutionResult,
)


class MockExecutionAdapter(
    ExecutionAdapter
):
    """
    Local execution adapter.

    Orders are stored only in memory and marked as filled immediately.
    """

    def __init__(self) -> None:
        self._orders: dict[
            str,
            ExecutionResult,
        ] = {}

    @staticmethod
    def _timestamp() -> str:
        """
        Return the current UTC timestamp.
        """

        return datetime.now(
            timezone.utc
        ).isoformat()

    def execute(
        self,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        """
        Simulate successful execution locally.
        """

        if not isinstance(
            request,
            ExecutionRequest,
        ):
            raise TypeError(
                "request must be an ExecutionRequest."
            )

        client_order_id = str(
            request.client_order_id
        ).strip()

        if not client_order_id:
            raise ExecutionAdapterError(
                "client_order_id cannot be empty."
            )

        if client_order_id in self._orders:
            raise ExecutionAdapterError(
                "Duplicate client_order_id."
            )

        if request.quantity <= 0:
            raise ExecutionAdapterError(
                "quantity must be greater than zero."
            )

        if request.reference_price <= 0:
            raise ExecutionAdapterError(
                "reference_price must be greater than zero."
            )

        external_order_id = (
            f"MOCK-{uuid4().hex}"
        )

        result = ExecutionResult(
            client_order_id=client_order_id,
            external_order_id=external_order_id,
            status="filled",
            executed_quantity=float(
                request.quantity
            ),
            executed_price=float(
                request.reference_price
            ),
            message=(
                "Order executed by the local mock adapter "
                f"at {self._timestamp()}."
            ),
        )

        self._orders[
            client_order_id
        ] = result

        return result

    def cancel(
        self,
        client_order_id: str,
    ) -> ExecutionResult:
        """
        Simulate cancellation of a locally stored order.
        """

        normalized_id = str(
            client_order_id
        ).strip()

        if not normalized_id:
            raise ExecutionAdapterError(
                "client_order_id cannot be empty."
            )

        existing = self._orders.get(
            normalized_id
        )

        if existing is None:
            raise ExecutionAdapterError(
                "Order does not exist."
            )

        if existing.status == "cancelled":
            return existing

        result = ExecutionResult(
            client_order_id=existing.client_order_id,
            external_order_id=existing.external_order_id,
            status="cancelled",
            executed_quantity=existing.executed_quantity,
            executed_price=existing.executed_price,
            message=(
                "Order cancelled by the local mock adapter "
                f"at {self._timestamp()}."
            ),
        )

        self._orders[
            normalized_id
        ] = result

        return result

    def get_status(
        self,
        client_order_id: str,
    ) -> ExecutionResult:
        """
        Retrieve the locally stored execution result.
        """

        normalized_id = str(
            client_order_id
        ).strip()

        if not normalized_id:
            raise ExecutionAdapterError(
                "client_order_id cannot be empty."
            )

        result = self._orders.get(
            normalized_id
        )

        if result is None:
            raise ExecutionAdapterError(
                "Order does not exist."
            )

        return result

    def list_orders(
        self,
    ) -> tuple[ExecutionResult, ...]:
        """
        Return all locally stored mock-execution results.
        """

        return tuple(
            self._orders.values()
            )
