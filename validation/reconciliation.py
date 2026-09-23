"""
Reconciliation layer for Insider Trade Bot.

This module compares expected records with records accepted by the
ingestion pipeline. It is designed to make missing, duplicated, and
unexpected records visible instead of silently assuming completeness.

Reconciliation does not invent missing records or substitute other data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ReconciliationResult:
    """
    Result of reconciling an expected record set against an accepted set.
    """

    expected_count: int
    accepted_count: int

    matched_count: int
    missing_count: int
    unexpected_count: int
    duplicate_count: int

    missing_ids: tuple[str, ...]
    unexpected_ids: tuple[str, ...]
    duplicate_ids: tuple[str, ...]

    complete: bool


class ReconciliationError(Exception):
    """Raised when reconciliation input is invalid."""


def _normalize_ids(
    values: Iterable[str],
    field_name: str,
) -> list[str]:
    """
    Normalize a collection of record identifiers.
    """

    result: list[str] = []

    for index, value in enumerate(values):
        normalized = str(value).strip()

        if not normalized:
            raise ReconciliationError(
                f"{field_name}[{index}] cannot be empty."
            )

        result.append(normalized)

    return result


def reconcile_record_ids(
    expected_ids: Iterable[str],
    accepted_ids: Iterable[str],
) -> ReconciliationResult:
    """
    Reconcile expected record identifiers against accepted identifiers.

    A record is considered:

        matched
            Present exactly once in both sets.

        missing
            Expected but not accepted.

        unexpected
            Accepted but not expected.

        duplicate
            Appears more than once in the accepted collection.

    The result is marked complete only when there are no missing,
    unexpected, or duplicate records.
    """

    expected = _normalize_ids(
        expected_ids,
        "expected_ids",
    )

    accepted = _normalize_ids(
        accepted_ids,
        "accepted_ids",
    )

    expected_set = set(
        expected
    )

    accepted_set = set(
        accepted
    )

    missing = sorted(
        expected_set - accepted_set
    )

    unexpected = sorted(
        accepted_set - expected_set
    )

    counts: dict[str, int] = {}

    for record_id in accepted:
        counts[record_id] = (
            counts.get(record_id, 0) + 1
        )

    duplicates = sorted(
        record_id
        for record_id, count in counts.items()
        if count > 1
    )

    matched = (
        expected_set
        & accepted_set
    )

    complete = not (
        missing
        or unexpected
        or duplicates
    )

    return ReconciliationResult(
        expected_count=len(expected),
        accepted_count=len(accepted),
        matched_count=len(matched),
        missing_count=len(missing),
        unexpected_count=len(unexpected),
        duplicate_count=len(duplicates),
        missing_ids=tuple(missing),
        unexpected_ids=tuple(unexpected),
        duplicate_ids=tuple(duplicates),
        complete=complete,
    )


def require_complete_reconciliation(
    result: ReconciliationResult,
) -> None:
    """
    Raise an error when reconciliation is incomplete.

    This prevents downstream components from treating an incomplete
    historical-data load as complete.
    """

    if not isinstance(
        result,
        ReconciliationResult,
    ):
        raise TypeError(
            "result must be a ReconciliationResult."
        )

    if result.complete:
        return

    problems: list[str] = []

    if result.missing_count:
        problems.append(
            f"missing={result.missing_count}"
        )

    if result.unexpected_count:
        problems.append(
            f"unexpected={result.unexpected_count}"
        )

    if result.duplicate_count:
        problems.append(
            f"duplicates={result.duplicate_count}"
        )

    raise ReconciliationError(
        "Reconciliation is incomplete: "
        + ", ".join(problems)
        + "."
  )
