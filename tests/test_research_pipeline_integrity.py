"""
End-to-end research pipeline integrity tests for Insider Trade Bot.

Covers:
SEC event -> PIT event date -> RAW price -> PIT research price ->
future return -> feature snapshot -> signal candidate -> backtest trade.
"""

from __future__ import annotations

import pytest

from backtesting.engine import BacktestTrade, execute_portfolio_backtest
from features.engine import FeatureEngine
from research.price_adjustment import apply_point_in_time_adjustment
from research.research.event_study import PriceSeriesMode, calculate_event_return
from signals.engine import SignalEngine


def test_research_pipeline_end_to_end_integrity() -> None:
    # 1. SEC Event known after close on 2024-05-10
    sec_event = {
        "event_key": "sec_evt_1001",
        "symbol": "AAPL",
        "event_date": "2024-05-10",
        "event_price": 100.0,  # RAW market price on observation date
        "historical_transactions": [
            {
                "symbol": "AAPL",
                "filing_date": "2024-05-10",
                "transaction_code": "P",
                "shares": 5000.0,
                "price": 100.0,
            }
        ],
    }

    # 2. Market prices: RAW series
    raw_prices = {
        "2024-05-10": 100.0,
        "2024-06-05": 30.0,  # RAW price post-split
    }

    # 3. Corporate action: 4:1 split on 2024-06-01
    corporate_actions = [
        {
            "symbol": "AAPL",
            "action_type": "split",
            "action_date": "2024-06-01",
            "ratio": "4:1",
            "source": "fmp",
        }
    ]

    # 4. Event Study: Request POINT_IN_TIME_ADJUSTED price mode for research return
    event_return = calculate_event_return(
        event_key=sec_event["event_key"],
        symbol=sec_event["symbol"],
        event_date=sec_event["event_date"],
        event_price=sec_event["event_price"],
        prices=raw_prices,
        horizon_days=1,
        price_series_mode=PriceSeriesMode.POINT_IN_TIME_ADJUSTED,
        corporate_actions=corporate_actions,
    )

    # Return is continuous: (30 / 25 - 1) * 100 = +20%
    assert event_return.return_pct == pytest.approx(20.0)
    # RAW execution prices remain untouched!
    assert event_return.event_price == 100.0
    assert event_return.future_price == 30.0

    # 5. Feature Engine
    feature_engine = FeatureEngine()
    features = feature_engine.build_features(event=sec_event)
    assert features.features["insider_buy_count"] == 1.0
    assert features.features["total_transaction_value"] == 500000.0

    # 6. Signal Engine
    signal_engine = SignalEngine()
    signal = signal_engine.generate(features=features)
    assert signal.direction == "long"
    assert signal.score > 0.0
    assert signal.signal_date == "2024-05-10"
    assert signal.confidence is None

    # 7. Backtest execution using RAW prices on eligible future observation date
    backtest_trade = BacktestTrade(
        trade_id="bt_1",
        symbol=signal.symbol,
        side="buy",
        entry_date="2024-05-13",  # First available trading day strictly after filing
        exit_date="2024-06-05",
        entry_price=100.0,  # RAW execution price
        exit_price=30.0,   # RAW execution price
        quantity=100.0,
        fees=10.0,
        slippage=5.0,
    )

    bt_result = execute_portfolio_backtest([backtest_trade], initial_capital=100000.0)
    assert bt_result.trade_count == 1
    assert bt_result.total_fees == 10.0
    assert bt_result.total_slippage == 5.0
    assert bt_result.max_drawdown_pct > 0.0
