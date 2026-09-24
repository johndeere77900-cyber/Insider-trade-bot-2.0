"""
Telegram trading gateway for Insider Trade Bot 2.0.

Trading requests received through Telegram must pass through the existing
execution service. This module deliberately does not provide a direct path
to a broker or exchange.

Natural-language parsing is never treated as authorization to execute a
trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TelegramTradeRequest:
    """Structured trading request received from Telegram."""

    user_id: int
    symbol: str
    side: str
    quantity: float
    request_id: str


class TelegramTradingGateway:
    """
    Safety boundary for Telegram-originated trading requests.

    The execution service is injected and is responsible for the actual
    execution-mode, risk, identity, and safety checks.
    """

    def __init__(
        self,
        execution_service: Any = None,
    ) -> None:
        self.execution_service = execution_service

    def submit(
        self,
        request: TelegramTradeRequest,
        context: Any = None,
    ) -> Any:
        """
        Submit a structured trading request to the execution service.

        No execution occurs when an execution service has not been
        explicitly connected.
        """
        self._validate_request(request)

        if self.execution_service is None:
            raise RuntimeError(
                "Telegram trading gateway is not connected to an "
                "execution service."
            )

        execute = getattr(
            self.execution_service,
            "execute",
            None,
        )

        if not callable(execute):
            raise RuntimeError(
                "Configured execution service does not expose execute()."
            )

        return execute(
            request=request,
            context=context,
        )

    @staticmethod
    def _validate_request(
        request: TelegramTradeRequest,
    ) -> None:
        """Validate basic request shape before reaching execution."""
        if not isinstance(request.user_id, int):
            raise TypeError(
                "Telegram trading user_id must be an integer."
            )

        if not request.symbol.strip():
            raise ValueError(
                "Trading symbol cannot be empty."
            )

        normalized_side = request.side.strip().upper()

        if normalized_side not in {"BUY", "SELL"}:
            raise ValueError(
                "Trading side must be BUY or SELL."
            )

        if request.quantity <= 0:
            raise ValueError(
                "Trading quantity must be greater than zero."
            )

        if not request.request_id.strip():
            raise ValueError(
                "Trading request_id cannot be empty."
            )
