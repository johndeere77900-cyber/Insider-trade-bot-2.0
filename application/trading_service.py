"""
Application-level trading service.

Provides the controlled bridge between external interfaces and the existing
execution layer. It does not bypass execution-mode, safety, or risk controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class TradingRequest:
    """Normalized trading request."""

    symbol: str
    side: str
    quantity: float
    order_type: str = "market"
    limit_price: Optional[float] = None
    execution_mode: Optional[str] = None
    metadata: Optional[Mapping[str, Any]] = None


class TradingService:
    """
    Controlled application boundary for trading requests.

    The execution service is injected and remains responsible for enforcing
    execution mode, safety checks, risk controls, and adapter selection.
    """

    def __init__(
        self,
        *,
        execution_service: Any,
        paper_trading_enabled: bool = True,
        live_trading_enabled: bool = False,
    ) -> None:
        if execution_service is None:
            raise ValueError("execution_service is required.")

        self.execution_service = execution_service
        self.paper_trading_enabled = paper_trading_enabled
        self.live_trading_enabled = live_trading_enabled

    def execute(
        self,
        *,
        request: TradingRequest,
        context: Any = None,
    ) -> Mapping[str, Any]:
        """
        Submit a normalized trading request to the execution boundary.

        No broker, exchange, or live adapter is called directly here.
        """

        self._validate_request(request)

        result = self.execution_service.execute(
            request=request,
            context=context,
        )

        if isinstance(result, Mapping):
            return dict(result)

        return {
            "status": "completed",
            "result": result,
        }

    def _validate_request(self, request: TradingRequest) -> None:
        """Validate basic request shape before execution."""

        if not isinstance(request, TradingRequest):
            raise TypeError("request must be a TradingRequest instance.")

        symbol = request.symbol.strip().upper()

        if not symbol:
            raise ValueError("Trading symbol is required.")

        if request.quantity <= 0:
            raise ValueError("Trading quantity must be greater than zero.")

        side = request.side.strip().lower()

        if side not in {"buy", "sell"}:
            raise ValueError("Trading side must be 'buy' or 'sell'.")

        order_type = request.order_type.strip().lower()

        if order_type not in {"market", "limit"}:
            raise ValueError("Order type must be 'market' or 'limit'.")

        if order_type == "limit":
            if request.limit_price is None:
                raise ValueError(
                    "limit_price is required for limit orders."
                )

            if request.limit_price <= 0:
                raise ValueError(
                    "limit_price must be greater than zero."
                )

        if request.execution_mode is not None:
            mode = request.execution_mode.strip().lower()

            if mode not in {"paper", "live"}:
                raise ValueError(
                    "execution_mode must be 'paper' or 'live'."
                )

            if mode == "paper" and not self.paper_trading_enabled:
                raise ValueError("Paper trading is disabled.")

            if mode == "live" and not self.live_trading_enabled:
                raise ValueError("Live trading is disabled.")
