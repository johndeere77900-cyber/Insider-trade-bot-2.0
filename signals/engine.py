"""
Signal Engine boundary for Insider Trade Bot research pipeline.

Consumes ResearchFeatures and generates research-only SignalCandidate records.
This module is strictly isolated from live execution and cannot place trades or authorize execution.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Mapping

from features.engine import ResearchFeatures


@dataclass(frozen=True)
class SignalCandidate:
    """Research-only signal candidate record."""

    signal_id: str
    symbol: str
    signal_date: str
    direction: str
    score: float
    confidence: float | None
    feature_snapshot: Mapping[str, float]


class SignalEngine:
    """
    Research-only signal candidate generator.

    Consumes ResearchFeatures and produces SignalCandidate records for strategy backtesting.
    It MUST NOT:
    - place trades
    - call broker APIs or execution services
    - call Telegram
    - bypass risk controls
    - access future information
    """

    def generate(
        self,
        *,
        features: ResearchFeatures,
    ) -> SignalCandidate:
        feats = features.features

        buy_count = feats.get("insider_buy_count", 0.0)
        sell_count = feats.get("insider_sell_count", 0.0)
        tx_val = feats.get("total_transaction_value", 0.0)

        # Simple deterministic rules-based placeholder logic for research evaluation
        if buy_count > sell_count:
            direction = "long"
            score = min(1.0, 0.5 + (buy_count * 0.1))
            confidence = 0.8 if tx_val > 10000.0 else 0.5
        elif sell_count > buy_count:
            direction = "short"
            score = min(1.0, 0.5 + (sell_count * 0.1))
            confidence = 0.8 if tx_val > 10000.0 else 0.5
        else:
            direction = "neutral"
            score = 0.0
            confidence = 0.0

        signal_id = f"sig_{features.symbol}_{features.event_date}_{uuid.uuid4().hex[:8]}"

        return SignalCandidate(
            signal_id=signal_id,
            symbol=features.symbol,
            signal_date=features.event_date,
            direction=direction,
            score=score,
            confidence=confidence,
            feature_snapshot=dict(feats),
        )
