"""
Paper-trading engine for Insider Trade Bot.

This module simulates trade execution without sending orders to any broker
or exchange.

Paper trading is isolated from live trading and exists for testing,
validation, and historical evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from risk.controls import (
    Position,
    RiskCheckResult,
    check_order,
)
from trading.portfolio import (
    Portfolio,
)


@dataclass(frozen=True)
class PaperOrder:
    """
    Simulated order record.
    """

    order_id: str

    symbol: str
    side: str

    quantity: float
    execution_price: float

    created_at: str


class PaperTradingError(Exception):
    """Base exception for paper-trading failures."""


class PaperTradingEngine:
    """
    Simulated trading engine.

    This engine changes only internal paper state.
    It never communicates with an external execution venue.
    """

    def __init__(
        self,
        *,
        portfolio: Portfolio,
    ) -> None:
        if not isinstance(
            portfolio,
            Portfolio,
        ):
            raise TypeError(
                "portfolio must be a Portfolio instance."
            )

        self.portfolio = portfolio

        self._orders: dict[str, PaperOrder] = {}

    @staticmethod
    def _timestamp() -> str:
        """
        Generate an ISO UTC timestamp.
        """

        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _normalize_side(
        side: str,
    ) -> str:
        """
        Normalize order direction.
        """

        normalized = str(
            side
        ).strip().lower()

        if normalized not in {
            "buy",
            "sell",
        }:
            raise PaperTradingError(
                "side must be either 'buy' or 'sell'."
            )

        return normalized

    @staticmethod
    def _validate_quantity(
        quantity: float,
    ) -> None:
        """
        Validate order quantity.
        """

        if quantity <= 0:
            raise PaperTradingError(
                "quantity must be greater than zero."
            )

    def simulate_buy(
        self,
        *,
        order_id: str,
        symbol: str,
        quantity: float,
        execution_price: float,
        risk_result: RiskCheckResult | None = None,
    ) -> PaperOrder:
        """
        Simulate a buy order.

        A risk result may be supplied from the risk-control layer.
        """

        if risk_result is not None:
            if not risk_result.approved:
                raise PaperTradingError(
                    "Paper buy rejected by risk controls."
                )

        normalized_order_id = str(
            order_id
        ).strip()

        if not normalized_order_id:
            raise PaperTradingError(
                "order_id cannot be empty."
            )

        if normalized_order_id in self._orders:
            raise PaperTradingError(
                "Duplicate paper order ID."
            )

        self._validate_quantity(
            quantity
        )

        normalized_symbol = str(
            symbol
        ).strip().upper()

        if not normalized_symbol:
            raise PaperTradingError(
                "symbol cannot be empty."
            )

        if execution_price <= 0:
            raise PaperTradingError(
                "execution_price must be greater than zero."
            )

        existing = self.portfolio.get_position(
            normalized_symbol
        )

        if existing is not None:
            new_quantity = (
                existing.quantity
                + quantity
            )

            weighted_price = (
                (
                    existing.quantity
                    * existing.reference_price
                )
                +
                (
                    quantity
                    * execution_price
                )
            ) / new_quantity

            self.portfolio.update_position(
                symbol=normalized_symbol,
                quantity=new_quantity,
                reference_price=weighted_price,
            )

        else:
            self.portfolio.add_position(
                Position(
                    symbol=normalized_symbol,
                    quantity=float(quantity),
                    reference_price=float(
                        execution_price
                    ),
                )
            )

        order = PaperOrder(
            order_id=normalized_order_id,
            symbol=normalized_symbol,
            side="buy",
            quantity=float(quantity),
            execution_price=float(
                execution_price
            ),
            created_at=self._timestamp(),
        )

        self._orders[
            normalized_order_id
        ] = order

        return order

    def simulate_sell(
        self,
        *,
        order_id: str,
        symbol: str,
        quantity: float,
        execution_price: float,
    ) -> PaperOrder:
        """
        Simulate a sell order.
        """

        normalized_order_id = str(
            order_id
        ).strip()

        if not normalized_order_id:
            raise PaperTradingError(
                "order_id cannot be empty."
            )

        if normalized_order_id in self._orders:
            raise PaperTradingError(
                "Duplicate paper order ID."
            )

        self._validate_quantity(
            quantity
        )

        normalized_symbol = str(
            symbol
        ).strip().upper()

        position = self.portfolio.get_position(
            normalized_symbol
        )

        if position is None:
            raise PaperTradingError(
                "Cannot sell a symbol that is not held."
            )

        if quantity > position.quantity:
            raise PaperTradingError(
                "Cannot sell more than the current position."
            )

        remaining = (
            position.quantity
            - quantity
        )

        if remaining == 0:
            self.portfolio.remove_position(
                normalized_symbol
            )

        else:
            self.portfolio.update_position(
                symbol=normalized_symbol,
                quantity=remaining,
                reference_price=position.reference_price,
            )

        order = PaperOrder(
            order_id=normalized_order_id,
            symbol=normalized_symbol,
            side="sell",
            quantity=float(quantity),
            execution_price=float(
                execution_price
            ),
            created_at=self._timestamp(),
        )

        self._orders[
            normalized_order_id
        ] = order

        return order

    def get_order(
        self,
        order_id: str,
    ) -> PaperOrder | None:
        """
        Retrieve one simulated order.
        """

        return self._orders.get(
            str(order_id).strip()
        )

    def list_orders(
        self,
    ) -> tuple[PaperOrder, ...]:
        """
        Return all simulated orders.
        """

        return tuple(
            self._orders.values()
          )
