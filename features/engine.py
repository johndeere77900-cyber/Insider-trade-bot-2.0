"""
Feature Engine boundary for Insider Trade Bot research pipeline.

Computes point-in-time features from SEC insider events and context with explicit
provenance mapping (`feature_sources`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class ResearchFeatures:
    """Immutable point-in-time feature snapshot with provenance mapping."""

    symbol: str
    event_date: str
    features: Mapping[str, float]
    feature_sources: Mapping[str, str]


class FeatureEngine:
    """
    Provider-neutral feature engine.

    Computes point-in-time features strictly using available historical inputs.
    Never uses future data, machine learning, or signal scoring.
    """

    def build_features(
        self,
        *,
        event: Mapping[str, object],
        research_context: Mapping[str, object] | None = None,
    ) -> ResearchFeatures:
        ctx = research_context or {}

        symbol = str(event.get("symbol") or event.get("ticker") or "").strip().upper()
        if not symbol:
            raise ValueError("Event must contain a valid symbol.")

        event_date = str(event.get("event_date") or event.get("filing_date") or event.get("transaction_date") or "").strip()
        if not event_date:
            raise ValueError("Event must contain a valid event_date.")

        # Extract insider transactions if present in context or event
        has_history = ("historical_transactions" in ctx) or ("historical_transactions" in event)
        history = ctx.get("historical_transactions") if "historical_transactions" in ctx else event.get("historical_transactions")
        if not has_history:
            history = [event]

        insider_tx_count = 0.0
        insider_buy_count = 0.0
        insider_sell_count = 0.0
        total_tx_value = 0.0
        prior_event_dates: list[str] = []

        if isinstance(history, Sequence):
            for tx in history:
                if not isinstance(tx, Mapping):
                    continue

                tx_symbol = str(tx.get("symbol") or tx.get("ticker") or "").strip().upper()
                if tx_symbol and tx_symbol != symbol:
                    continue

                # Enforce strict point-in-time: information availability is governed by filing_date <= event_date
                tx_filing_date = str(tx.get("filing_date") or "").strip()
                if not tx_filing_date or tx_filing_date > event_date:
                    continue

                insider_tx_count += 1.0

                code = str(tx.get("transaction_code") or tx.get("transaction_type") or "").strip().upper()
                acq_disp = str(tx.get("acquired_disposed") or "").strip().upper()

                if code == "P" or acq_disp == "A":
                    insider_buy_count += 1.0
                elif code == "S" or acq_disp == "D":
                    insider_sell_count += 1.0

                shares = float(tx.get("shares") or 0.0)
                price = float(tx.get("price") or tx.get("price_per_share") or 0.0)
                if shares > 0 and price > 0:
                    total_tx_value += shares * price

                if tx_filing_date < event_date:
                    prior_event_dates.append(tx_filing_date)

        days_since_prior = -1.0
        if prior_event_dates:
            prior_event_dates.sort()
            import datetime
            try:
                d_event = datetime.datetime.strptime(event_date, "%Y-%m-%d")
                d_prior = datetime.datetime.strptime(prior_event_dates[-1], "%Y-%m-%d")
                days_since_prior = float((d_event - d_prior).days)
            except ValueError:
                days_since_prior = -1.0

        features = {
            "insider_transaction_count": insider_tx_count,
            "insider_buy_count": insider_buy_count,
            "insider_sell_count": insider_sell_count,
            "total_transaction_value": total_tx_value,
            "days_since_prior_insider_event": days_since_prior,
        }

        feature_sources = {
            "insider_transaction_count": "sec_insider_transactions.filing_date",
            "insider_buy_count": "sec_insider_transactions.transaction_code",
            "insider_sell_count": "sec_insider_transactions.transaction_code",
            "total_transaction_value": "sec_insider_transactions.shares*price",
            "days_since_prior_insider_event": "sec_insider_transactions.filing_date",
        }

        return ResearchFeatures(
            symbol=symbol,
            event_date=event_date,
            features=features,
            feature_sources=feature_sources,
        )
