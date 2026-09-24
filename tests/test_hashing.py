from __future__ import annotations

from core.hashing import (
    canonical_json,
    generate_record_hash,
)


def test_canonical_json_is_deterministic() -> None:
    first = canonical_json(
        {
            "symbol": "AAPL",
            "shares": 100,
            "price": 150.25,
        }
    )

    second = canonical_json(
        {
            "price": 150.25,
            "shares": 100,
            "symbol": "AAPL",
        }
    )

    assert first == second


def test_record_hash_is_deterministic() -> None:
    payload = {
        "symbol": "AAPL",
        "transaction_type": "BUY",
        "shares": 100,
        "price": 150.25,
    }

    first = generate_record_hash(payload)
    second = generate_record_hash(payload)

    assert first == second


def test_different_records_produce_different_hashes() -> None:
    first = generate_record_hash(
        {
            "symbol": "AAPL",
            "shares": 100,
        }
    )

    second = generate_record_hash(
        {
            "symbol": "AAPL",
            "shares": 101,
        }
    )

    assert first != second


def test_record_hash_is_sha256_length() -> None:
    record_hash = generate_record_hash(
        {
            "symbol": "MSFT",
            "shares": 50,
        }
    )

    assert len(record_hash) == 64
    assert all(
        character in "0123456789abcdef"
        for character in record_hash
  )
