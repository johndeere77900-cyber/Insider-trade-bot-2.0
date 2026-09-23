"""
Core domain models for Insider Trade Bot.

These models represent normalized records moving through the system.
They are deliberately separate from database-specific code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class InsiderTransaction:
    """
    Normalized insider transaction record.
    """

    source: str
    accession_number: str
    issuer_cik: str

    issuer_name: Optional[str] = None

    insider_name: Optional[str] = None
    insider_cik: Optional[str] = None

    transaction_date: Optional[str] = None
    filing_date: Optional[str] = None

    form_type: Optional[str] = None
    transaction_code: Optional[str] = None

    shares: Optional[float] = None
    price: Optional[float] = None

    ownership_type: Optional[str] = None


@dataclass(frozen=True)
class MarketPrice:
    """
    Normalized historical market-price record.
    """

    symbol: str
    price_date: str

    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    adjusted_close: Optional[float] = None

    volume: Optional[float] = None

    source: str = ""


@dataclass(frozen=True)
class CorporateAction:
    """
    Normalized corporate-action record.

    Examples include stock splits, reverse splits, dividends, and other
    actions that can affect historical-price interpretation.
    """

    symbol: str
    action_type: str
    action_date: str

    ratio: Optional[str] = None
    cash_amount: Optional[float] = None

    source: str = ""


@dataclass(frozen=True)
class ResearchEvent:
    """
    Represents a research event used by the event-study layer.
    """

    event_key: str
    event_type: str

    symbol: Optional[str] = None
    event_date: Optional[str] = None

    methodology_version: str = "1.0"

    result_payload: str = ""


@dataclass(frozen=True)
class Signal:
    """
    Represents a research-derived trading signal candidate.

    A signal is not an order and does not authorize trading.
    """

    signal_key: str
    symbol: str
    signal_date: str

    signal_type: str

    score: Optional[float] = None

    rationale: Optional[str] = None

    methodology_version: str = "1.0"
