from __future__ import annotations

import pytest

from execution.safety import ExecutionSafetyError, ExecutionSafety


def test_execution_safety_can_be_created() -> None:
    safety = ExecutionSafety()

    assert safety is not None


def test_live_execution_is_blocked_without_explicit_enablement() -> None:
    safety = ExecutionSafety()

    with pytest.raises(ExecutionSafetyError):
        safety.authorize_live_execution(
            confirmed=False,
            strict_mode=False,
        )


def test_live_execution_requires_confirmation() -> None:
    safety = ExecutionSafety()

    with pytest.raises(ExecutionSafetyError):
        safety.authorize_live_execution(
            confirmed=False,
            strict_mode=True,
        )


def test_live_execution_requires_strict_mode() -> None:
    safety = ExecutionSafety()

    with pytest.raises(ExecutionSafetyError):
        safety.authorize_live_execution(
            confirmed=True,
            strict_mode=False,
        )


def test_live_execution_can_be_authorized_when_requirements_are_met() -> None:
    safety = ExecutionSafety()

    result = safety.authorize_live_execution(
        confirmed=True,
        strict_mode=True,
    )

    assert result is True
