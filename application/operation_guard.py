"""
Application operation guard.

Provides a final application-layer boundary for checking whether an
operation is permitted before it reaches a domain service.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from application.configuration import ApplicationConfiguration
from application.errors import ApplicationRequestError


@dataclass(frozen=True)
class OperationDecision:
    """Result of an application operation authorization check."""

    allowed: bool
    operation: str
    reason: str


class ApplicationOperationGuard:
    """Guards application operations using runtime configuration."""

    def __init__(
        self,
        *,
        configuration: ApplicationConfiguration,
    ) -> None:
        if configuration is None:
            raise ValueError("configuration is required.")

        self.configuration = configuration

    def check(
        self,
        operation: str,
        *,
        execution_mode: Optional[str] = None,
    ) -> OperationDecision:
        """Determine whether an operation may proceed."""

        normalized_operation = operation.strip().lower()

        if not normalized_operation:
            raise ApplicationRequestError(
                "Operation name is required."
            )

        if normalized_operation == "live_trade":
            if not self.configuration.live_trading_enabled:
                return OperationDecision(
                    allowed=False,
                    operation=normalized_operation,
                    reason="Live trading is disabled.",
                )

            if not self.configuration.strict_mode:
                return OperationDecision(
                    allowed=False,
                    operation=normalized_operation,
                    reason="Live trading requires strict mode.",
                )

        if execution_mode is not None:
            mode = execution_mode.strip().lower()

            if mode not in {"paper", "live"}:
                return OperationDecision(
                    allowed=False,
                    operation=normalized_operation,
                    reason="Invalid execution mode.",
                )

            if mode == "live":
                if not self.configuration.live_trading_enabled:
                    return OperationDecision(
                        allowed=False,
                        operation=normalized_operation,
                        reason="Live trading is disabled.",
                    )

                if not self.configuration.strict_mode:
                    return OperationDecision(
                        allowed=False,
                        operation=normalized_operation,
                        reason="Live trading requires strict mode.",
                    )

            if mode == "paper":
                if not self.configuration.paper_trading_enabled:
                    return OperationDecision(
                        allowed=False,
                        operation=normalized_operation,
                        reason="Paper trading is disabled.",
                    )

        return OperationDecision(
            allowed=True,
            operation=normalized_operation,
            reason="Operation permitted by application configuration.",
    )
