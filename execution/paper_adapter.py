"""
Paper execution adapter for Insider Trade Bot.

This adapter connects the generic execution interface to the local
paper-trading engine.

It never connects to a broker or exchange.
"""

from __future__ import annotations

from execution.interface import (
    ExecutionAdapter,
    ExecutionAdapterError,
    ExecutionRequest,
    ExecutionResult,
)
from trading.paper_engine import (
    PaperTradingEngine,
)


class PaperExecutionAdapter(
    ExecutionAdapter
):
    """
    ExecutionAdapter implementation backed by PaperTradingEngine.
    """

    def __init__(
        self,
        *,
        engine: PaperTradingEngine,
    ) -> None:
        if not isinstance(
            engine,
            PaperTradingEngine,
        ):
            raise TypeError(
                "engine must be a PaperTradingEngine instance."
            )

        self.engine = engine

        self._request_map: dict[
            str,
            str,
        ] = {}

    def execute(
        self,
        request: ExecutionRequest,
    ) -> ExecutionResult:
        """
        Execute a buy or sell request through the paper engine.
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

        if client_order_id in self._request_map:
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

        try:
            if request.side == "buy":
                order = self.engine.simulate_buy(
                    order_id=client_order_id,
                    symbol=request.symbol,
                    quantity=request.quantity,
                    execution_price=request.reference_price,
                )

            elif request.side == "sell":
                order = self.engine.simulate_sell(
                    order_id=client_order_id,
                    symbol=request.symbol,
                    quantity=request.quantity,
                    execution_price=request.reference_price,
                )

            else:
                raise ExecutionAdapterError(
                    "Unsupported execution side."
                )

        except Exception as exc:
            raise ExecutionAdapterError(
                f"Paper execution failed: {exc}"
            ) from exc

        self._request_map[
            client_order_id
        ] = order.order_id

        return ExecutionResult(
            client_order_id=client_order_id,
            external_order_id=order.order_id,
            status="filled",
            executed_quantity=order.quantity,
            executed_price=order.execution_price,
            message=(
                "Order executed in paper-trading mode."
            ),
        )

    def cancel(
        self,
        client_order_id: str,
    ) -> ExecutionResult:
        """
        Cancel a paper order when supported by the paper engine.

        The current paper engine does not expose order cancellation, so
        this adapter refuses the operation instead of pretending it was
        cancelled.
        """

        normalized_id = str(
            client_order_id
        ).strip()

        if not normalized_id:
            raise ExecutionAdapterError(
                "client_order_id cannot be empty."
            )

        if normalized_id not in self._request_map:
            raise ExecutionAdapterError(
                "Paper order does not exist."
            )

        raise ExecutionAdapterError(
            "Paper-order cancellation is not implemented."
        )

    def get_status(
        self,
        client_order_id: str,
    ) -> ExecutionResult:
        """
        Retrieve the current status of a paper order.
        """

        normalized_id = str(
            client_order_id
        ).strip()

        if not normalized_id:
            raise ExecutionAdapterError(
                "client_order_id cannot be empty."
            )

        paper_order_id = self._request_map.get(
            normalized_id
        )

        if paper_order_id is None:
            raise ExecutionAdapterError(
                "Paper order does not exist."
            )

        order = self.engine.get_order(
            paper_order_id
        )

        if order is None:
            raise ExecutionAdapterError(
                "Paper order state could not be found."
            )

        return ExecutionResult(
            client_order_id=normalized_id,
            external_order_id=order.order_id,
            status="filled",
            executed_quantity=order.quantity,
            executed_price=order.execution_price,
            message=(
                "Paper-trading order status."
            ),
          )
