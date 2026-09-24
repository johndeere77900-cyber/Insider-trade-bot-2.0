from __future__ import annotations

import pytest

from risk.controls import RiskControlError, RiskControls


def test_risk_controls_can_be_created() -> None:
    controls = RiskControls()

    assert controls is not None


def test_order_within_limit_is_allowed() -> None:
    controls = RiskControls(
        max_order_value=10_000.0,
        max_position_value=50_000.0,
    )

    result = controls.check_order(
        symbol="AAPL",
        quantity=10,
        price=100.0,
    )

    assert result is True


def test_order_above_limit_is_rejected() -> None:
    controls = RiskControls(
        max_order_value=1_000.0,
        max_position_value=50_000.0,
    )

    with pytest.raises(RiskControlError):
        controls.check_order(
            symbol="AAPL",
            quantity=20,
            price=100.0,
        )


def test_position_above_limit_is_rejected() -> None:
    controls = RiskControls(
        max_order_value=10_000.0,
        max_position_value=1_000.0,
    )

    with pytest.raises(RiskControlError):
        controls.check_order(
            symbol="AAPL",
            quantity=20,
            price=100.0,
  )
