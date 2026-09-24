from __future__ import annotations

from outcomes.engine import OutcomeEngine


def test_outcome_engine_can_be_created() -> None:
    engine = OutcomeEngine()

    assert engine is not None


def test_outcome_engine_handles_empty_outcomes() -> None:
    engine = OutcomeEngine()

    result = engine.evaluate([])

    assert result is not None


def test_outcome_engine_evaluates_positive_result() -> None:
    engine = OutcomeEngine()

    result = engine.evaluate(
        [
            {
                "entry_price": 100.0,
                "exit_price": 110.0,
            }
        ]
    )

    assert result is not None
