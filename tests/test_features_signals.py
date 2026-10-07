"""
Unit tests for Feature Engine and Signal Engine boundaries.
"""

from __future__ import annotations

import pytest

from features.engine import FeatureEngine, ResearchFeatures
from signals.engine import SignalCandidate, SignalEngine


def test_feature_engine_filing_date_pit_filtering() -> None:
    engine = FeatureEngine()
    event = {
        "symbol": "AAPL",
        "event_date": "2024-05-10",
        "historical_transactions": [
            {
                "symbol": "AAPL",
                "filing_date": "2024-05-01",
                "transaction_code": "P",
                "shares": 100.0,
                "price": 150.0,
            },
            {
                "symbol": "AAPL",
                "filing_date": "2024-05-10",
                "transaction_code": "P",
                "shares": 200.0,
                "price": 155.0,
            },
            {
                "symbol": "AAPL",
                "filing_date": "2024-05-15",  # Future filing date > event_date -> excluded!
                "transaction_code": "S",
                "shares": 500.0,
                "price": 160.0,
            },
        ],
    }

    res = engine.build_features(event=event)

    assert res.symbol == "AAPL"
    assert res.event_date == "2024-05-10"
    assert res.features["insider_transaction_count"] == 2.0
    assert res.features["insider_buy_count"] == 2.0
    assert res.features["insider_sell_count"] == 0.0
    assert res.features["total_transaction_value"] == 100.0 * 150.0 + 200.0 * 155.0


def test_signal_engine_generates_deterministic_signal_id() -> None:
    feat_engine = FeatureEngine()
    event = {
        "symbol": "MSFT",
        "event_date": "2024-05-10",
        "historical_transactions": [
            {
                "symbol": "MSFT",
                "filing_date": "2024-05-10",
                "transaction_code": "P",
                "shares": 1000.0,
                "price": 400.0,
            }
        ],
    }
    feats1 = feat_engine.build_features(event=event)
    feats2 = feat_engine.build_features(event=event)

    sig_engine = SignalEngine()
    cand1 = sig_engine.generate(features=feats1)
    cand2 = sig_engine.generate(features=feats2)

    assert cand1.signal_id == cand2.signal_id
    assert cand1.direction == "long"
