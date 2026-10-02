"""
Application command definitions.

Defines normalized commands that can be submitted by Telegram, CLI, or
future interfaces without coupling the command model to any one interface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class ApplicationCommand:
    """Base normalized application command."""

    name: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    request_id: Optional[str] = None
    user_id: Optional[str] = None
    source: str = "unknown"


@dataclass(frozen=True)
class ResearchCommand(ApplicationCommand):
    """Request for historical or event-study research."""

    name: str = "research"


@dataclass(frozen=True)
class SignalCommand(ApplicationCommand):
    """Request for signal generation."""

    name: str = "signal"


@dataclass(frozen=True)
class BacktestCommand(ApplicationCommand):
    """Request for backtesting."""

    name: str = "backtest"


@dataclass(frozen=True)
class PortfolioCommand(ApplicationCommand):
    """Request for portfolio information."""

    name: str = "portfolio"


@dataclass(frozen=True)
class StatusCommand(ApplicationCommand):
    """Request for application status."""

    name: str = "status"


@dataclass(frozen=True)
class TradeCommand(ApplicationCommand):
    """
    Structured trading request.

    Trading commands remain subject to the execution service, safety layer,
    risk controls, and execution-mode restrictions.
    """

    name: str = "trade"
    parameters: Mapping[str, Any] = field(default_factory=dict)
    execution_mode: Optional[str] = None


@dataclass(frozen=True)
class HistoricalAcquisitionCommand(ApplicationCommand):
    """Request for historical SEC dataset acquisition."""

    name: str = "historical acquisition"
