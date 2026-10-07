"""
Unit tests for chronological train/test splitting in backtesting/splits.py.
"""

from __future__ import annotations

import pytest

from backtesting.splits import BacktestSplit, chronological_split


def test_chronological_split_success() -> None:
    records = [
        {"event_date": "2024-01-02", "val": 1},
        {"event_date": "2024-01-10", "val": 2},
        {"event_date": "2024-02-01", "val": 3},
        {"event_date": "2024-02-15", "val": 4},
    ]

    train, test = chronological_split(
        records,
        train_end="2024-01-15",
        test_start="2024-02-01",
    )

    assert len(train) == 2
    assert [r["val"] for r in train] == [1, 2]

    assert len(test) == 2
    assert [r["val"] for r in test] == [3, 4]


def test_chronological_split_invalid_boundary_raises_error() -> None:
    records = [{"event_date": "2024-01-02"}]

    with pytest.raises(ValueError, match="must be strictly before"):
        chronological_split(
            records,
            train_end="2024-02-01",
            test_start="2024-01-15",
        )
