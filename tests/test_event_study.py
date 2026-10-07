"""
Unit tests for event study engine with PriceSeriesMode and look-ahead prevention.
"""

from __future__ import annotations

import pytest

from research.price_adjustment import UnsupportedCorporateActionError
from research.research.event_study import (
    PriceSeriesMode,
    calculate_event_return,
    find_horizon_price,
    run_event_study,
)


def test_event_study_no_same_day_look_ahead() -> None:
    # Event date is 2024-05-10.
    # Same day observation exists (2024-05-10: 100.0).
    # Next trading day observation is 2024-05-13: 105.0.
    prices = {
        "2024-05-10": 100.0,
        "2024-05-13": 105.0,
        "2024-05-14": 110.0,
    }

    # Horizon = 1 observation after event date must select 2024-05-13, NOT same-day 2024-05-10!
    future_date, future_price = find_horizon_price(prices, "2024-05-10", horizon_days=1)
    assert future_date == "2024-05-13"
    assert future_price == 105.0


def test_event_study_raw_mode_preserves_raw_prices() -> None:
    prices = {
        "2024-05-10": 100.0,
        "2024-05-13": 110.0,
    }

    res = calculate_event_return(
        event_key="evt1",
        symbol="AAPL",
        event_date="2024-05-10",
        event_price=100.0,
        prices=prices,
        horizon_days=1,
        price_series_mode=PriceSeriesMode.RAW,
    )

    assert res.return_pct == pytest.approx(10.0)
    assert res.event_price == 100.0
    assert res.future_price == 110.0


def test_event_study_point_in_time_adjusted_mode_split() -> None:
    prices = {
        "2024-05-01": 100.0,
        "2024-06-02": 30.0,
    }
    actions = [
        {
            "symbol": "AAPL",
            "action_type": "split",
            "action_date": "2024-06-01",
            "ratio": "4:1",
            "source": "fmp",
        }
    ]

    res = calculate_event_return(
        event_key="evt1",
        symbol="AAPL",
        event_date="2024-05-01",
        event_price=100.0,
        prices=prices,
        horizon_days=1,
        price_series_mode=PriceSeriesMode.POINT_IN_TIME_ADJUSTED,
        corporate_actions=actions,
    )

    # Pre-split $100 -> adjusted to $25. Future price $30 post-split -> adjusted to $30.
    # Continuous return: (30 / 25 - 1) * 100 = +20%
    assert res.return_pct == pytest.approx(20.0)
    # Raw source prices on EventReturn remain untouched!
    assert res.event_price == 100.0
    assert res.future_price == 30.0
