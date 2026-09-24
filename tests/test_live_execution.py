from __future__ import annotations

from execution.live_adapter import LiveExecutionAdapter
from execution.mode import ExecutionMode


def test_live_execution_adapter_can_be_created() -> None:
    adapter = LiveExecutionAdapter()

    assert adapter is not None


def test_live_execution_adapter_declares_live_mode() -> None:
    adapter = LiveExecutionAdapter()

    assert adapter.mode == ExecutionMode.LIVE


def test_live_execution_adapter_is_not_automatically_enabled() -> None:
    adapter = LiveExecutionAdapter()

    assert adapter.is_enabled() is False
