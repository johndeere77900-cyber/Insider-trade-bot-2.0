from __future__ import annotations

from execution.mode import ExecutionMode
from execution.paper_adapter import PaperExecutionAdapter


def test_paper_execution_adapter_can_be_created() -> None:
    adapter = PaperExecutionAdapter()

    assert adapter is not None


def test_paper_execution_adapter_uses_paper_mode() -> None:
    adapter = PaperExecutionAdapter()

    assert adapter.mode == ExecutionMode.PAPER


def test_paper_execution_adapter_does_not_use_live_mode() -> None:
    adapter = PaperExecutionAdapter()

    assert adapter.mode != ExecutionMode.LIVE
