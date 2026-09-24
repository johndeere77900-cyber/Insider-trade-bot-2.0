from __future__ import annotations

from core.hashing import generate_record_hash
from validation.integrity import (
    IntegrityCheckResult,
    check_record_integrity,
)


def test_valid_record_integrity_passes() -> None:
    record = {
        "record_id": "REC-001",
        "symbol": "AAPL",
        "shares": 100,
        "price": 150.25,
    }

    record_hash = generate_record_hash(record)

    result = check_record_integrity(
        record=record,
        expected_hash=record_hash,
    )

    assert isinstance(result, IntegrityCheckResult)
    assert result.valid is True


def test_modified_record_fails_integrity_check() -> None:
    original_record = {
        "record_id": "REC-001",
        "symbol": "AAPL",
        "shares": 100,
        "price": 150.25,
    }

    original_hash = generate_record_hash(original_record)

    modified_record = {
        **original_record,
        "shares": 200,
    }

    result = check_record_integrity(
        record=modified_record,
        expected_hash=original_hash,
    )

    assert result.valid is False


def test_missing_expected_hash_fails_integrity_check() -> None:
    record = {
        "record_id": "REC-002",
        "symbol": "MSFT",
        "shares": 50,
    }

    result = check_record_integrity(
        record=record,
        expected_hash="",
    )

    assert result.valid is False
