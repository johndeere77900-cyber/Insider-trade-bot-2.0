"""
Unit tests for research/price_adjustment.py.
"""

from __future__ import annotations

import pytest

from research.price_adjustment import (
    PriceAdjustmentFactor,
    UnsupportedCorporateActionError,
    apply_point_in_time_adjustment,
)


def test_price_adjustment_4_for_1_split() -> None:
    actions = [
        {
            "symbol": "AAPL",
            "action_type": "split",
            "action_date": "2024-06-01",
            "ratio": "4:1",
            "source": "fmp",
        }
    ]

    # Price before split, as_of_date after split -> adjusted (100 / 4 = 25)
    adj_price = apply_point_in_time_adjustment(
        symbol="AAPL",
        price_date="2024-05-01",
        raw_price=100.0,
        corporate_actions=actions,
        as_of_date="2024-06-05",
    )
    assert adj_price == 25.0

    # Price after split -> unchanged
    adj_price_post = apply_point_in_time_adjustment(
        symbol="AAPL",
        price_date="2024-06-02",
        raw_price=25.0,
        corporate_actions=actions,
        as_of_date="2024-06-05",
    )
    assert adj_price_post == 25.0


def test_price_adjustment_future_action_not_applied_before_as_of_date() -> None:
    actions = [
        {
            "symbol": "AAPL",
            "action_type": "split",
            "action_date": "2024-06-01",
            "ratio": "4:1",
            "source": "fmp",
        }
    ]

    # As of May 15, 2024, the June 1 split date is in the future relative to as_of_date!
    adj_price = apply_point_in_time_adjustment(
        symbol="AAPL",
        price_date="2024-05-01",
        raw_price=100.0,
        corporate_actions=actions,
        as_of_date="2024-05-15",
    )
    assert adj_price == 100.0


def test_price_adjustment_ignores_other_symbols() -> None:
    actions = [
        {
            "symbol": "MSFT",
            "action_type": "split",
            "action_date": "2024-06-01",
            "ratio": "4:1",
            "source": "fmp",
        }
    ]

    adj_price = apply_point_in_time_adjustment(
        symbol="AAPL",
        price_date="2024-05-01",
        raw_price=100.0,
        corporate_actions=actions,
        as_of_date="2024-06-05",
    )
    assert adj_price == 100.0


def test_price_adjustment_deduplicates_actions() -> None:
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

    adj_price = apply_point_in_time_adjustment(
        symbol="AAPL",
        price_date="2024-05-01",
        raw_price=100.0,
        corporate_actions=actions,
        as_of_date="2024-06-05",
    )
    assert adj_price == 25.0


def test_price_adjustment_unsupported_action_raises_error() -> None:
    actions = [
        {
            "symbol": "AAPL",
            "action_type": "spin_off",
            "action_date": "2024-06-01",
            "ratio": "1:1",
            "source": "fmp",
        }
    ]

    with pytest.raises(UnsupportedCorporateActionError, match="Unsupported corporate action type"):
        apply_point_in_time_adjustment(
            symbol="AAPL",
            price_date="2024-05-01",
            raw_price=100.0,
            corporate_actions=actions,
            as_of_date="2024-06-05",
        )


def test_price_adjustment_missing_ratio_raises_error() -> None:
    actions = [
        {
            "symbol": "AAPL",
            "action_type": "split",
            "action_date": "2024-06-01",
            "source": "fmp",
        }
    ]

    with pytest.raises(UnsupportedCorporateActionError, match="missing required 'ratio'"):
        apply_point_in_time_adjustment(
            symbol="AAPL",
            price_date="2024-05-01",
            raw_price=100.0,
            corporate_actions=actions,
            as_of_date="2024-06-05",
        )
