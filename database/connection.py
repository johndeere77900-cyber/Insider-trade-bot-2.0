"""
Database connection and initialization layer for Insider Trade Bot.

This module is responsible for creating the local database and establishing
database connections. It does not contain research, trading, or strategy
logic.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def get_database_path(database_url: str) -> Path:
    """
    Convert a SQLite database URL into a filesystem path.

    Currently supported format:

        sqlite:///path/to/database.db
    """

    prefix = "sqlite:///"

    if not database_url.startswith(prefix):
        raise ValueError(
            "Unsupported database URL. "
            "The current database layer requires a sqlite:/// URL."
        )

    database_path = Path(database_url[len(prefix):])

    database_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return database_path


def connect(database_url: str) -> sqlite3.Connection:
    """
    Create and return a SQLite database connection.

    Foreign-key enforcement is enabled for every connection.
    """

    database_path = get_database_path(database_url)

    connection = sqlite3.connect(database_path)

    connection.row_factory = sqlite3.Row

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


def initialize_database(database_url: str) -> Path:
    """
    Create the database file and initialize the core database schema.

    This creates the foundational tables required by the agent.
    """

    database_path = get_database_path(database_url)

    schema = """
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

    with sqlite3.connect(database_path) as connection:
        connection.executescript(schema)
        connection.commit()

    return database_path
