"""
Chronological dataset and trade splitting boundary for Insider Trade Bot.

Enforces strict walk-forward / chronological train/test separation to eliminate
data leakage across time boundaries during model/signal evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class BacktestSplit:
    """Explicit date boundaries defining a chronological train/test split."""

    train_start: str
    train_end: str
    test_start: str
    test_end: str


def chronological_split(
    records: Sequence[T],
    *,
    train_end: str,
    test_start: str,
    date_field: str = "event_date",
) -> tuple[list[T], list[T]]:
    """
    Split a collection of chronological records into train and test sets.

    Rules:
    - train_end must be strictly before test_start.
    - Train data contains records with date <= train_end.
    - Test data contains records with date >= test_start.
    - No overlap permitted between train and test boundaries.
    - Future data must never enter training set.
    """
    norm_train_end = str(train_end).strip()
    norm_test_start = str(test_start).strip()

    if not norm_train_end or not norm_test_start:
        raise ValueError("train_end and test_start dates cannot be empty.")

    if norm_train_end >= norm_test_start:
        raise ValueError(
            f"Invalid date boundary: train_end '{norm_train_end}' must be strictly before test_start '{norm_test_start}'."
        )

    train_set: list[T] = []
    test_set: list[T] = []

    def _get_record_date(item: T) -> str:
        if isinstance(item, Mapping):
            d = item.get(date_field) or item.get("date") or item.get("entry_date") or item.get("signal_date")
        else:
            d = getattr(item, date_field, None) or getattr(item, "date", None) or getattr(item, "entry_date", None) or getattr(item, "signal_date", None)
        if d is None:
            raise ValueError(f"Record {item} missing date field '{date_field}'.")
        return str(d).strip()

    for rec in records:
        rec_date = _get_record_date(rec)

        if rec_date <= norm_train_end:
            train_set.append(rec)
        elif rec_date >= norm_test_start:
            test_set.append(rec)
        # Records falling in the gap between train_end and test_start are excluded from both sets

    # Sort each set chronologically
    train_set.sort(key=_get_record_date)
    test_set.sort(key=_get_record_date)

    return train_set, test_set
