"""
Unit tests for Feature Engine and Signal Engine boundaries.
"""

from __future__ import annotations

import pytest

from features.engine import FeatureEngine, ResearchFeatures
from signals.engine import SignalCandidate, SignalEngine


def test_feature_engine_builds_features_with_provenance() -> None:
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
                "filing_date": "2024-06-01",  # Future date relative to event_date -> excluded!
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
    assert res.features["days_since_prior_insider_event"] == 9.0
    assert "insider_transaction_count" in res.feature_sources


def test_signal_engine_generates_research_signal_candidate() -> None:
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
    feats = feat_engine.build_features(event=event)

    sig_engine = SignalEngine()
    cand = sig_engine.generate(features=feats)

    assert cand.symbol == "MSFT"
    assert cand.signal_date == "2024-05-10"
    assert cand.direction == "long"
    assert cand.score > 0.0
    assert cand.feature_snapshot["insider_buy_count"] == 1.0
    assert not hasattr(sig_engine, "execute_trade")
    assert not hasattr(sig_engine, "TradingService")
