"""
Live-trading safety boundary for Insider Trade Bot.

This module intentionally does not contain broker or exchange execution
logic yet.

Its purpose is to establish a hard control boundary so that live trading
cannot be reached accidentally from research, backtesting, or paper
trading components.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models import Signal


class LiveTradingError(Exception):
    """Base exception for live-trading failures."""


class LiveTradingDisabledError(
    LiveTradingError
):
    """Raised whenever live trading is disabled."""


class LiveExecutionNotConfiguredError(
    LiveTradingError
):
    """Raised when no verified live executor exists."""


@dataclass(frozen=True)
class LiveTradingStatus:
    """
    Explicit status of the live-trading boundary.
    """

    enabled: bool
    executor_configured: bool
    execution_allowed: bool


class LiveTradingEngine:
    """
    Safety-controlled live-trading boundary.

    Live execution remains unavailable until both:
        1. live trading is explicitly enabled, and
        2. a verified execution adapter is configured.

    This class does not provide a direct exchange or broker implementation.
    """

    def __init__(
        self,
        enabled: bool = False,
        executor_configured: bool = False,
    ) -> None:
        self.enabled = enabled
        self.executor_configured = (
            executor_configured
        )

    def status(self) -> LiveTradingStatus:
        """
        Return the current live-trading safety status.
        """

        return LiveTradingStatus(
            enabled=self.enabled,
            executor_configured=(
                self.executor_configured
            ),
            execution_allowed=(
                self.enabled
                and self.executor_configured
            ),
        )

    def validate_live_execution(
        self,
        signal: Signal,
    ) -> None:
        """
        Validate whether a signal may reach the live execution boundary.

        This method performs safety checks only. It does not submit an order.
        """

        if not isinstance(
            signal,
            Signal,
        ):
            raise TypeError(
                "signal must be a Signal instance."
            )

        if not self.enabled:
            raise LiveTradingDisabledError(
                "Live trading is disabled."
            )

        if not self.executor_configured:
            raise LiveExecutionNotConfiguredError(
                "No verified live-trading executor is configured."
            )

        if not signal.signal_key.strip():
            raise LiveTradingError(
                "Signal key cannot be empty."
            )

        if not signal.symbol.strip():
            raise LiveTradingError(
                "Signal symbol cannot be empty."
            )

    def execute(
        self,
        signal: Signal,
        *,
        side: str,
        quantity: float,
    ) -> None:
        """
        Refuse execution until a verified live execution adapter exists.

        This deliberate failure prevents accidental live trading from being
        implemented through an incomplete placeholder.
        """

        self.validate_live_execution(
            signal
        )

        normalized_side = str(
            side
        ).strip().lower()

        if normalized_side not in {
            "buy",
            "sell",
        }:
            raise LiveTradingError(
                "side must be either 'buy' or 'sell'."
            )

        if not isinstance(
            quantity,
            (int, float),
        ):
            raise LiveTradingError(
                "quantity must be numeric."
            )

        if quantity <= 0:
            raise LiveTradingError(
                "quantity must be greater than zero."
            )

        raise LiveExecutionNotConfiguredError(
            "Live execution adapter has not been implemented. "
            "No live order was submitted."
    )
