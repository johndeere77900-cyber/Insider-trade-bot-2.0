"""
Unit tests for event study engine with PriceSeriesMode and corporate actions.
"""

from __future__ import annotations

import pytest

from research.price_adjustment import UnsupportedCorporateActionError
from research.research.event_study import (
    PriceSeriesMode,
    calculate_event_return,
    run_event_study,
)


def test_event_study_raw_mode() -> None:
    prices = {
        "2024-05-01": 100.0,
        "2024-05-02": 110.0,
    }

    res = calculate_event_return(
        event_key="evt1",
        symbol="AAPL",
        event_date="2024-05-01",
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
    # Execution price fields remain RAW!
    assert res.event_price == 100.0
    assert res.future_price == 30.0


def test_future_corporate_action_not_applied_before_action_date() -> None:
    prices = {
        "2024-05-01": 100.0,
        "2024-05-15": 110.0,
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

    # As of May 15, the June 1 split is in the future and NOT applied yet.
    # Return: (110 / 100 - 1) * 100 = 10%
    assert res.return_pct == pytest.approx(10.0)


def test_unsupported_corporate_action_raises_error() -> None:
    prices = {
        "2024-05-01": 100.0,
        "2024-06-02": 110.0,
    }
    actions = [
        {
            "symbol": "AAPL",
            "action_type": "spin_off",
            "action_date": "2024-06-01",
            "source": "fmp",
        }
    ]

    with pytest.raises(UnsupportedCorporateActionError):
        calculate_event_return(
            event_key="evt1",
            symbol="AAPL",
            event_date="2024-05-01",
            event_price=100.0,
            prices=prices,
            horizon_days=1,
            price_series_mode=PriceSeriesMode.POINT_IN_TIME_ADJUSTED,
            corporate_actions=actions,
        )


def test_no_double_adjustment() -> None:
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
        },
        {
            "symbol": "AAPL",
            "action_type": "split",
            "action_date": "2024-06-01",
            "ratio": "4:1",
            "source": "fmp",
        },
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

    # Deduplicated action -> return is 20% (not 380%)
    assert res.return_pct == pytest.approx(20.0)
