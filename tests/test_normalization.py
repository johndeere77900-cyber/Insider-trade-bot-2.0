from __future__ import annotations

from data.normalization import (
    normalize_insider_record,
    normalize_market_price,
)


def test_normalize_insider_record() -> None:
    record = {
        "ticker": "AAPL",
        "insider": "John Doe",
        "transaction_date": "2026-01-15",
        "transaction_type": "BUY",
        "shares": "100",
        "price": "150.25",
        "source": "SEC",
        "accession_number": "0000000000-26-000001",
    }

    normalized = normalize_insider_record(record)

    assert normalized["symbol"] == "AAPL"
    assert normalized["insider_name"] == "John Doe"
    assert normalized["transaction_date"] == "2026-01-15"
    assert normalized["transaction_type"] == "BUY"
    assert normalized["shares"] == 100
    assert normalized["price"] == 150.25
    assert normalized["source"] == "SEC"


def test_normalize_market_price() -> None:
    record = {
        "ticker": "MSFT",
        "date": "2026-01-15",
        "open": "400.00",
        "high": "405.00",
        "low": "398.50",
        "close": "403.25",
        "volume": "2500000",
        "source": "TEST",
    }

    normalized = normalize_market_price(record)

    assert normalized["symbol"] == "MSFT"
    assert normalized["price_date"] == "2026-01-15"
    assert normalized["open_price"] == 400.00
    assert normalized["high_price"] == 405.00
    assert normalized["low_price"] == 398.50
    assert normalized["close_price"] == 403.25
    assert normalized["volume"] == 2500000
    assert normalized["source"] == "TEST"


def test_normalization_preserves_zero_values() -> None:
    insider = {
        "symbol": "TEST",
        "insider_name": "Test Person",
        "transaction_date": "2026-01-15",
        "transaction_type": "BUY",
        "shares": 0,
        "price": 0,
        "source": "TEST",
        "accession_number": "TEST-001",
    }

    normalized_insider = normalize_insider_record(insider)

    assert normalized_insider["shares"] == 0
    assert normalized_insider["price"] == 0
