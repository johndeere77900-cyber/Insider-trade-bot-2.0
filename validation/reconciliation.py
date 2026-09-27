"""
Reconciliation layer for Insider Trade Bot.

Compares expected records with accepted records without inventing,
substituting, or silently discarding records.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ReconciliationResult:
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

    @property
    def is_reconciled(self) -> bool:
        return self.complete

    @property
    def missing_record_ids(self) -> tuple[str, ...]:
        return self.missing_ids

    @property
    def unexpected_record_ids(self) -> tuple[str, ...]:
        return self.unexpected_ids


class ReconciliationError(Exception):
    """Raised when reconciliation input is invalid."""


def _normalize_ids(
    values: Iterable[str],
    field_name: str,
) -> list[str]:
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
    expected = _normalize_ids(
        expected_ids,
        "expected_ids",
    )

    accepted = _normalize_ids(
        accepted_ids,
        "accepted_ids",
    )

    expected_set = set(expected)
    accepted_set = set(accepted)

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


def _extract_record_id(
    record: Mapping[str, Any],
    *,
    index: int,
    collection_name: str,
) -> str:
    if not isinstance(record, Mapping):
        raise ReconciliationError(
            f"{collection_name}[{index}] must be a mapping."
        )

    record_id = record.get("record_id")

    if record_id is None:
        raise ReconciliationError(
            f"{collection_name}[{index}] is missing record_id."
        )

    normalized = str(record_id).strip()

    if not normalized:
        raise ReconciliationError(
            f"{collection_name}[{index}] has an empty record_id."
        )

    return normalized


def reconcile_records(
    expected_records: Iterable[Mapping[str, Any]],
    actual_records: Iterable[Mapping[str, Any]],
) -> ReconciliationResult:
    """
    Reconcile expected record dictionaries against actual records.

    Record identity is determined by the explicit `record_id` field.
    """

    expected = list(expected_records)
    actual = list(actual_records)

    expected_ids = [
        _extract_record_id(
            record,
            index=index,
            collection_name="expected_records",
        )
        for index, record in enumerate(expected)
    ]

    actual_ids = [
        _extract_record_id(
            record,
            index=index,
            collection_name="actual_records",
        )
        for index, record in enumerate(actual)
    ]

    return reconcile_record_ids(
        expected_ids,
        actual_ids,
    )


def require_complete_reconciliation(
    result: ReconciliationResult,
) -> None:
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
