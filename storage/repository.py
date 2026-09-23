"""
Permanent storage repository for Insider Trade Bot.

This module provides controlled database-write operations for validated
records and provenance information.

Raw external data must not be treated as validated merely because it was
retrieved successfully.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from core.hashing import sha256_record
from database.connection import connect


ALLOWED_PAYLOAD_TABLES = {
    "insider_transactions",
    "market_prices",
    "corporate_actions",
}


def utc_now() -> str:
    """
    Return the current UTC timestamp in ISO-8601 format.
    """

    return datetime.now(
        timezone.utc
    ).isoformat()


def store_provenance(
    database_url: str,
    record_type: str,
    record_id: str,
    source: str,
    source_reference: str | None,
    checksum: str | None,
    validation_status: str,
) -> None:
    """
    Store provenance information for a record.
    """

    if not record_type.strip():
        raise ValueError(
            "record_type cannot be empty."
        )

    if not record_id.strip():
        raise ValueError(
            "record_id cannot be empty."
        )

    if not source.strip():
        raise ValueError(
            "source cannot be empty."
        )

    if not validation_status.strip():
        raise ValueError(
            "validation_status cannot be empty."
        )

    with connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO provenance (
                record_type,
                record_id,
                source,
                source_reference,
                retrieved_at,
                checksum,
                validation_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_type,
                record_id,
                source,
                source_reference,
                utc_now(),
                checksum,
                validation_status,
            ),
        )

        connection.commit()


def store_insider_transaction(
    database_url: str,
    *,
    source: str,
    accession_number: str,
    issuer_cik: str,
    issuer_name: str | None,
    insider_name: str | None,
    insider_cik: str | None,
    transaction_date: str | None,
    filing_date: str | None,
    form_type: str | None,
    transaction_code: str | None,
    shares: float | None,
    price: float | None,
    ownership_type: str | None,
    raw_payload: dict[str, Any],
) -> str:
    """
    Store an insider transaction.

    Returns:
        The deterministic SHA-256 record hash.
    """

    record_hash = sha256_record(
        raw_payload
    )

    with connect(database_url) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO insider_transactions (
                source,
                accession_number,
                issuer_cik,
                issuer_name,
                insider_name,
                insider_cik,
                transaction_date,
                filing_date,
                form_type,
                transaction_code,
                shares,
                price,
                ownership_type,
                raw_payload,
                record_hash,
                created_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                source,
                accession_number,
                issuer_cik,
                issuer_name,
                insider_name,
                insider_cik,
                transaction_date,
                filing_date,
                form_type,
                transaction_code,
                shares,
                price,
                ownership_type,
                json.dumps(
                    raw_payload,
                    sort_keys=True,
                    default=str,
                ),
                record_hash,
                utc_now(),
            ),
        )

        connection.commit()

    return record_hash


def store_market_price(
    database_url: str,
    *,
    symbol: str,
    price_date: str,
    open_price: float | None,
    high: float | None,
    low: float | None,
    close: float | None,
    adjusted_close: float | None,
    volume: float | None,
    source: str,
    raw_payload: dict[str, Any],
) -> str:
    """
    Store a normalized market-price record.

    Returns:
        The deterministic SHA-256 record hash.
    """

    record_hash = sha256_record(
        raw_payload
    )

    with connect(database_url) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO market_prices (
                symbol,
                price_date,
                open,
                high,
                low,
                close,
                adjusted_close,
                volume,
                source,
                record_hash,
                created_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                symbol,
                price_date,
                open_price,
                high,
                low,
                close,
                adjusted_close,
                volume,
                source,
                record_hash,
                utc_now(),
            ),
        )

        connection.commit()

    return record_hash


def store_corporate_action(
    database_url: str,
    *,
    symbol: str,
    action_type: str,
    action_date: str,
    ratio: str | None,
    cash_amount: float | None,
    source: str,
    raw_payload: dict[str, Any],
) -> str:
    """
    Store a normalized corporate-action record.

    Returns:
        The deterministic SHA-256 record hash.
    """

    record_hash = sha256_record(
        raw_payload
    )

    with connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO corporate_actions (
                symbol,
                action_type,
                action_date,
                ratio,
                cash_amount,
                source,
                raw_payload,
                record_hash,
                created_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                symbol,
                action_type,
                action_date,
                ratio,
                cash_amount,
                source,
                json.dumps(
                    raw_payload,
                    sort_keys=True,
                    default=str,
                ),
                record_hash,
                utc_now(),
            ),
        )

        connection.commit()

    return record_hash


def table_exists(
    database_url: str,
    table_name: str,
) -> bool:
    """
    Check whether a table exists in the configured database.
    """

    with connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
            """,
            (table_name,),
        ).fetchone()

    return row is not None


def count_records(
    database_url: str,
    table_name: str,
) -> int:
    """
    Return the number of records in an approved permanent-storage table.
    """

    if table_name not in {
        "insider_transactions",
        "market_prices",
        "corporate_actions",
        "research_events",
        "signals",
        "trade_runs",
        "provenance",
    }:
        raise ValueError(
            "Unsupported table."
        )

    with connect(database_url) as connection:
        row = connection.execute(
            f"SELECT COUNT(*) AS count FROM {table_name}"
        ).fetchone()

    return int(row["count"])
