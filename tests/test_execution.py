from __future__ import annotations

from execution.mode import ExecutionMode


def test_execution_mode_contains_paper_and_live() -> None:
    assert hasattr(ExecutionMode, "PAPER")
    assert hasattr(ExecutionMode, "LIVE")


def test_execution_mode_values_are_distinct() -> None:
    assert ExecutionMode.PAPER != ExecutionMode.LIVE


def test_paper_mode_is_not_live_mode() -> None:
    assert ExecutionMode.PAPER is not ExecutionMode.LIVE
