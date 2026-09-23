"""
Execution-mode control for Insider Trade Bot.

This module defines the explicit operating modes of the trading system and
prevents accidental mixing of paper and live execution.
"""

from __future__ import annotations

from enum import Enum


class ExecutionMode(
    str,
    Enum,
):
    """
    Supported execution modes.
    """

    PAPER = "paper"
    LIVE = "live"


class ExecutionModeError(
    Exception
):
    """Raised when an invalid execution mode is requested."""


class ExecutionModeController:
    """
    Controls the currently selected execution mode.

    The default mode is PAPER.

    LIVE mode requires explicit enablement and is never enabled merely
    because a live adapter exists.
    """

    def __init__(
        self,
        *,
        live_enabled: bool = False,
        initial_mode: ExecutionMode = ExecutionMode.PAPER,
    ) -> None:
        if not isinstance(
            initial_mode,
            ExecutionMode,
        ):
            raise TypeError(
                "initial_mode must be an ExecutionMode."
            )

        self.live_enabled = bool(
            live_enabled
        )

        if (
            initial_mode == ExecutionMode.LIVE
            and not self.live_enabled
        ):
            raise ExecutionModeError(
                "LIVE mode cannot be selected while live execution "
                "is disabled."
            )

        self._mode = initial_mode

    @property
    def mode(
        self,
    ) -> ExecutionMode:
        """
        Return the current execution mode.
        """

        return self._mode

    def set_mode(
        self,
        mode: ExecutionMode,
    ) -> None:
        """
        Change the execution mode.

        LIVE mode requires explicit live enablement.
        """

        if not isinstance(
            mode,
            ExecutionMode,
        ):
            raise TypeError(
                "mode must be an ExecutionMode."
            )

        if (
            mode == ExecutionMode.LIVE
            and not self.live_enabled
        ):
            raise ExecutionModeError(
                "LIVE mode is disabled."
            )

        self._mode = mode

    def enable_live(
        self,
    ) -> None:
        """
        Explicitly enable the live-execution mode.

        This does not select LIVE mode automatically.
        """

        self.live_enabled = True

    def disable_live(
        self,
    ) -> None:
        """
        Disable live execution immediately.

        If LIVE mode is currently selected, the controller automatically
        returns to PAPER mode.
        """

        self.live_enabled = False

        if self._mode == ExecutionMode.LIVE:
            self._mode = ExecutionMode.PAPER

    def require_mode(
        self,
        expected_mode: ExecutionMode,
    ) -> None:
        """
        Require that the system is currently operating in a specific mode.
        """

        if not isinstance(
            expected_mode,
            ExecutionMode,
        ):
            raise TypeError(
                "expected_mode must be an ExecutionMode."
            )

        if self._mode != expected_mode:
            raise ExecutionModeError(
                f"Execution mode is '{self._mode.value}', "
                f"but '{expected_mode.value}' was required."
            )

    def is_paper(
        self,
    ) -> bool:
        """
        Return True when PAPER mode is active.
        """

        return (
            self._mode
            == ExecutionMode.PAPER
        )

    def is_live(
        self,
    ) -> bool:
        """
        Return True only when LIVE mode is active and explicitly enabled.
        """

        return (
            self._mode
            == ExecutionMode.LIVE
            and self.live_enabled
        )
