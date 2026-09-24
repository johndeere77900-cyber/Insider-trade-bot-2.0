"""
Signal engine for Insider Trade Bot.

This module converts research observations into structured signal
candidates. It does not place orders and does not authorize live trading.

Signal generation is intentionally deterministic and auditable: the same
inputs and methodology version should produce the same signal result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from core.hashing import sha256_record
from core.models import Signal
from research.research.event_study import EventStudySummary

@dataclass(frozen=True)
class SignalCriteria:
    """
    Explicit criteria used to determine whether a research result can
    produce a signal candidate.

    These thresholds are methodology parameters, not guarantees of future
    performance.
    """

    minimum_event_count: int = 30
    minimum_positive_event_rate_pct: float = 55.0
    minimum_mean_return_pct: float = 0.0


@dataclass(frozen=True)
class SignalDecision:
    """
    Result of evaluating one research summary against signal criteria.
    """

    qualified: bool

    event_count: int
    positive_event_rate_pct: float | None
    mean_return_pct: float | None

    reasons: tuple[str, ...]


def evaluate_event_study(
    summary: EventStudySummary,
    criteria: SignalCriteria,
) -> SignalDecision:
    """
    Evaluate an event-study summary against explicit signal criteria.

    Every criterion is checked independently. A signal qualifies only when
    all required criteria are satisfied.
    """

    if criteria.minimum_event_count < 1:
        raise ValueError(
            "minimum_event_count must be at least 1."
        )

    reasons: list[str] = []

    if summary.event_count < criteria.minimum_event_count:
        reasons.append(
            "Insufficient event count."
        )

    if summary.positive_event_rate_pct is None:
        reasons.append(
            "Positive-event rate is unavailable."
        )
    elif (
        summary.positive_event_rate_pct
        < criteria.minimum_positive_event_rate_pct
    ):
        reasons.append(
            "Positive-event rate is below the required threshold."
        )

    if summary.mean_return_pct is None:
        reasons.append(
            "Mean return is unavailable."
        )
    elif (
        summary.mean_return_pct
        < criteria.minimum_mean_return_pct
    ):
        reasons.append(
            "Mean return is below the required threshold."
        )

    return SignalDecision(
        qualified=not reasons,
        event_count=summary.event_count,
        positive_event_rate_pct=(
            summary.positive_event_rate_pct
        ),
        mean_return_pct=summary.mean_return_pct,
        reasons=tuple(reasons),
    )


def calculate_signal_score(
    summary: EventStudySummary,
) -> float | None:
    """
    Calculate a deterministic descriptive signal score.

    The score combines:
        - positive-event rate
        - mean return

    It is a research metric only. It is not a probability, guarantee,
    expected profit, or trading instruction.
    """

    if (
        summary.positive_event_rate_pct is None
        or summary.mean_return_pct is None
    ):
        return None

    return (
        summary.positive_event_rate_pct
        + summary.mean_return_pct
    )


def create_signal(
    *,
    symbol: str,
    signal_date: str,
    signal_type: str,
    summary: EventStudySummary,
    methodology_version: str,
    criteria: SignalCriteria,
) -> Signal | None:
    """
    Create a signal candidate if the research summary qualifies.

    Returns:
        Signal when all criteria pass.
        None when the research result does not qualify.
    """

    normalized_symbol = str(
        symbol
    ).strip()

    if not normalized_symbol:
        raise ValueError(
            "symbol cannot be empty."
        )

    normalized_date = str(
        signal_date
    ).strip()

    if not normalized_date:
        raise ValueError(
            "signal_date cannot be empty."
        )

    normalized_type = str(
        signal_type
    ).strip()

    if not normalized_type:
        raise ValueError(
            "signal_type cannot be empty."
        )

    normalized_methodology = str(
        methodology_version
    ).strip()

    if not normalized_methodology:
        raise ValueError(
            "methodology_version cannot be empty."
        )

    decision = evaluate_event_study(
        summary,
        criteria,
    )

    if not decision.qualified:
        return None

    score = calculate_signal_score(
        summary
    )

    signal_identity = {
        "symbol": normalized_symbol,
        "signal_date": normalized_date,
        "signal_type": normalized_type,
        "methodology_version": normalized_methodology,
        "horizon_days": summary.horizon_days,
        "event_count": summary.event_count,
    }

    signal_key = sha256_record(
        signal_identity
    )

    rationale = (
        "Qualified from event-study research. "
        f"Events={summary.event_count}; "
        f"positive_rate="
        f"{summary.positive_event_rate_pct:.4f}%; "
        f"mean_return="
        f"{summary.mean_return_pct:.4f}%; "
        f"horizon={summary.horizon_days} observations."
    )

    return Signal(
        signal_key=signal_key,
        symbol=normalized_symbol,
        signal_date=normalized_date,
        signal_type=normalized_type,
        score=score,
        rationale=rationale,
        methodology_version=normalized_methodology,
    )


def create_signal_batch(
    *,
    symbol: str,
    signal_date: str,
    signal_type: str,
    summary: EventStudySummary,
    methodology_version: str,
    criteria: SignalCriteria,
) -> list[Signal]:
    """
    Generate a signal list from one research summary.

    The list-based interface makes the output compatible with later
    persistence and downstream signal-processing components.
    """

    signal = create_signal(
        symbol=symbol,
        signal_date=signal_date,
        signal_type=signal_type,
        summary=summary,
        methodology_version=methodology_version,
        criteria=criteria,
    )

    if signal is None:
        return []

    return [signal]


def signal_to_dict(
    signal: Signal,
) -> dict[str, object]:
    """
    Convert a Signal model into a serializable dictionary.
    """

    return {
        "signal_key": signal.signal_key,
        "symbol": signal.symbol,
        "signal_date": signal.signal_date,
        "signal_type": signal.signal_type,
        "score": signal.score,
        "rationale": signal.rationale,
        "methodology_version": (
            signal.methodology_version
        ),
    }


def build_signal_date() -> str:
    """
    Return the current UTC date in YYYY-MM-DD format.

    This helper is intended for live system orchestration when a signal
    date has not been explicitly supplied.
    """

    return datetime.now(
        timezone.utc
    ).date().isoformat()


def validate_signal_collection(
    signals: Iterable[Signal],
) -> list[str]:
    """
    Validate a collection of generated signals.

    Returns a list of validation errors. An empty list means the collection
    passed structural validation.
    """

    errors: list[str] = []
    seen_keys: set[str] = set()

    for index, signal in enumerate(signals):
        prefix = f"signals[{index}]"

        if not signal.signal_key.strip():
            errors.append(
                f"{prefix}.signal_key is empty."
            )

        if not signal.symbol.strip():
            errors.append(
                f"{prefix}.symbol is empty."
            )

        if not signal.signal_date.strip():
            errors.append(
                f"{prefix}.signal_date is empty."
            )

        if not signal.signal_type.strip():
            errors.append(
                f"{prefix}.signal_type is empty."
            )

        if not signal.methodology_version.strip():
            errors.append(
                f"{prefix}.methodology_version is empty."
            )

        if signal.signal_key in seen_keys:
            errors.append(
                f"{prefix}.signal_key is duplicated."
            )

        seen_keys.add(
            signal.signal_key
        )

    return errors
