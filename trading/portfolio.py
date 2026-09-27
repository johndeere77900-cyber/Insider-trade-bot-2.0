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

    Compatibility attributes:
        positions
            Dictionary-style view used by the existing test/application
            compatibility layer.

        cash
            Current cash balance. A newly created portfolio starts with
            zero cash unless explicitly configured.
    """

    def __init__(
        self,
        positions: Iterable[Position] | None = None,
        *,
        cash: float = 0.0,
    ) -> None:
        if cash < 0:
            raise PortfolioError(
                "cash cannot be negative."
            )

        self._positions: dict[str, Position | float | int] = {}
        self._cash = float(cash)

        if positions is not None:
            for position in positions:
                self.add_position(position)

    @property
    def positions(self) -> dict[str, Position | float | int]:
        """
        Return the compatibility dictionary of portfolio positions.

        This intentionally exposes the underlying dictionary because the
        existing application/test compatibility layer expects dictionary-style
        access such as:

            portfolio.positions["AAPL"] = 100

        Normal application code should prefer add_position(),
        update_position(), remove_position(), get_position(), and
        list_positions().
        """

        return self._positions

    @property
    def cash(self) -> float:
        """
        Return the current portfolio cash balance.
        """

        return self._cash

    @cash.setter
    def cash(self, value: float) -> None:
        """
        Set the portfolio cash balance.
        """

        numeric_value = float(value)

        if numeric_value < 0:
            raise PortfolioError(
                "cash cannot be negative."
            )

        self._cash = numeric_value

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

        Dictionary-style compatibility values that are not Position objects
        are ignored by this typed accessor.
        """

        normalized_symbol = self._normalize_symbol(
            symbol
        )

        position = self._positions.get(
            normalized_symbol
        )

        if isinstance(position, Position):
            return position

        return None

    def list_positions(
        self,
    ) -> tuple[Position, ...]:
        """
        Return all current Position objects.

        Compatibility dictionary values that are simple numeric values are
        excluded from this typed application-level view.
        """

        return tuple(
            position
            for position in self._positions.values()
            if isinstance(position, Position)
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
            if isinstance(position, Position)
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
