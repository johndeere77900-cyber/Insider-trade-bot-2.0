"""
Natural-language request interpretation for Insider Trade Bot 2.0.

This module provides a deterministic first-layer interpreter for ordinary
Telegram messages. It does not make investment decisions and does not
execute trades.

Complex natural-language interpretation can later be connected to an
external or local AI layer without changing the Telegram transport layer.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class NaturalLanguageRequest:
    """Normalized interpretation of an ordinary Telegram message."""

    intent: str
    text: str
    symbol: str | None = None
    quantity: float | None = None


class NaturalLanguageInterpreter:
    """Interpret common user requests deterministically."""

    _SYMBOL_PATTERN = re.compile(
        r"\b[A-Z]{1,6}(?:\.[A-Z]{1,3})?\b"
    )

    _QUANTITY_PATTERN = re.compile(
        r"\b(?:buy|sell)\s+"
        r"(\d+(?:\.\d+)?)\s+"
        r"(?:shares?|units?)\b",
        re.IGNORECASE,
    )

    def interpret(self, text: str) -> NaturalLanguageRequest:
        """Interpret an ordinary natural-language message."""
        if text is None:
            raise ValueError("Natural-language text cannot be None.")

        normalized = text.strip()

        if not normalized:
            raise ValueError(
                "Natural-language text cannot be empty."
            )

        lowered = normalized.lower()

        intent = self._detect_intent(lowered)
        symbol = self._extract_symbol(normalized)
        quantity = self._extract_quantity(normalized)

        return NaturalLanguageRequest(
            intent=intent,
            text=normalized,
            symbol=symbol,
            quantity=quantity,
        )

    @staticmethod
    def _detect_intent(text: str) -> str:
        """Determine the broad request intent."""
        if any(
            phrase in text
            for phrase in (
                "buy ",
                "purchase ",
            )
        ):
            return "trade_buy"

        if any(
            phrase in text
            for phrase in (
                "sell ",
            )
        ):
            return "trade_sell"

        if any(
            phrase in text
            for phrase in (
                "research",
                "analyze",
                "analysis",
                "investigate",
                "look into",
            )
        ):
            return "research"

        if any(
            phrase in text
            for phrase in (
                "signal",
                "signals",
                "insider activity",
            )
        ):
            return "signal"

        if any(
            phrase in text
            for phrase in (
                "backtest",
                "back-test",
                "back test",
            )
        ):
            return "backtest"

        if any(
            phrase in text
            for phrase in (
                "portfolio",
                "positions",
                "holdings",
            )
        ):
            return "portfolio"

        if any(
            phrase in text
            for phrase in (
                "status",
                "health",
                "running",
            )
        ):
            return "status"

        if any(
            phrase in text
            for phrase in (
                "help",
                "what can you do",
                "commands",
            )
        ):
            return "help"

        return "unknown"

    def _extract_symbol(self, text: str) -> str | None:
        """Extract a likely ticker symbol from the request."""
        matches = self._SYMBOL_PATTERN.findall(text)

        if not matches:
            return None

        ignored = {
            "BUY",
            "SELL",
            "THE",
            "AND",
            "FOR",
            "FROM",
            "WITH",
            "WHAT",
            "WHEN",
            "WHERE",
            "SHOW",
            "GIVE",
            "HELP",
            "BACK",
            "TEST",
        }

        for match in matches:
            if match.upper() not in ignored:
                return match.upper()

        return None

    @staticmethod
    def _extract_quantity(text: str) -> float | None:
        """Extract a requested trade quantity when explicitly provided."""
        match = NaturalLanguageInterpreter._QUANTITY_PATTERN.search(text)

        if not match:
            return None

        try:
            quantity = float(match.group(1))
        except ValueError:
            return None

        if quantity <= 0:
            return None

        return quantity
