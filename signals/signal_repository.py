"""
Permanent signal repository for Insider Trade Bot.

This module stores research-derived signal candidates in permanent
storage. Storing a signal does not place an order or authorize trading.
"""

from __future__ import annotations

from core.models import Signal
from database.connection import connect
from storage.repository import utc_now


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

    with connect(database_url) as connection:
        cursor = connection.execute(
            """
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
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

        connection.commit()

        return cursor.rowcount == 1


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

    with connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT
                signal_key,
                symbol,
                signal_date,
                signal_type,
                score,
                rationale,
                methodology_version
            FROM signals
            WHERE signal_key = ?
            """,
            (normalized_key,),
        ).fetchone()

    if row is None:
        return None

    return Signal(
        signal_key=row["signal_key"],
        symbol=row["symbol"],
        signal_date=row["signal_date"],
        signal_type=row["signal_type"],
        score=row["score"],
        rationale=row["rationale"],
        methodology_version=row[
            "methodology_version"
        ],
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
        query += """
            AND symbol = ?
        """
        parameters.append(
            symbol.strip()
        )

    if signal_type is not None:
        query += """
            AND signal_type = ?
        """
        parameters.append(
            signal_type.strip()
        )

    query += """
        ORDER BY signal_date DESC, created_at DESC
        LIMIT ?
    """

    parameters.append(limit)

    with connect(database_url) as connection:
        rows = connection.execute(
            query,
            parameters,
        ).fetchall()

    return [
        Signal(
            signal_key=row["signal_key"],
            symbol=row["symbol"],
            signal_date=row["signal_date"],
            signal_type=row["signal_type"],
            score=row["score"],
            rationale=row["rationale"],
            methodology_version=row[
                "methodology_version"
            ],
        )
        for row in rows
    ]


def count_signals(
    database_url: str,
) -> int:
    """
    Return the number of permanently stored signals.
    """

    with connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM signals
            """
        ).fetchone()

    return int(
        row["count"]
  )
