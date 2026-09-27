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
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL support requires the psycopg package."
            ) from exc

        return psycopg.connect(database_url)

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
        insider_name TEXT,
        insider_cik TEXT,
        transaction_date TEXT,
        filing_date TEXT,
        form_type TEXT,
        transaction_code TEXT,
        shares DOUBLE PRECISION,
        price DOUBLE PRECISION,
        ownership_type TEXT,
        raw_payload TEXT,
        record_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (
            source,
            accession_number,
            record_hash
        )
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
        validation_status TEXT NOT NULL
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
        insider_name TEXT,
        insider_cik TEXT,
        transaction_date TEXT,
        filing_date TEXT,
        form_type TEXT,
        transaction_code TEXT,
        shares REAL,
        price REAL,
        ownership_type TEXT,
        raw_payload TEXT,
        record_hash TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (
            source,
            accession_number,
            record_hash
        )
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
        validation_status TEXT NOT NULL
    );
    """


def initialize_database(database_url: str) -> Any:
    """
    Create and initialize the configured database.

    The existing SQLite backend remains supported for local testing.
    PostgreSQL is supported for persistent deployment.
    """

    if is_sqlite_url(database_url):
        database_path = get_database_path(database_url)

        with sqlite3.connect(database_path) as connection:
            connection.executescript(
                _sqlite_schema()
            )
            connection.commit()

        return database_path

    if is_postgresql_url(database_url):
        connection = connect(database_url)

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    _postgres_schema()
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
