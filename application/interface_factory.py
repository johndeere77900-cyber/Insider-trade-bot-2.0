"""
External-interface factory.

Creates interface bridges from the assembled application facade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from application.facade import ApplicationFacade
from application.telegram_bridge import TelegramApplicationBridge


@dataclass(frozen=True)
class ApplicationInterfaces:
    """Available external-interface bridges."""

    telegram: Optional[TelegramApplicationBridge] = None


def create_interfaces(
    *,
    facade: ApplicationFacade,
    telegram_enabled: bool = False,
) -> ApplicationInterfaces:
    """
    Create external interface bridges.

    The factory does not start polling, networking, or trading.
    """

    if facade is None:
        raise ValueError("facade is required.")

    telegram_bridge = None

    if telegram_enabled:
        telegram_bridge = TelegramApplicationBridge(
            facade=facade,
        )

    return ApplicationInterfaces(
        telegram=telegram_bridge,
    )
