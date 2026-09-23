"""
Paper-trading engine for Insider Trade Bot.

This module simulates trade execution without sending orders to an exchange
or broker. It is deliberately isolated from the live-trading layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from core.models import Signal


@dataclass(frozen=True)
class PaperOrder:
    """
    Represents a simulated paper-trading order.
    """

    order_id: str
    signal_key: str

    symbol: str
    side: str

    quantity: float

    reference_price: float

    status: str
    created_at: str


class PaperTradingError(Exception):
    """Base exception for paper-trading failures."""


class PaperTradingEngine:
    """
    Simulated trading engine.

    No network calls, broker calls, exchange calls, or live orders are
    performed by this class.
    """

    VALID_SIDES = {
        "buy",
        "sell",
    }

    def __init__(
        self,
        enabled: bool = True,
    ) -> None:
        self.enabled = enabled

    @staticmethod
    def _utc_now() -> str:
        """
        Return the current UTC timestamp.
        """

        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _validate_quantity(
        quantity: float,
    ) -> None:
        """
        Validate an order quantity.
        """

        if not isinstance(
            quantity,
            (int, float),
        ):
            raise PaperTradingError(
                "quantity must be numeric."
            )

        if quantity <= 0:
            raise PaperTradingError(
                "quantity must be greater than zero."
            )

    @staticmethod
    def _validate_price(
        price: float,
    ) -> None:
        """
        Validate a reference market price.
        """

        if not isinstance(
            price,
            (int, float),
        ):
            raise PaperTradingError(
                "reference_price must be numeric."
            )

        if price <= 0:
            raise PaperTradingError(
                "reference_price must be greater than zero."
            )

    def create_order(
        self,
        *,
        signal: Signal,
        side: str,
        quantity: float,
        reference_price: float,
    ) -> PaperOrder:
        """
        Create a simulated paper order from a signal.

        The order is marked as simulated and is never sent externally.
        """

        if not self.enabled:
            raise PaperTradingError(
                "Paper trading is disabled."
            )

        if not isinstance(
            signal,
            Signal,
        ):
            raise TypeError(
                "signal must be a Signal instance."
            )

        normalized_side = str(
            side
        ).strip().lower()

        if normalized_side not in self.VALID_SIDES:
            raise PaperTradingError(
                "side must be either 'buy' or 'sell'."
            )

        self._validate_quantity(
            quantity
        )

        self._validate_price(
            reference_price
        )

        if not signal.symbol.strip():
            raise PaperTradingError(
                "Signal symbol cannot be empty."
            )

        order_id = (
            f"PAPER-{uuid4().hex}"
        )

        return PaperOrder(
            order_id=order_id,
            signal_key=signal.signal_key,
            symbol=signal.symbol,
            side=normalized_side,
            quantity=float(quantity),
            reference_price=float(
                reference_price
            ),
            status="simulated",
            created_at=self._utc_now(),
        )

    def cancel_order(
        self,
        order: PaperOrder,
    ) -> PaperOrder:
        """
        Mark a simulated paper order as cancelled.

        This only changes the local representation of the simulated order.
        """

        if not isinstance(
            order,
            PaperOrder,
        ):
            raise TypeError(
                "order must be a PaperOrder instance."
            )

        return PaperOrder(
            order_id=order.order_id,
            signal_key=order.signal_key,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            reference_price=order.reference_price,
            status="cancelled",
            created_at=order.created_at,
  )
