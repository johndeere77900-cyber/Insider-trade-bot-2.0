"""
Application runtime factory.

Creates the assembled runtime and optional external-interface bridges without
starting external network loops or live trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from application.assembly import assemble_application
from application.configuration import ApplicationConfiguration
from application.interface_factory import (
    ApplicationInterfaces,
    create_interfaces,
)
from application.registry import ApplicationRegistry
from application.runtime import ApplicationRuntime
from application.startup import ApplicationStartup


@dataclass(frozen=True)
class RuntimeBundle:
    """Complete assembled application runtime bundle."""

    runtime: ApplicationRuntime
    interfaces: ApplicationInterfaces


def create_runtime_bundle(
    *,
    configuration: ApplicationConfiguration,
    registry: ApplicationRegistry,
    health_service: Optional[Any] = None,
) -> RuntimeBundle:
    """
    Assemble the runtime and external interface bridges.

    No Telegram polling, market-data polling, or live order submission is
    started by this factory.
    """

    if configuration is None:
        raise ValueError("configuration is required.")

    if registry is None:
        raise ValueError("registry is required.")

    startup = ApplicationStartup(
        configuration=configuration,
    )

    runtime = startup.initialize(
        registry=registry,
    )

    facade = assemble_application(registry)

    interfaces = create_interfaces(
        facade=facade,
        telegram_enabled=configuration.telegram_enabled,
    )

    return RuntimeBundle(
        runtime=runtime,
        interfaces=interfaces,
)
