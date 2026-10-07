"""
Hashing and canonicalization utilities for Insider Trade Bot.

These utilities are used to create deterministic fingerprints for records.
They support deduplication, provenance, and integrity verification.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """
    Convert a Python value into deterministic JSON.

    Sorting keys and using consistent separators ensures that equivalent
    records produce the same serialized representation.
    """

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    )


def sha256_text(value: str) -> str:
    """
    Return the SHA-256 hexadecimal digest of text.
    """

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def sha256_record(value: Any) -> str:
    """
    Create a deterministic SHA-256 fingerprint for a record.
    """

    return sha256_text(
        canonical_json(value)
    )


def generate_record_hash(value: Any) -> str:
    """
    Generate the deterministic SHA-256 hash used as a record fingerprint.

    This is the public compatibility API used by validation and integrity
    components.
    """

    return sha256_record(value)


def generate_market_price_hash(
    symbol: str,
    price_date: str,
    source: str,
    open_price: float | None = None,
    high: float | None = None,
    low: float | None = None,
    close: float | None = None,
    adjusted_close: float | None = None,
    volume: float | None = None,
) -> str:
    """
    Generate a deterministic SHA-256 fingerprint for a market price record
    based on its normalized semantic fields.
    """
    payload = {
        "symbol": str(symbol).strip().upper(),
        "price_date": str(price_date).strip(),
        "source": str(source).strip(),
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "adjusted_close": adjusted_close,
        "volume": volume,
    }
    return sha256_record(payload)
