"""
Top-level bootstrap boundary for Insider Trade Bot 2.0.

This module connects the existing application bootstrap/runtime machinery to
the top-level agent entrypoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from application.agent_entrypoint import AgentEntrypoint
from application.agent_result import AgentResult
from application.bootstrap import bootstrap_application
from application.configuration import ApplicationConfiguration
from application.registry import ApplicationRegistry
from application.runtime_factory import create_runtime_bundle
from application.trading_service import TradingService


@dataclass
class AgentBootstrapResult:
    """Result of assembling the top-level agent."""

    entrypoint: AgentEntrypoint
    registry: ApplicationRegistry
    runtime: Any

    def status(self) -> dict[str, Any]:
        """Return the initial assembled-agent status."""
        return self.entrypoint.status()


class AgentBootstrap:
    """
    Constructs the top-level agent from application-level dependencies.

    This class performs assembly only. It does not perform historical data
    ingestion, research, backtesting, or live trading.
    """

    def __init__(
        self,
        *,
        configuration: ApplicationConfiguration,
        dependencies: Any,
    ) -> None:
        self.configuration = configuration
        self.dependencies = dependencies

    def build(self) -> AgentBootstrapResult:
        """
        Assemble the application registry, runtime, and top-level entrypoint.
        """

        self.configuration.validate()

        registry = bootstrap_application(
            dependencies=self.dependencies,
        )

        runtime_bundle = create_runtime_bundle(
            registry=registry,
            dependencies=self.dependencies,
        )

        trading_service: Optional[TradingService] = None

        try:
            trading_service = registry.get_trading()
        except Exception:
            trading_service = None

        entrypoint = AgentEntrypoint(
            registry=registry,
            runtime=runtime_bundle.runtime,
            facade=runtime_bundle.facade,
            controller=getattr(
                runtime_bundle,
                "controller",
                None,
            ),
            command_parser=getattr(
                runtime_bundle,
                "command_parser",
                None,
            ),
            command_service=getattr(
                runtime_bundle,
                "command_service",
                None,
            ),
            trading_service=trading_service,
        )

        return AgentBootstrapResult(
            entrypoint=entrypoint,
            registry=registry,
            runtime=runtime_bundle.runtime,
        )

    def start(self) -> AgentResult:
        """Build and start the top-level agent."""
        result = self.build()
        return result.entrypoint.start()
