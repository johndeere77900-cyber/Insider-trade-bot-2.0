"""
Database connection and initialization layer for Insider Trade Bot.

Supported backends:
    - SQLite
    - PostgreSQL

The database URL determines the backend.

SQLite:
    sqlite:///data/insider_trade_bot.db

PostgreSQL:
    postgresql://user:password@host:5432/database
    postgres://user:password@host:5432/database

This module contains database connectivity and schema initialization only.
It does not contain research, trading, or strategy logic.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


POSTGRES_PREFIXES = (
    "postgresql://",
    "postgres://",
)


def is_postgresql_url(database_url: str) -> bool:
    """Return whether the configured URL targets PostgreSQL."""
    return database_url.startswith(POSTGRES_PREFIXES)


def is_sqlite_url(database_url: str) -> bool:
    """Return whether the configured URL targets SQLite."""
    return database_url.startswith("sqlite:///")


def get_database_path(database_url: str) -> Path:
    """
    Convert a SQLite database URL into a filesystem path.

    PostgreSQL URLs are not filesystem paths and must not be passed
    to this function.
    """

    prefix = "sqlite:///"

    if not database_url.startswith(prefix):
        raise ValueError(
            "get_database_path() requires a sqlite:/// database URL."
        )

    database_path = Path(database_url[len(prefix):])

    database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return database_path


def connect(database_url: str) -> Any:
    """
    Create a database connection for the configured backend.

    SQLite uses the standard-library sqlite3 driver.

    PostgreSQL uses psycopg 3.
    """

    if is_sqlite_url(database_url):
        database_path = get_database_path(database_url)

        connection = sqlite3.connect(database_path)

        connection.row_factory = sqlite3.Row

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        return connection

    if is_postgresql_url(database_url):
        try:
            import psycopg
            import psycopg.conninfo
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL support requires the psycopg package."
            ) from exc

        import socket

        kwargs = psycopg.conninfo.conninfo_to_dict(database_url)
        host = kwargs.get("host")

        if host and not host.startswith("/") and not host.startswith("."):
            try:
                addrinfo = socket.getaddrinfo(
                    host, None, family=socket.AF_INET, type=socket.SOCK_STREAM
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Could not resolve an IPv4 address for PostgreSQL host: {host}"
                ) from exc

            if not addrinfo:
                raise RuntimeError(
                    f"Could not resolve an IPv4 address for PostgreSQL host: {host}"
                )

            ipv4_address = addrinfo[0][4][0]
            kwargs["hostaddr"] = ipv4_address

        return psycopg.connect(**kwargs)

    raise ValueError(
        "Unsupported database URL. "
        "Use sqlite:///... or postgresql://..."
    )


def _postgres_schema() -> str:
    """Return the PostgreSQL database schema."""

    return """
    CREATE TABLE IF NOT EXISTS insider_transactions (
        id BIGSERIAL PRIMARY KEY,
        source TEXT NOT NULL,
        accession_number TEXT NOT NULL,
        issuer_cik TEXT NOT NULL,
        issuer_name TEXT,
        ticker TEXT,
        insider_name TEXT,
        insider_cik TEXT,
        transaction_date TEXT,
        filing_date TEXT,
        form_type TEXT,
        transaction_code TEXT,
        security_title TEXT,
        shares DOUBLE PRECISION,
        price DOUBLE PRECISION,
        transaction_type TEXT,
        acquired_disposed TEXT,
        ownership_type TEXT,
        ownership_nature TEXT,
        source_url TEXT,
        is_amendment BOOLEAN DEFAULT FALSE,
        date_of_orig_submission TEXT,
        raw_payload TEXT,
        record_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (
            source,
            accession_number,
            record_hash
        )
    );

    CREATE TABLE IF NOT EXISTS ingestion_state (
        id BIGSERIAL PRIMARY KEY,
        period TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL,
        records_parsed BIGINT DEFAULT 0,
        records_inserted BIGINT DEFAULT 0,
        duplicates_count BIGINT DEFAULT 0,
        invalid_count BIGINT DEFAULT 0,
        failures_count BIGINT DEFAULT 0,
        completed_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS market_prices (
        id BIGSERIAL PRIMARY KEY,
        symbol TEXT NOT NULL,
        price_date TEXT NOT NULL,
        open DOUBLE PRECISION,
        high DOUBLE PRECISION,
        low DOUBLE PRECISION,
        close DOUBLE PRECISION,
        adjusted_close DOUBLE PRECISION,
        volume DOUBLE PRECISION,
        source TEXT NOT NULL,
        record_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (
            symbol,
            price_date,
            source
        )
    );

    CREATE TABLE IF NOT EXISTS corporate_actions (
        id BIGSERIAL PRIMARY KEY,
        symbol TEXT NOT NULL,
        action_type TEXT NOT NULL,
        action_date TEXT NOT NULL,
        ratio TEXT,
        cash_amount DOUBLE PRECISION,
        source TEXT NOT NULL,
        raw_payload TEXT,
        record_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS research_events (
        id BIGSERIAL PRIMARY KEY,
        event_key TEXT NOT NULL UNIQUE,
        event_type TEXT NOT NULL,
        symbol TEXT,
        event_date TEXT,
        methodology_version TEXT NOT NULL,
        result_payload TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS signals (
        id BIGSERIAL PRIMARY KEY,
        signal_key TEXT NOT NULL UNIQUE,
        symbol TEXT NOT NULL,
        signal_date TEXT NOT NULL,
        signal_type TEXT NOT NULL,
        score DOUBLE PRECISION,
        rationale TEXT,
        methodology_version TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS trade_runs (
        id BIGSERIAL PRIMARY KEY,
        run_id TEXT NOT NULL UNIQUE,
        mode TEXT NOT NULL
            CHECK (
                mode IN ('paper', 'live')
            ),
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        details TEXT
    );

    CREATE TABLE IF NOT EXISTS provenance (
        id BIGSERIAL PRIMARY KEY,
        record_type TEXT NOT NULL,
        record_id TEXT NOT NULL,
        source TEXT NOT NULL,
        source_reference TEXT,
        retrieved_at TEXT NOT NULL,
        checksum TEXT,
        validation_status TEXT NOT NULL,
        UNIQUE (record_type, record_id, source)
    );
    """


def _sqlite_schema() -> str:
    """Return the SQLite database schema."""

    return """
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS insider_transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT NOT NULL,
        accession_number TEXT NOT NULL,
        issuer_cik TEXT NOT NULL,
        issuer_name TEXT,
        ticker TEXT,
        insider_name TEXT,
        insider_cik TEXT,
        transaction_date TEXT,
        filing_date TEXT,
        form_type TEXT,
        transaction_code TEXT,
        security_title TEXT,
        shares REAL,
        price REAL,
        transaction_type TEXT,
        ownership_type TEXT,
        ownership_nature TEXT,
        source_url TEXT,
        is_amendment INTEGER DEFAULT 0,
        date_of_orig_submission TEXT,
        raw_payload TEXT,
        record_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (
            source,
            accession_number,
            record_hash
        )
    );

    CREATE TABLE IF NOT EXISTS ingestion_state (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL,
        records_parsed INTEGER DEFAULT 0,
        records_inserted INTEGER DEFAULT 0,
        duplicates_count INTEGER DEFAULT 0,
        invalid_count INTEGER DEFAULT 0,
        failures_count INTEGER DEFAULT 0,
        completed_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS market_prices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        price_date TEXT NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        adjusted_close REAL,
        volume REAL,
        source TEXT NOT NULL,
        record_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (
            symbol,
            price_date,
            source
        )
    );

    CREATE TABLE IF NOT EXISTS corporate_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        action_type TEXT NOT NULL,
        action_date TEXT NOT NULL,
        ratio TEXT,
        cash_amount REAL,
        source TEXT NOT NULL,
        raw_payload TEXT,
        record_hash TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS research_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_key TEXT NOT NULL UNIQUE,
        event_type TEXT NOT NULL,
        symbol TEXT,
        event_date TEXT,
        methodology_version TEXT NOT NULL,
        result_payload TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        signal_key TEXT NOT NULL UNIQUE,
        symbol TEXT NOT NULL,
        signal_date TEXT NOT NULL,
        signal_type TEXT NOT NULL,
        score REAL,
        rationale TEXT,
        methodology_version TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS trade_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL UNIQUE,
        mode TEXT NOT NULL
            CHECK (
                mode IN ('paper', 'live')
            ),
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        details TEXT
    );

    CREATE TABLE IF NOT EXISTS provenance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        record_type TEXT NOT NULL,
        record_id TEXT NOT NULL,
        source TEXT NOT NULL,
        source_reference TEXT,
        retrieved_at TEXT NOT NULL,
        checksum TEXT,
        validation_status TEXT NOT NULL,
        UNIQUE (record_type, record_id, source)
    );
    """


def initialize_database(database_url: str) -> Any:
    """
    Create and initialize the configured database, including migration
    of new columns on existing tables.

    The existing SQLite backend remains supported for local testing.
    PostgreSQL is supported for persistent deployment.
    """

    if is_sqlite_url(database_url):
        database_path = get_database_path(database_url)

        with sqlite3.connect(database_path) as connection:
            connection.executescript(_sqlite_schema())

            # Migration for SQLite: Add missing columns to pre-existing tables if needed
            cursor = connection.cursor()
            cursor.execute("PRAGMA table_info(insider_transactions)")
            existing_cols = {row[1] for row in cursor.fetchall()}

            new_columns = [
                ("ticker", "TEXT"),
                ("security_title", "TEXT"),
                ("transaction_type", "TEXT"),
                ("acquired_disposed", "TEXT"),
                ("ownership_nature", "TEXT"),
                ("source_url", "TEXT"),
                ("is_amendment", "INTEGER"),
                ("date_of_orig_submission", "TEXT"),
            ]

            for col_name, col_type in new_columns:
                if col_name not in existing_cols:
                    connection.execute(
                        f"ALTER TABLE insider_transactions ADD COLUMN {col_name} {col_type}"
                    )

            # Ensure indexes exist for insider_transactions query optimization
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_insider_tx_dates ON insider_transactions (transaction_date, filing_date);"
            )

            connection.commit()

        return database_path

    if is_postgresql_url(database_url):
        connection = connect(database_url)

        try:
            with connection.cursor() as cursor:
                cursor.execute(_postgres_schema())

                # Migration for PostgreSQL: Add missing columns to pre-existing tables if needed
                alter_queries = [
                    "ALTER TABLE insider_transactions ADD COLUMN IF NOT EXISTS ticker TEXT;",
                    "ALTER TABLE insider_transactions ADD COLUMN IF NOT EXISTS security_title TEXT;",
                    "ALTER TABLE insider_transactions ADD COLUMN IF NOT EXISTS transaction_type TEXT;",
                    "ALTER TABLE insider_transactions ADD COLUMN IF NOT EXISTS acquired_disposed TEXT;",
                    "ALTER TABLE insider_transactions ADD COLUMN IF NOT EXISTS ownership_nature TEXT;",
                    "ALTER TABLE insider_transactions ADD COLUMN IF NOT EXISTS source_url TEXT;",
                    "ALTER TABLE insider_transactions ADD COLUMN IF NOT EXISTS is_amendment BOOLEAN DEFAULT FALSE;",
                    "ALTER TABLE insider_transactions ADD COLUMN IF NOT EXISTS date_of_orig_submission TEXT;",
                ]

                for query in alter_queries:
                    cursor.execute(query)

                # Ensure PostgreSQL indexes exist
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_insider_tx_dates ON insider_transactions (transaction_date, filing_date);"
                )

            connection.commit()

        finally:
            connection.close()

        return database_url

    raise ValueError(
        "Unsupported database URL. "
        "Use sqlite:///... or postgresql://..."
    )


class DatabaseConnection:
    """
    Compatibility interface for the database layer.

    The backend is selected automatically from database_url.
    """

    def __init__(self, database_url: str) -> None:
        if not database_url or not database_url.strip():
            raise ValueError(
                "database_url is required."
            )

        self.database_url = database_url.strip()

    def connect(self) -> Any:
        """Open a connection to the configured database."""

        return connect(
            self.database_url
        )

    def initialize(self) -> Any:
        """Initialize the configured database schema."""

        return initialize_database(
            self.database_url
    )
