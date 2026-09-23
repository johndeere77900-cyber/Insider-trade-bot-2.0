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
