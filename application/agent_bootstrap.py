"""
Top-level bootstrap boundary for Insider Trade Bot 2.0.

This module connects the existing application bootstrap/runtime machinery to
the top-level agent entrypoint.

Assembly only:
    configuration
        -> application registry
        -> application runtime
        -> external interfaces
        -> top-level entrypoint

No external polling or live trading is started by build().
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from application.agent_entrypoint import AgentEntrypoint
from application.agent_result import AgentResult
from application.bootstrap import bootstrap_application
from application.configuration import ApplicationConfiguration
from application.registry import ApplicationRegistry
from application.runtime_factory import RuntimeBundle, create_runtime_bundle
from application.trading_service import TradingService


@dataclass
class AgentBootstrapResult:
    """Result of assembling the top-level agent."""

    entrypoint: AgentEntrypoint
    registry: ApplicationRegistry
    runtime: Any
    interfaces: Any

    def status(self) -> dict[str, Any]:
        """Return the initial assembled-agent status."""
        return self.entrypoint.status()


def _dependency(
    dependencies: Any,
    name: str,
    default: Any = None,
) -> Any:
    """
    Read an optional dependency from either a mapping or an object.

    This keeps the bootstrap boundary compatible with simple dependency
    containers without inventing a new dependency-injection framework.
    """

    if dependencies is None:
        return default

    if isinstance(dependencies, Mapping):
        return dependencies.get(name, default)

    return getattr(
        dependencies,
        name,
        default,
    )


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
        dependencies: Any = None,
    ) -> None:
        if configuration is None:
            raise ValueError("configuration is required.")

        self.configuration = configuration
        self.dependencies = dependencies

    def build(self) -> AgentBootstrapResult:
        """
        Assemble the application registry, runtime, interfaces, and
        top-level entrypoint.
        """

        self.configuration.validate()

        dependencies = self.dependencies

        registry = bootstrap_application(
            environment=self.configuration.environment,
            paper_trading_enabled=(
                self.configuration.paper_trading_enabled
            ),
            live_trading_enabled=(
                self.configuration.live_trading_enabled
            ),
            historical_data_available=(
                self.configuration.historical_data_available
            ),
            event_study_engine=_dependency(
                dependencies,
                "event_study_engine",
            ),
            signal_engine=_dependency(
                dependencies,
                "signal_engine",
            ),
            backtest_engine=_dependency(
                dependencies,
                "backtest_engine",
            ),
            outcome_engine=_dependency(
                dependencies,
                "outcome_engine",
            ),
            research_performance=_dependency(
                dependencies,
                "research_performance",
            ),
            portfolio=_dependency(
                dependencies,
                "portfolio",
            ),
            execution_service=_dependency(
                dependencies,
                "execution_service",
            ),
        )

        runtime_bundle: RuntimeBundle = create_runtime_bundle(
            configuration=self.configuration,
            registry=registry,
        )

        runtime = runtime_bundle.runtime
        interfaces = runtime_bundle.interfaces

        trading_service: Optional[TradingService] = None

        try:
            trading_service = registry.get_trading()
        except RuntimeError:
            trading_service = None

        entrypoint = AgentEntrypoint(
            registry=registry,
            runtime=runtime,
            facade=runtime.facade,
            controller=runtime.facade.controller,
            command_parser=(
                runtime.facade.controller.command_parser
            ),
            command_service=(
                runtime.facade.controller.command_service
            ),
            trading_service=trading_service,
        )

        return AgentBootstrapResult(
            entrypoint=entrypoint,
            registry=registry,
            runtime=runtime,
            interfaces=interfaces,
        )

    def start(self) -> AgentResult:
        """Build and start the top-level agent."""

        result = self.build()

        return result.entrypoint.start()
