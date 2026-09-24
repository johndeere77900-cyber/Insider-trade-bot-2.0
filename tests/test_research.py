from __future__ import annotations

from research.event_study import EventStudyEngine


def test_event_study_engine_can_calculate_returns() -> None:
    engine = EventStudyEngine()

    prices = [
        {"date": "2026-01-01", "close": 100.0},
        {"date": "2026-01-02", "close": 105.0},
        {"date": "2026-01-03", "close": 110.0},
    ]

    result = engine.calculate_returns(prices)

    assert result is not None
    assert len(result) == 2
    assert result[0]["return"] == 0.05
    assert result[1]["return"] == (110.0 / 105.0) - 1


def test_event_study_handles_empty_price_data() -> None:
    engine = EventStudyEngine()

    result = engine.calculate_returns([])

    assert result == []


def test_event_study_handles_single_price() -> None:
    engine = EventStudyEngine()

    result = engine.calculate_returns(
        [
            {"date": "2026-01-01", "close": 100.0},
        ]
    )

    assert result == []
