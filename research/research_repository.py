"""
Permanent research-result repository for Insider Trade Bot.

This module stores completed research events and provides controlled
retrieval of those results from permanent storage.

Research storage is separate from signal generation and trading execution.
A stored research result does not authorize a trade.
"""

from __future__ import annotations

import json
from typing import Any

from database.connection import connect
from research.event_study import (
    EventReturn,
    EventStudySummary,
)
from storage.repository import utc_now


def store_research_event(
    database_url: str,
    *,
    event_key: str,
    event_type: str,
    symbol: str | None,
    event_date: str | None,
    methodology_version: str,
    result_payload: dict[str, Any],
) -> bool:
    """
    Store a research result permanently.

    Returns:
        True when a new record is inserted.
        False when the event_key already exists.

    Existing research results are not silently overwritten.
    """

    if not event_key.strip():
        raise ValueError(
            "event_key cannot be empty."
        )

    if not event_type.strip():
        raise ValueError(
            "event_type cannot be empty."
        )

    if not methodology_version.strip():
        raise ValueError(
            "methodology_version cannot be empty."
        )

    if not isinstance(result_payload, dict):
        raise TypeError(
            "result_payload must be a dictionary."
        )

    payload = json.dumps(
        result_payload,
        sort_keys=True,
        default=str,
    )

    with connect(database_url) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO research_events (
                event_key,
                event_type,
                symbol,
                event_date,
                methodology_version,
                result_payload,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_key,
                event_type,
                symbol,
                event_date,
                methodology_version,
                payload,
                utc_now(),
            ),
        )

        connection.commit()

        return cursor.rowcount == 1


def store_event_study_result(
    database_url: str,
    *,
    event_key: str,
    symbol: str,
    event_date: str,
    methodology_version: str,
    event_return: EventReturn,
) -> bool:
    """
    Store one completed event-study observation.
    """

    payload = {
        "event_return": {
            "event_key": event_return.event_key,
            "symbol": event_return.symbol,
            "event_date": event_return.event_date,
            "horizon_days": event_return.horizon_days,
            "event_price": event_return.event_price,
            "future_price": event_return.future_price,
            "return_pct": event_return.return_pct,
        }
    }

    return store_research_event(
        database_url,
        event_key=event_key,
        event_type="event_return",
        symbol=symbol,
        event_date=event_date,
        methodology_version=methodology_version,
        result_payload=payload,
    )


def store_event_study_summary(
    database_url: str,
    *,
    event_key: str,
    symbol: str | None,
    event_date: str | None,
    methodology_version: str,
    summary: EventStudySummary,
) -> bool:
    """
    Store an aggregate event-study summary.
    """

    payload = {
        "event_count": summary.event_count,
        "horizon_days": summary.horizon_days,
        "mean_return_pct": summary.mean_return_pct,
        "median_return_pct": summary.median_return_pct,
        "positive_event_count": summary.positive_event_count,
        "negative_event_count": summary.negative_event_count,
        "zero_return_event_count": summary.zero_return_event_count,
        "positive_event_rate_pct": (
            summary.positive_event_rate_pct
        ),
    }

    return store_research_event(
        database_url,
        event_key=event_key,
        event_type="event_study_summary",
        symbol=symbol,
        event_date=event_date,
        methodology_version=methodology_version,
        result_payload=payload,
    )


def get_research_event(
    database_url: str,
    event_key: str,
) -> dict[str, Any] | None:
    """
    Retrieve one research event by its unique event key.
    """

    if not event_key.strip():
        raise ValueError(
            "event_key cannot be empty."
        )

    with connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT
                id,
                event_key,
                event_type,
                symbol,
                event_date,
                methodology_version,
                result_payload,
                created_at
            FROM research_events
            WHERE event_key = ?
            """,
            (event_key,),
        ).fetchone()

    if row is None:
        return None

    try:
        result_payload = json.loads(
            row["result_payload"]
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Stored research result contains invalid JSON."
        ) from exc

    return {
        "id": row["id"],
        "event_key": row["event_key"],
        "event_type": row["event_type"],
        "symbol": row["symbol"],
        "event_date": row["event_date"],
        "methodology_version": row[
            "methodology_version"
        ],
        "result_payload": result_payload,
        "created_at": row["created_at"],
    }


def list_research_events(
    database_url: str,
    *,
    event_type: str | None = None,
    symbol: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Retrieve research events using optional filters.

    Results are returned newest first.
    """

    if limit < 1:
        raise ValueError(
            "limit must be at least 1."
        )

    query = """
        SELECT
            id,
            event_key,
            event_type,
            symbol,
            event_date,
            methodology_version,
            result_payload,
            created_at
        FROM research_events
        WHERE 1 = 1
    """

    parameters: list[Any] = []

    if event_type is not None:
        query += """
            AND event_type = ?
        """
        parameters.append(event_type)

    if symbol is not None:
        query += """
            AND symbol = ?
        """
        parameters.append(symbol)

    query += """
        ORDER BY created_at DESC
        LIMIT ?
    """

    parameters.append(limit)

    with connect(database_url) as connection:
        rows = connection.execute(
            query,
            parameters,
        ).fetchall()

    results: list[dict[str, Any]] = []

    for row in rows:
        try:
            result_payload = json.loads(
                row["result_payload"]
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Stored research result contains invalid JSON."
            ) from exc

        results.append(
            {
                "id": row["id"],
                "event_key": row["event_key"],
                "event_type": row["event_type"],
                "symbol": row["symbol"],
                "event_date": row["event_date"],
                "methodology_version": row[
                    "methodology_version"
                ],
                "result_payload": result_payload,
                "created_at": row["created_at"],
            }
        )

    return results
