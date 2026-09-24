from __future__ import annotations

from validation.reconciliation import (
    ReconciliationResult,
    reconcile_records,
)


def test_reconciliation_reports_matching_records() -> None:
    expected = [
        {
            "record_id": "REC-001",
            "symbol": "AAPL",
            "shares": 100,
        },
        {
            "record_id": "REC-002",
            "symbol": "MSFT",
            "shares": 50,
        },
    ]

    actual = [
        {
            "record_id": "REC-001",
            "symbol": "AAPL",
            "shares": 100,
        },
        {
            "record_id": "REC-002",
            "symbol": "MSFT",
            "shares": 50,
        },
    ]

    result = reconcile_records(expected, actual)

    assert isinstance(result, ReconciliationResult)
    assert result.is_reconciled is True


def test_reconciliation_detects_missing_records() -> None:
    expected = [
        {
            "record_id": "REC-001",
            "symbol": "AAPL",
        },
        {
            "record_id": "REC-002",
            "symbol": "MSFT",
        },
    ]

    actual = [
        {
            "record_id": "REC-001",
            "symbol": "AAPL",
        },
    ]

    result = reconcile_records(expected, actual)

    assert result.is_reconciled is False
    assert "REC-002" in result.missing_record_ids


def test_reconciliation_detects_unexpected_records() -> None:
    expected = [
        {
            "record_id": "REC-001",
            "symbol": "AAPL",
        },
    ]

    actual = [
        {
            "record_id": "REC-001",
            "symbol": "AAPL",
        },
        {
            "record_id": "REC-002",
            "symbol": "MSFT",
        },
    ]

    result = reconcile_records(expected, actual)

    assert result.is_reconciled is False
    assert "REC-002" in result.unexpected_record_ids
