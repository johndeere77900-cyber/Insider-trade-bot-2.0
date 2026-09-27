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
from typing import Any, Mapping

from core.hashing import sha256_record
from database.connection import (
    connect,
    initialize_database,
)


ALLOWED_PAYLOAD_TABLES = {
    "insider_transactions",
    "market_prices",
    "corporate_actions",
}


def utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def store_provenance(
    database_url: str,
    record_type: str,
    record_id: str,
    source: str,
    source_reference: str | None,
    checksum: str | None,
    validation_status: str,
) -> None:
    """Store provenance information for a record."""

    if not record_type.strip():
        raise ValueError("record_type cannot be empty.")

    if not record_id.strip():
        raise ValueError("record_id cannot be empty.")

    if not source.strip():
        raise ValueError("source cannot be empty.")

    if not validation_status.strip():
        raise ValueError("validation_status cannot be empty.")

    initialize_database(database_url)

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
    """Store an insider transaction and return its record hash."""

    initialize_database(database_url)

    record_hash = sha256_record(raw_payload)

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
    """Store a normalized market-price record and return its hash."""

    initialize_database(database_url)

    record_hash = sha256_record(raw_payload)

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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    """Store a normalized corporate-action record and return its hash."""

    initialize_database(database_url)

    record_hash = sha256_record(raw_payload)

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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    """Check whether a table exists in the configured database."""

    initialize_database(database_url)

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
    """Return the number of records in an approved storage table."""

    allowed_tables = {
        "insider_transactions",
        "market_prices",
        "corporate_actions",
        "research_events",
        "signals",
        "trade_runs",
        "provenance",
    }

    if table_name not in allowed_tables:
        raise ValueError("Unsupported table.")

    initialize_database(database_url)

    with connect(database_url) as connection:
        row = connection.execute(
            f"SELECT COUNT(*) AS count FROM {table_name}"
        ).fetchone()

    return int(row["count"])


class Repository:
    """
    Compatibility repository interface.

    This class provides the object-oriented interface expected by callers
    while preserving the existing specialized storage functions above.
    """

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

        initialize_database(
            self.database_url
        )

    def store(
        self,
        *,
        table: str,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        """
        Store a generic compatibility record.

        The compatibility API accepts the lightweight normalized shape used
        by the existing repository tests:

            {
                "symbol": "...",
                "source": "...",
                "record_hash": "..."
            }

        For insider_transactions, those fields are represented in the
        existing normalized schema without silently changing the permanent
        schema. The original compatibility payload is retained in
        raw_payload.
        """

        allowed_tables = {
            "insider_transactions",
            "market_prices",
            "corporate_actions",
            "research_events",
            "signals",
            "trade_runs",
            "provenance",
        }

        if table not in allowed_tables:
            raise ValueError(
                f"Unsupported table: {table!r}"
            )

        if not record:
            raise ValueError(
                "record cannot be empty."
            )

        supplied = {
            str(key): value
            for key, value in record.items()
        }

        if table == "insider_transactions":
            return self._store_compat_insider(
                supplied
            )

        with connect(self.database_url) as connection:
            columns = {
                row["name"]
                for row in connection.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            }

            unknown = set(supplied) - columns

            if unknown:
                raise ValueError(
                    "Record contains unsupported columns: "
                    + ", ".join(sorted(unknown))
                )

            insert_columns = list(
                supplied.keys()
            )

            placeholders = ", ".join(
                "?"
                for _ in insert_columns
            )

            column_sql = ", ".join(
                f'"{column}"'
                for column in insert_columns
            )

            values = [
                supplied[column]
                for column in insert_columns
            ]

            connection.execute(
                f"""
                INSERT INTO {table} (
                    {column_sql}
                )
                VALUES (
                    {placeholders}
                )
                """,
                values,
            )

            connection.commit()

            row_id = connection.execute(
                "SELECT last_insert_rowid() AS id"
            ).fetchone()["id"]

        return {
            "table": table,
            "id": row_id,
            "record": dict(record),
        }

    def _store_compat_insider(
        self,
        record: Mapping[str, Any],
    ) -> dict[str, Any]:
        """
        Store the legacy lightweight insider-record compatibility shape.

        The permanent insider schema requires issuer and accession metadata.
        The compatibility interface supplies neither, so deterministic
        compatibility values are derived without pretending they came from
        the SEC.
        """

        source = str(
            record.get(
                "source",
                "UNKNOWN",
            )
        )

        record_hash = str(
            record.get(
                "record_hash",
                sha256_record(record),
            )
        )

        symbol = record.get(
            "symbol"
        )

        raw_payload = json.dumps(
            dict(record),
            sort_keys=True,
            default=str,
        )

        with connect(self.database_url) as connection:
            cursor = connection.execute(
                """
                INSERT INTO insider_transactions (
                    source,
                    accession_number,
                    issuer_cik,
                    issuer_name,
                    raw_payload,
                    record_hash,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source,
                    record_hash,
                    "UNKNOWN",
                    symbol,
                    raw_payload,
                    record_hash,
                    utc_now(),
                ),
            )

            connection.commit()

            row_id = cursor.lastrowid

        return {
            "table": "insider_transactions",
            "id": row_id,
            "record": dict(record),
                }
