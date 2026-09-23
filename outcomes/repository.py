"""
Permanent outcome repository for Insider Trade Bot.

This module stores historical signal outcomes as research records.

Outcome records do not modify the original signal and do not authorize
trading.
"""

from __future__ import annotations

import json
from typing import Any

from database.connection import connect
from outcomes.engine import SignalOutcome
from storage.repository import utc_now


def store_signal_outcome(
    database_url: str,
    outcome: SignalOutcome,
    *,
    methodology_version: str,
) -> bool:
    """
    Store one evaluated signal outcome permanently.

    Returns:
        True when inserted.
        False when the same outcome key already exists.
    """

    if not isinstance(
        outcome,
        SignalOutcome,
    ):
        raise TypeError(
            "outcome must be a SignalOutcome."
        )

    normalized_methodology = str(
        methodology_version
    ).strip()

    if not normalized_methodology:
        raise ValueError(
            "methodology_version cannot be empty."
        )

    event_key = (
        f"signal-outcome:"
        f"{outcome.signal_key}:"
        f"{outcome.evaluation_periods}"
    )

    payload: dict[str, Any] = {
        "signal_key": outcome.signal_key,
        "symbol": outcome.symbol,
        "signal_date": outcome.signal_date,
        "outcome_date": outcome.outcome_date,
        "signal_price": outcome.signal_price,
        "outcome_price": outcome.outcome_price,
        "return_pct": outcome.return_pct,
        "evaluation_periods": (
            outcome.evaluation_periods
        ),
    }

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
                "signal_outcome",
                outcome.symbol,
                outcome.signal_date,
                normalized_methodology,
                json.dumps(
                    payload,
                    sort_keys=True,
                    default=str,
                ),
                utc_now(),
            ),
        )

        connection.commit()

        return cursor.rowcount == 1


def get_signal_outcome(
    database_url: str,
    *,
    signal_key: str,
    evaluation_periods: int,
) -> dict[str, Any] | None:
    """
    Retrieve one stored signal outcome.
    """

    normalized_signal_key = str(
        signal_key
    ).strip()

    if not normalized_signal_key:
        raise ValueError(
            "signal_key cannot be empty."
        )

    if evaluation_periods < 1:
        raise ValueError(
            "evaluation_periods must be at least 1."
        )

    event_key = (
        f"signal-outcome:"
        f"{normalized_signal_key}:"
        f"{evaluation_periods}"
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
              AND event_type = 'signal_outcome'
            """,
            (event_key,),
        ).fetchone()

    if row is None:
        return None

    try:
        payload = json.loads(
            row["result_payload"]
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Stored signal outcome contains invalid JSON."
        ) from exc

    return {
        "id": row["id"],
        "event_key": row["event_key"],
        "event_type": row["event_type"],
        "symbol": row["symbol"],
        "event_date": row["event_date"],
        "methodology_version": (
            row["methodology_version"]
        ),
        "result": payload,
        "created_at": row["created_at"],
    }


def list_signal_outcomes(
    database_url: str,
    *,
    symbol: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Retrieve stored signal outcomes.

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
        WHERE event_type = 'signal_outcome'
    """

    parameters: list[Any] = []

    if symbol is not None:
        normalized_symbol = str(
            symbol
        ).strip()

        if not normalized_symbol:
            raise ValueError(
                "symbol cannot be empty."
            )

        query += """
            AND symbol = ?
        """

        parameters.append(
            normalized_symbol
        )

    query += """
        ORDER BY event_date DESC, created_at DESC
        LIMIT ?
    """

    parameters.append(
        limit
    )

    with connect(database_url) as connection:
        rows = connection.execute(
            query,
            parameters,
        ).fetchall()

    results: list[dict[str, Any]] = []

    for row in rows:
        try:
            payload = json.loads(
                row["result_payload"]
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Stored signal outcome contains invalid JSON."
            ) from exc

        results.append(
            {
                "id": row["id"],
                "event_key": row["event_key"],
                "event_type": row["event_type"],
                "symbol": row["symbol"],
                "event_date": row["event_date"],
                "methodology_version": (
                    row["methodology_version"]
                ),
                "result": payload,
                "created_at": row["created_at"],
            }
        )

    return results
