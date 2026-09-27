from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RiskLimits:
    max_position_value: float
    max_total_exposure: float
    max_order_value: float
    max_open_positions: int = 10


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: float
    reference_price: float


@dataclass(frozen=True)
class RiskCheckResult:
    approved: bool
    order_value: float
    existing_exposure: float
    projected_exposure: float
    reasons: tuple[str, ...]


class RiskControlError(Exception):
    """Base exception for risk-control failures."""


def _validate_positive(
    value: float,
    field_name: str,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RiskControlError(
            f"{field_name} must be numeric."
        )

    if value <= 0:
        raise RiskControlError(
            f"{field_name} must be greater than zero."
        )


def validate_limits(
    limits: RiskLimits,
) -> None:
    if not isinstance(limits, RiskLimits):
        raise TypeError(
            "limits must be a RiskLimits instance."
        )

    _validate_positive(
        limits.max_position_value,
        "max_position_value",
    )

    _validate_positive(
        limits.max_total_exposure,
        "max_total_exposure",
    )

    _validate_positive(
        limits.max_order_value,
        "max_order_value",
    )

    if limits.max_open_positions < 1:
        raise RiskControlError(
            "max_open_positions must be at least 1."
        )


def position_value(
    position: Position,
) -> float:
    if not isinstance(position, Position):
        raise TypeError(
            "position must be a Position instance."
        )

    _validate_positive(
        position.quantity,
        "quantity",
    )

    _validate_positive(
        position.reference_price,
        "reference_price",
    )

    return (
        float(position.quantity)
        * float(position.reference_price)
    )


def calculate_total_exposure(
    positions: Iterable[Position],
) -> float:
    total = 0.0

    for position in positions:
        total += position_value(position)

    return total


def count_open_positions(
    positions: Iterable[Position],
) -> int:
    return sum(
        1
        for _ in positions
    )


def check_order(
    *,
    limits: RiskLimits,
    positions: Iterable[Position],
    symbol: str,
    quantity: float,
    reference_price: float,
) -> RiskCheckResult:

    validate_limits(limits)

    normalized_symbol = str(symbol).strip().upper()

    if not normalized_symbol:
        raise RiskControlError(
            "symbol cannot be empty."
        )

    _validate_positive(
        quantity,
        "quantity",
    )

    _validate_positive(
        reference_price,
        "reference_price",
    )

    position_list = list(positions)

    for position in position_list:
        if not isinstance(position, Position):
            raise TypeError(
                "Every position must be a Position instance."
            )

    order_value = (
        float(quantity)
        * float(reference_price)
    )

    existing_exposure = calculate_total_exposure(
        position_list
    )

    projected_exposure = (
        existing_exposure
        + order_value
    )

    reasons: list[str] = []

    if order_value > limits.max_order_value:
        reasons.append(
            "Order value exceeds the maximum order-value limit."
        )

    existing_symbol_position = sum(
        position_value(position)
        for position in position_list
        if position.symbol.strip().upper()
        == normalized_symbol
    )

    projected_symbol_position = (
        existing_symbol_position
        + order_value
    )

    if projected_symbol_position > limits.max_position_value:
        reasons.append(
            "Projected position value exceeds the maximum "
            "position-value limit."
        )

    if projected_exposure > limits.max_total_exposure:
        reasons.append(
            "Projected total exposure exceeds the maximum "
            "total-exposure limit."
        )

    symbol_already_open = any(
        position.symbol.strip().upper()
        == normalized_symbol
        for position in position_list
    )

    projected_open_positions = len(position_list)

    if not symbol_already_open:
        projected_open_positions += 1

    if projected_open_positions > limits.max_open_positions:
        reasons.append(
            "Projected open-position count exceeds the configured limit."
        )

    return RiskCheckResult(
        approved=not reasons,
        order_value=order_value,
        existing_exposure=existing_exposure,
        projected_exposure=projected_exposure,
        reasons=tuple(reasons),
    )


def require_risk_approval(
    result: RiskCheckResult,
) -> None:
    if not isinstance(result, RiskCheckResult):
        raise TypeError(
            "result must be a RiskCheckResult."
        )

    if result.approved:
        return

    raise RiskControlError(
        "Risk check rejected the proposed order: "
        + "; ".join(result.reasons)
    )


class RiskControls:
    """
    Compatibility interface used by the application/test layer.

    This wrapper converts the class-based API into the existing
    deterministic risk-control functions above.
    """

    def __init__(
        self,
        *,
        max_order_value: float = 10_000.0,
        max_position_value: float = 50_000.0,
        max_total_exposure: float = 100_000.0,
        max_open_positions: int = 10,
    ) -> None:

        self.limits = RiskLimits(
            max_position_value=float(max_position_value),
            max_total_exposure=float(max_total_exposure),
            max_order_value=float(max_order_value),
            max_open_positions=int(max_open_positions),
        )

        validate_limits(self.limits)

    def check_order(
        self,
        *,
        symbol: str,
        quantity: float,
        price: float,
    ) -> bool:

        result = check_order(
            limits=self.limits,
            positions=[],
            symbol=symbol,
            quantity=quantity,
            reference_price=price,
        )

        require_risk_approval(result)

        return True
