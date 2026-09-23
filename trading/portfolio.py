"""
Portfolio-state layer for Insider Trade Bot.

This module maintains a controlled in-memory representation of positions
used by paper trading, risk checks, and later portfolio persistence.

It does not connect to a broker or exchange.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from risk.controls import Position


@dataclass(frozen=True)
class PortfolioSnapshot:
    """
    Immutable snapshot of portfolio positions.
    """

    positions: tuple[Position, ...]

    total_exposure: float


class PortfolioError(Exception):
    """Base exception for portfolio-state failures."""


class Portfolio:
    """
    Controlled portfolio-state container.

    The portfolio stores position state locally. It does not execute orders.
    """

    def __init__(
        self,
        positions: Iterable[Position] | None = None,
    ) -> None:
        self._positions: dict[str, Position] = {}

        if positions is not None:
            for position in positions:
                self.add_position(
                    position
                )

    @staticmethod
    def _normalize_symbol(
        symbol: str,
    ) -> str:
        """
        Normalize a portfolio symbol.
        """

        normalized = str(
            symbol
        ).strip().upper()

        if not normalized:
            raise PortfolioError(
                "symbol cannot be empty."
            )

        return normalized

    @staticmethod
    def _validate_position(
        position: Position,
    ) -> None:
        """
        Validate one portfolio position.
        """

        if not isinstance(
            position,
            Position,
        ):
            raise TypeError(
                "position must be a Position instance."
            )

        if position.quantity <= 0:
            raise PortfolioError(
                "position quantity must be greater than zero."
            )

        if position.reference_price <= 0:
            raise PortfolioError(
                "position reference price must be greater than zero."
            )

    def add_position(
        self,
        position: Position,
    ) -> None:
        """
        Add a new position.

        Existing positions for the same symbol are rejected rather than
        silently replaced.
        """

        self._validate_position(
            position
        )

        symbol = self._normalize_symbol(
            position.symbol
        )

        if symbol in self._positions:
            raise PortfolioError(
                f"Position for {symbol} already exists."
            )

        self._positions[
            symbol
        ] = Position(
            symbol=symbol,
            quantity=float(
                position.quantity
            ),
            reference_price=float(
                position.reference_price
            ),
        )

    def update_position(
        self,
        *,
        symbol: str,
        quantity: float,
        reference_price: float,
    ) -> None:
        """
        Replace the state of an existing position.
        """

        normalized_symbol = self._normalize_symbol(
            symbol
        )

        if quantity <= 0:
            raise PortfolioError(
                "quantity must be greater than zero."
            )

        if reference_price <= 0:
            raise PortfolioError(
                "reference_price must be greater than zero."
            )

        if normalized_symbol not in self._positions:
            raise PortfolioError(
                f"No existing position for {normalized_symbol}."
            )

        self._positions[
            normalized_symbol
        ] = Position(
            symbol=normalized_symbol,
            quantity=float(quantity),
            reference_price=float(
                reference_price
            ),
        )

    def remove_position(
        self,
        symbol: str,
    ) -> None:
        """
        Remove an existing position.
        """

        normalized_symbol = self._normalize_symbol(
            symbol
        )

        if normalized_symbol not in self._positions:
            raise PortfolioError(
                f"No existing position for {normalized_symbol}."
            )

        del self._positions[
            normalized_symbol
        ]

    def get_position(
        self,
        symbol: str,
    ) -> Position | None:
        """
        Retrieve one position by symbol.
        """

        normalized_symbol = self._normalize_symbol(
            symbol
        )

        return self._positions.get(
            normalized_symbol
        )

    def list_positions(
        self,
    ) -> tuple[Position, ...]:
        """
        Return all current positions.
        """

        return tuple(
            self._positions.values()
        )

    def total_exposure(
        self,
    ) -> float:
        """
        Calculate total portfolio exposure.
        """

        return sum(
            position.quantity
            * position.reference_price
            for position
            in self._positions.values()
        )

    def snapshot(
        self,
    ) -> PortfolioSnapshot:
        """
        Create an immutable portfolio snapshot.
        """

        return PortfolioSnapshot(
            positions=self.list_positions(),
            total_exposure=self.total_exposure(),
        )

    def clear(
        self,
    ) -> None:
        """
        Remove all locally stored portfolio positions.
        """

        self._positions.clear()
