from __future__ import annotations

from datetime import datetime, timezone

import pytest

from validation.records import (
    RecordValidationError,
    validate_insider_record,
    validate_market_price_record,
)


def test_valid_insider_record_passes() -> None:
    record = {
        "symbol": "AAPL",
        "insider_name": "John Doe",
        "transaction_date": "2026-01-15",
        "transaction_type": "BUY",
        "shares": 100,
        "price": 150.25,
        "source": "SEC",
        "accession_number": "0000000000-26-000001",
    }

    result = validate_insider_record(record)

    assert result is True


def test_missing_insider_symbol_is_rejected() -> None:
    record = {
        "insider_name": "John Doe",
        "transaction_date": "2026-01-15",
        "transaction_type": "BUY",
        "shares": 100,
        "price": 150.25,
        "source": "SEC",
        "accession_number": "0000000000-26-000001",
    }

    with pytest.raises(RecordValidationError):
        validate_insider_record(record)


def test_invalid_insider_transaction_type_is_rejected() -> None:
    record = {
        "symbol": "AAPL",
        "insider_name": "John Doe",
        "transaction_date": "2026-01-15",
        "transaction_type": "INVALID",
        "shares": 100,
        "price": 150.25,
        "source": "SEC",
        "accession_number": "0000000000-26-000001",
    }

    with pytest.raises(RecordValidationError):
        validate_insider_record(record)


def test_valid_market_price_record_passes() -> None:
    record = {
        "symbol": "AAPL",
        "price_date": "2026-01-15",
        "open_price": 149.00,
        "high_price": 152.00,
        "low_price": 148.50,
        "close_price": 151.25,
        "volume": 1000000,
        "source": "TEST",
    }

    result = validate_market_price_record(record)

    assert result is True


def test_market_price_with_negative_close_is_rejected() -> None:
    record = {
        "symbol": "AAPL",
        "price_date": "2026-01-15",
        "open_price": 149.00,
        "high_price": 152.00,
        "low_price": 148.50,
        "close_price": -1.00,
        "volume": 1000000,
        "source": "TEST",
    }

    with pytest.raises(RecordValidationError):
        validate_market_price_record(record)
