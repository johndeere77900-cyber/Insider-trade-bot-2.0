"""
Permanent signal repository for Insider Trade Bot.

This module stores research-derived signal candidates in permanent
storage. Storing a signal does not place an order or authorize trading.

Supports both SQLite and PostgreSQL backends via database_url abstraction.
"""

from __future__ import annotations

from typing import Any, Mapping

from core.models import Signal
from database.connection import connect, initialize_database, is_postgresql_url
from storage.repository import utc_now


def _placeholder(database_url: str) -> str:
    """Return the backend parameter placeholder."""
    return "%s" if is_postgresql_url(database_url) else "?"


def _row_val(row: Any, key: str, index: int) -> Any:
    """Safely extract field from mapping or tuple row."""
    if row is None:
        return None
    if isinstance(row, Mapping) or hasattr(row, "keys"):
        return row[key]
    return row[index]


def store_signal(
    database_url: str,
    signal: Signal,
) -> bool:
    """
    Store a signal permanently.

    Returns:
        True when a new signal is inserted.
        False when the signal already exists.

    Existing signals are never silently overwritten.
    """

    if not signal.signal_key.strip():
        raise ValueError(
            "signal_key cannot be empty."
        )

    if not signal.symbol.strip():
        raise ValueError(
            "symbol cannot be empty."
        )

    if not signal.signal_date.strip():
        raise ValueError(
            "signal_date cannot be empty."
        )

    if not signal.signal_type.strip():
        raise ValueError(
            "signal_type cannot be empty."
        )

    if not signal.methodology_version.strip():
        raise ValueError(
            "methodology_version cannot be empty."
        )

    initialize_database(database_url)
    ph = _placeholder(database_url)

    with connect(database_url) as connection:
        if is_postgresql_url(database_url):
            query = f"""
                INSERT INTO signals (
                    signal_key,
                    symbol,
                    signal_date,
                    signal_type,
                    score,
                    rationale,
                    methodology_version,
                    created_at
                )
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                ON CONFLICT (signal_key) DO NOTHING
            """
            with connection.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        signal.signal_key,
                        signal.symbol,
                        signal.signal_date,
                        signal.signal_type,
                        signal.score,
                        signal.rationale,
                        signal.methodology_version,
                        utc_now(),
                    ),
                )
                inserted = cursor.rowcount == 1
        else:
            query = f"""
                INSERT OR IGNORE INTO signals (
                    signal_key,
                    symbol,
                    signal_date,
                    signal_type,
                    score,
                    rationale,
                    methodology_version,
                    created_at
                )
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """
            cursor = connection.execute(
                query,
                (
                    signal.signal_key,
                    signal.symbol,
                    signal.signal_date,
                    signal.signal_type,
                    signal.score,
                    signal.rationale,
                    signal.methodology_version,
                    utc_now(),
                ),
            )
            inserted = cursor.rowcount == 1

        connection.commit()

        return inserted


def get_signal(
    database_url: str,
    signal_key: str,
) -> Signal | None:
    """
    Retrieve one signal by its unique signal key.
    """

    normalized_key = str(
        signal_key
    ).strip()

    if not normalized_key:
        raise ValueError(
            "signal_key cannot be empty."
        )

    initialize_database(database_url)
    ph = _placeholder(database_url)

    with connect(database_url) as connection:
        cursor = connection.execute(
            f"""
            SELECT
                signal_key,
                symbol,
                signal_date,
                signal_type,
                score,
                rationale,
                methodology_version
            FROM signals
            WHERE signal_key = {ph}
            """,
            (normalized_key,),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    return Signal(
        signal_key=_row_val(row, "signal_key", 0),
        symbol=_row_val(row, "symbol", 1),
        signal_date=_row_val(row, "signal_date", 2),
        signal_type=_row_val(row, "signal_type", 3),
        score=_row_val(row, "score", 4),
        rationale=_row_val(row, "rationale", 5),
        methodology_version=_row_val(row, "methodology_version", 6),
    )


def list_signals(
    database_url: str,
    *,
    symbol: str | None = None,
    signal_type: str | None = None,
    limit: int = 100,
) -> list[Signal]:
    """
    Retrieve stored signals using optional filters.

    Results are returned newest first.
    """

    if limit < 1:
        raise ValueError(
            "limit must be at least 1."
        )

    initialize_database(database_url)
    ph = _placeholder(database_url)

    query = """
        SELECT
            signal_key,
            symbol,
            signal_date,
            signal_type,
            score,
            rationale,
            methodology_version
        FROM signals
        WHERE 1 = 1
    """

    parameters: list[object] = []

    if symbol is not None:
        query += f"""
            AND symbol = {ph}
        """
        parameters.append(
            symbol.strip()
        )

    if signal_type is not None:
        query += f"""
            AND signal_type = {ph}
        """
        parameters.append(
            signal_type.strip()
        )

    query += f"""
        ORDER BY signal_date DESC, created_at DESC
        LIMIT {ph}
    """

    parameters.append(limit)

    with connect(database_url) as connection:
        cursor = connection.execute(
            query,
            parameters,
        )
        rows = cursor.fetchall()

    return [
        Signal(
            signal_key=_row_val(row, "signal_key", 0),
            symbol=_row_val(row, "symbol", 1),
            signal_date=_row_val(row, "signal_date", 2),
            signal_type=_row_val(row, "signal_type", 3),
            score=_row_val(row, "score", 4),
            rationale=_row_val(row, "rationale", 5),
            methodology_version=_row_val(row, "methodology_version", 6),
        )
        for row in rows
    ]


def count_signals(
    database_url: str,
) -> int:
    """
    Return the number of permanently stored signals.
    """

    initialize_database(database_url)

    with connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM signals
            """
        ).fetchone()

    if row is None:
        return 0

    return int(_row_val(row, "count", 0))
