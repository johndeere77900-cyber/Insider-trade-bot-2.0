"""
Permanent storage repository for Insider Trade Bot.

This module provides controlled database-write operations for validated
records and provenance information.

Raw external data must not be treated as validated merely because it was
retrieved successfully.

The repository supports both SQLite and PostgreSQL through the database
backend selected by database_url.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping

from core.hashing import generate_market_price_hash, sha256_record
from database.connection import (
    connect,
    initialize_database,
    is_postgresql_url,
)

try:
    import psycopg.errors
    PSYCOPG_INTEGRITY_ERRORS: tuple[type[BaseException], ...] = (
        psycopg.errors.UniqueViolation,
        psycopg.errors.IntegrityError,
    )
except ImportError:
    PSYCOPG_INTEGRITY_ERRORS = ()

INTEGRITY_ERRORS: tuple[type[BaseException], ...] = (
    sqlite3.IntegrityError,
) + PSYCOPG_INTEGRITY_ERRORS


ALLOWED_PAYLOAD_TABLES = {
    "insider_transactions",
    "market_prices",
    "corporate_actions",
}


class MarketDataConflictError(ValueError):
    """Raised when an insertion conflicts with an existing different record for the same symbol/date/source."""


def utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _should_store_raw_payload(override: bool | None = None) -> bool:
    """Determine if raw_payload should be stored based on parameter or SEC_STORE_RAW_PAYLOAD env var."""
    if override is not None:
        return bool(override)
    value = os.getenv("SEC_STORE_RAW_PAYLOAD")
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _placeholder(database_url: str) -> str:
    """Return the SQL parameter placeholder for the configured backend."""
    return "%s" if is_postgresql_url(database_url) else "?"


def _row_value(row: Any, key: str, index: int = 0) -> Any:
    """
    Read a value from either a mapping-style row or a tuple-style row.

    SQLite is configured with sqlite3.Row. PostgreSQL psycopg connections
    may return ordinary tuples unless a row factory is explicitly configured.
    """
    if row is None:
        return None

    if isinstance(row, Mapping) or hasattr(row, "keys"):
        return row[key]

    return row[index]


def _quote_identifier(identifier: str) -> str:
    """
    Quote a trusted SQL identifier.

    Identifiers passed here are always checked against an explicit allowlist
    before this helper is used.
    """
    return '"' + identifier.replace('"', '""') + '"'


def _table_columns(
    database_url: str,
    table: str,
) -> set[str]:
    """Return the columns for an approved table."""

    if is_postgresql_url(database_url):
        query = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
        """
        parameters = (table,)
    else:
        query = f"""
            PRAGMA table_info({_quote_identifier(table)})
        """
        parameters = ()

    with connect(database_url) as connection:
        cursor = connection.execute(
            query,
            parameters,
        )
        rows = cursor.fetchall()

    if is_postgresql_url(database_url):
        return {
            str(_row_value(row, "column_name", index=0))
            for row in rows
        }

    return {
        str(_row_value(row, "name", index=1))
        for row in rows
    }


def _insert_ignore_sql(database_url: str) -> str:
    """Return the backend-specific conflict-ignore clause."""
    if is_postgresql_url(database_url):
        return "ON CONFLICT DO NOTHING"

    return "INSERT OR IGNORE"


def store_provenance(
    database_url: str,
    record_type: str,
    record_id: str,
    source: str,
    source_reference: str | None,
    checksum: str | None,
    validation_status: str,
) -> None:
    """Store provenance information for a record (idempotent)."""

    if not record_type.strip():
        raise ValueError("record_type cannot be empty.")

    if not record_id.strip():
        raise ValueError("record_id cannot be empty.")

    if not source.strip():
        raise ValueError("source cannot be empty.")

    if not validation_status.strip():
        raise ValueError("validation_status cannot be empty.")

    initialize_database(database_url)

    placeholder = _placeholder(database_url)

    with connect(database_url) as connection:
        connection.execute(
            f"""
            INSERT INTO provenance (
                record_type,
                record_id,
                source,
                source_reference,
                retrieved_at,
                checksum,
                validation_status
            )
            VALUES (
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder},
                {placeholder}
            )
            ON CONFLICT (record_type, record_id, source)
            DO UPDATE SET
                source_reference = EXCLUDED.source_reference,
                retrieved_at = EXCLUDED.retrieved_at,
                checksum = EXCLUDED.checksum,
                validation_status = EXCLUDED.validation_status
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
    ticker: str | None = None,
    insider_name: str | None = None,
    insider_cik: str | None = None,
    transaction_date: str | None = None,
    filing_date: str | None = None,
    form_type: str | None = None,
    transaction_code: str | None = None,
    security_title: str | None = None,
    shares: float | None = None,
    price: float | None = None,
    transaction_type: str | None = None,
    ownership_type: str | None = None,
    ownership_nature: str | None = None,
    source_url: str | None = None,
    raw_payload: dict[str, Any],
    store_raw_payload: bool | None = None,
) -> str:
    """Store an insider transaction and return its record hash."""

    initialize_database(database_url)

    record_hash = sha256_record(raw_payload)
    placeholder = _placeholder(database_url)

    columns = """
        source,
        accession_number,
        issuer_cik,
        issuer_name,
        ticker,
        insider_name,
        insider_cik,
        transaction_date,
        filing_date,
        form_type,
        transaction_code,
        security_title,
        shares,
        price,
        transaction_type,
        acquired_disposed,
        ownership_type,
        ownership_nature,
        source_url,
        is_amendment,
        date_of_orig_submission,
        raw_payload,
        record_hash,
        created_at
    """

    raw_payload_str = (
        json.dumps(
            raw_payload,
            sort_keys=True,
            default=str,
        )
        if _should_store_raw_payload(store_raw_payload)
        else None
    )

    values = (
        source,
        accession_number,
        issuer_cik,
        issuer_name,
        ticker,
        insider_name,
        insider_cik,
        transaction_date,
        filing_date,
        form_type,
        transaction_code,
        security_title,
        shares,
        price,
        transaction_type,
        None,  # acquired_disposed
        ownership_type,
        ownership_nature,
        source_url,
        0,  # is_amendment
        None,  # date_of_orig_submission
        raw_payload_str,
        record_hash,
        utc_now(),
    )

    placeholders = ", ".join(
        placeholder
        for _ in values
    )

    with connect(database_url) as connection:
        if is_postgresql_url(database_url):
            connection.execute(
                f"""
                INSERT INTO insider_transactions (
                    {columns}
                )
                VALUES (
                    {placeholders}
                )
                ON CONFLICT (
                    source,
                    accession_number,
                    record_hash
                )
                DO NOTHING
                """,
                values,
            )
        else:
            connection.execute(
                f"""
                INSERT OR IGNORE INTO insider_transactions (
                    {columns}
                )
                VALUES (
                    {placeholders}
                )
                """,
                values,
            )

        connection.commit()

    return record_hash


def store_bulk_insider_transactions(
    database_url: str,
    records: list[Any],
    *,
    store_raw_payload: bool | None = None,
) -> tuple[int, int]:
    """
    Batch store normalized insider transactions with deduplication.
    Note: Provenance is tracked at the dataset level (dataset_period) rather
    than per-transaction to prevent massive database index/storage bloat.

    Returns:
        (inserted_count, duplicates_count)
    """
    if not records:
        return 0, 0

    initialize_database(database_url)

    columns = """
        source, accession_number, issuer_cik, issuer_name, ticker,
        insider_name, insider_cik, transaction_date, filing_date,
        form_type, transaction_code, security_title, shares, price,
        transaction_type, acquired_disposed, ownership_type, ownership_nature, source_url,
        is_amendment, date_of_orig_submission,
        raw_payload, record_hash, created_at
    """

    now = utc_now()
    rows_to_insert = []
    should_store_raw = _should_store_raw_payload(store_raw_payload)

    for r in records:
        # Use persisted semantic transaction identity (record_hash) if available
        r_hash = getattr(r, "record_hash", None)
        raw_payload_val = getattr(r, "raw_payload", None)

        if not r_hash:
            if raw_payload_val:
                r_hash = sha256_record(raw_payload_val)
            else:
                raise ValueError(
                    "Transaction record identity cannot be established: "
                    "both record_hash and raw_payload are missing."
                )

        raw_json = (
            json.dumps(raw_payload_val, sort_keys=True, default=str)
            if should_store_raw and raw_payload_val is not None
            else None
        )

        form_t = getattr(r, "form_type", None) or getattr(r, "form", None) or "4"
        acq_disp = getattr(r, "acquired_disposed", None)
        is_amend = int(bool(getattr(r, "is_amendment", False)))
        orig_sub_date = getattr(r, "date_of_orig_submission", None)

        val_tuple = (
            r.source,
            r.accession_number,
            r.issuer_cik,
            r.issuer_name,
            r.ticker,
            r.reporting_owner_name,
            r.reporting_owner_cik,
            r.transaction_date,
            r.filing_date,
            form_t,
            r.transaction_code,
            r.security_title,
            r.shares,
            r.price_per_share,
            r.transaction_type,
            acq_disp,
            r.ownership_type,
            r.ownership_nature,
            r.source_url,
            is_amend,
            orig_sub_date,
            raw_json,
            r_hash,
            now,
        )
        rows_to_insert.append(val_tuple)

    placeholder_str = ", ".join(_placeholder(database_url) for _ in rows_to_insert[0])

    initial_count = count_records(database_url, "insider_transactions")

    with connect(database_url) as connection:
        if is_postgresql_url(database_url):
            insert_sql = f"""
                INSERT INTO insider_transactions ({columns})
                VALUES ({placeholder_str})
                ON CONFLICT (source, accession_number, record_hash) DO NOTHING
            """
        else:
            insert_sql = f"""
                INSERT OR IGNORE INTO insider_transactions ({columns})
                VALUES ({placeholder_str})
            """

        if is_postgresql_url(database_url):
            with connection.cursor() as cursor:
                cursor.executemany(insert_sql, rows_to_insert)
        else:
            connection.executemany(insert_sql, rows_to_insert)

        connection.commit()

    final_count = count_records(database_url, "insider_transactions")
    inserted_count = final_count - initial_count
    duplicates_count = len(records) - inserted_count

    return inserted_count, max(0, duplicates_count)


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
    raw_payload: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """
    Store a normalized market-price record idempotently and return (record_hash, outcome).

    Outcome is either 'INSERTED' or 'DUPLICATE'.
    Raises MarketDataConflictError if a record for the same symbol/price_date/source
    already exists with materially different price data.
    """

    initialize_database(database_url)

    normalized_symbol = str(symbol).strip().upper()
    normalized_date = str(price_date).strip()
    normalized_source = str(source).strip()

    record_hash = generate_market_price_hash(
        symbol=normalized_symbol,
        price_date=normalized_date,
        source=normalized_source,
        open_price=open_price,
        high=high,
        low=low,
        close=close,
        adjusted_close=adjusted_close,
        volume=volume,
    )

    placeholder = _placeholder(database_url)

    select_sql = f"""
        SELECT record_hash
        FROM market_prices
        WHERE symbol = {placeholder}
          AND price_date = {placeholder}
          AND source = {placeholder}
    """

    with connect(database_url) as connection:
        cursor = connection.execute(
            select_sql,
            (normalized_symbol, normalized_date, normalized_source),
        )
        existing = cursor.fetchone()

        if existing is not None:
            existing_hash = _row_value(existing, "record_hash", index=0)
            if existing_hash == record_hash:
                return record_hash, "DUPLICATE"
            raise MarketDataConflictError(
                f"Data conflict: market price for symbol '{normalized_symbol}', date '{normalized_date}', "
                f"source '{normalized_source}' already exists with different values."
            )

        values = (
            normalized_symbol,
            normalized_date,
            open_price,
            high,
            low,
            close,
            adjusted_close,
            volume,
            normalized_source,
            record_hash,
            utc_now(),
        )

        placeholders = ", ".join(
            placeholder
            for _ in values
        )

        if is_postgresql_url(database_url):
            connection.execute(
                f"""
                INSERT INTO market_prices (
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
                    {placeholders}
                )
                ON CONFLICT (
                    symbol,
                    price_date,
                    source
                )
                DO NOTHING
                """,
                values,
            )
        else:
            connection.execute(
                f"""
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
                    {placeholders}
                )
                """,
                values,
            )

        connection.commit()

    return record_hash, "INSERTED"


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
    record_hash: str | None = None,
) -> tuple[str, str]:
    """
    Store a normalized corporate-action record idempotently and return (record_hash, outcome).

    Identity is provider-neutral: (symbol, action_type, action_date, source).
    Outcomes:
        - 'INSERTED': New identity row stored.
        - 'DUPLICATE': Identity exists with identical normalized record_hash (no-op).
        - 'CONFLICT': Identity exists with different normalized record_hash (no-op, report conflict).
    """

    initialize_database(database_url)

    norm_symbol = str(symbol).strip().upper()
    norm_action_type = str(action_type).strip().lower()
    norm_action_date = str(action_date).strip()
    norm_source = str(source).strip().lower()

    if record_hash is None:
        norm_dict = {
            "symbol": norm_symbol,
            "action_type": norm_action_type,
            "action_date": norm_action_date,
            "ratio": str(ratio).strip() if ratio is not None else None,
            "cash_amount": float(cash_amount) if cash_amount is not None else None,
            "source": norm_source,
        }
        record_hash = sha256_record(norm_dict)

    placeholder = _placeholder(database_url)

    select_sql = f"""
        SELECT record_hash
        FROM corporate_actions
        WHERE symbol = {placeholder}
          AND action_type = {placeholder}
          AND action_date = {placeholder}
          AND source = {placeholder}
    """

    with connect(database_url) as connection:
        cursor = connection.execute(
            select_sql,
            (norm_symbol, norm_action_type, norm_action_date, norm_source),
        )
        existing = cursor.fetchone()

        if existing is not None:
            existing_hash = _row_value(existing, "record_hash", index=0)
            if existing_hash == record_hash:
                return record_hash, "DUPLICATE"
            return record_hash, "CONFLICT"

        values = (
            norm_symbol,
            norm_action_type,
            norm_action_date,
            ratio,
            cash_amount,
            norm_source,
            json.dumps(
                raw_payload,
                sort_keys=True,
                default=str,
            ),
            record_hash,
            utc_now(),
        )

        placeholders = ", ".join(placeholder for _ in values)

        try:
            connection.execute(
                f"""
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
                    {placeholders}
                )
                """,
                values,
            )
            connection.commit()
            return record_hash, "INSERTED"

        except INTEGRITY_ERRORS as exc:
            connection.rollback()

            is_expected_unique_race = False

            if PSYCOPG_INTEGRITY_ERRORS and isinstance(exc, PSYCOPG_INTEGRITY_ERRORS):
                pgcode = getattr(exc, "pgcode", None) or getattr(exc, "sqlstate", None)
                if pgcode == "23505" or (
                    hasattr(psycopg.errors, "UniqueViolation")
                    and isinstance(exc, psycopg.errors.UniqueViolation)
                ):
                    diag_table = getattr(getattr(exc, "diag", None), "table_name", "") or ""
                    diag_constraint = getattr(getattr(exc, "diag", None), "constraint_name", "") or ""
                    exc_str = str(exc).lower()
                    if (
                        not diag_table
                        and not diag_constraint
                    ) or (
                        "corporate_actions" in diag_table
                        or "corporate_actions" in diag_constraint
                        or "corporate_actions" in exc_str
                    ):
                        is_expected_unique_race = True
            elif isinstance(exc, sqlite3.IntegrityError):
                msg = str(exc).lower()
                if "unique" in msg and not any(
                    k in msg for k in ("foreign key", "not null", "check constraint")
                ):
                    is_expected_unique_race = True

            if is_expected_unique_race:
                cursor = connection.execute(
                    select_sql,
                    (norm_symbol, norm_action_type, norm_action_date, norm_source),
                )
                race_existing = cursor.fetchone()
                if race_existing is not None:
                    race_hash = _row_value(race_existing, "record_hash", index=0)
                    if race_hash == record_hash:
                        return record_hash, "DUPLICATE"
                    return record_hash, "CONFLICT"

            raise


def table_exists(
    database_url: str,
    table_name: str,
) -> bool:
    """Check whether a table exists in the configured database."""

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

    if is_postgresql_url(database_url):
        query = """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = %s
        """
        parameters = (table_name,)
    else:
        query = """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?
        """
        parameters = (table_name,)

    with connect(database_url) as connection:
        row = connection.execute(
            query,
            parameters,
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
            f"""
            SELECT COUNT(*) AS count
            FROM {_quote_identifier(table_name)}
            """
        ).fetchone()

    return int(_row_value(row, "count"))


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
        by the existing repository tests.

        The compatibility path is retained for existing callers and tests.
        It does not replace the validated SEC ingestion path.
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

        columns = _table_columns(
            self.database_url,
            table,
        )

        unknown = set(supplied) - columns

        if unknown:
            raise ValueError(
                "Record contains unsupported columns: "
                + ", ".join(sorted(unknown))
            )

        insert_columns = list(
            supplied.keys()
        )

        placeholder = _placeholder(
            self.database_url
        )

        placeholders = ", ".join(
            placeholder
            for _ in insert_columns
        )

        column_sql = ", ".join(
            _quote_identifier(column)
            for column in insert_columns
        )

        values = [
            supplied[column]
            for column in insert_columns
        ]

        with connect(self.database_url) as connection:
            if is_postgresql_url(self.database_url):
                cursor = connection.execute(
                    f"""
                    INSERT INTO {_quote_identifier(table)} (
                        {column_sql}
                    )
                    VALUES (
                        {placeholders}
                    )
                    RETURNING id
                    """,
                    values,
                )
                row = cursor.fetchone()

                if row is None:
                    raise RuntimeError(
                        "Generic repository insert did not return an id."
                    )

                row_id = _row_value(row, "id")
            else:
                connection.execute(
                    f"""
                    INSERT INTO {_quote_identifier(table)} (
                        {column_sql}
                    )
                    VALUES (
                        {placeholders}
                    )
                    """,
                    values,
                )

                row = connection.execute(
                    "SELECT last_insert_rowid() AS id"
                ).fetchone()

                row_id = _row_value(row, "id")

            connection.commit()

        return {
            "table": table,
            "id": row_id,
            "record": dict(record),
        }

    def _store_compat_insider(
        self,
        record: Mapping[str, Any],
        store_raw_payload: bool | None = None,
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

        raw_payload = (
            json.dumps(
                dict(record),
                sort_keys=True,
                default=str,
            )
            if _should_store_raw_payload(store_raw_payload)
            else None
        )

        placeholder = _placeholder(
            self.database_url
        )

        values = (
            source,
            record_hash,
            "UNKNOWN",
            symbol,
            raw_payload,
            record_hash,
            utc_now(),
        )

        placeholders = ", ".join(
            placeholder
            for _ in values
        )

        with connect(self.database_url) as connection:
            if is_postgresql_url(self.database_url):
                cursor = connection.execute(
                    f"""
                    INSERT INTO insider_transactions (
                        source,
                        accession_number,
                        issuer_cik,
                        issuer_name,
                        raw_payload,
                        record_hash,
                        created_at
                    )
                    VALUES (
                        {placeholders}
                    )
                    RETURNING id
                    """,
                    values,
                )
                row = cursor.fetchone()

                if row is None:
                    raise RuntimeError(
                        "Compatibility insider insert did not return an id."
                    )

                row_id = _row_value(row, "id")
            else:
                cursor = connection.execute(
                    f"""
                    INSERT INTO insider_transactions (
                        source,
                        accession_number,
                        issuer_cik,
                        issuer_name,
                        raw_payload,
                        record_hash,
                        created_at
                    )
                    VALUES (
                        {placeholders}
                    )
                    """,
                    values,
                )

                row_id = cursor.lastrowid

            connection.commit()

        return {
            "table": "insider_transactions",
            "id": row_id,
            "record": dict(record),
    }
