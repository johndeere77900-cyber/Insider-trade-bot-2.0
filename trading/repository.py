"""
Trading-run repository for Insider Trade Bot.

This module records paper and live trading runs in permanent storage.

It does not execute trades. Execution remains isolated inside the trading
engines.
"""

from __future__ import annotations

from database.connection import connect
from storage.repository import utc_now


VALID_MODES = {
    "paper",
    "live",
}

VALID_STATUSES = {
    "created",
    "running",
    "completed",
    "failed",
    "cancelled",
}


def create_trade_run(
    database_url: str,
    *,
    run_id: str,
    mode: str,
    details: str | None = None,
) -> bool:
    """
    Create a permanent trading-run record.

    Returns:
        True when the run is newly created.
        False when the run_id already exists.
    """

    normalized_run_id = str(
        run_id
    ).strip()

    if not normalized_run_id:
        raise ValueError(
            "run_id cannot be empty."
        )

    normalized_mode = str(
        mode
    ).strip().lower()

    if normalized_mode not in VALID_MODES:
        raise ValueError(
            "mode must be either 'paper' or 'live'."
        )

    with connect(database_url) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO trade_runs (
                run_id,
                mode,
                status,
                started_at,
                completed_at,
                details
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                normalized_run_id,
                normalized_mode,
                "created",
                utc_now(),
                None,
                details,
            ),
        )

        connection.commit()

        return cursor.rowcount == 1


def update_trade_run_status(
    database_url: str,
    *,
    run_id: str,
    status: str,
    details: str | None = None,
) -> bool:
    """
    Update the status of an existing trading run.

    Returns:
        True when a matching run was updated.
        False when no matching run exists.
    """

    normalized_run_id = str(
        run_id
    ).strip()

    if not normalized_run_id:
        raise ValueError(
            "run_id cannot be empty."
        )

    normalized_status = str(
        status
    ).strip().lower()

    if normalized_status not in VALID_STATUSES:
        raise ValueError(
            "Unsupported trading-run status."
        )

    completed_at = None

    if normalized_status in {
        "completed",
        "failed",
        "cancelled",
    }:
        completed_at = utc_now()

    with connect(database_url) as connection:
        cursor = connection.execute(
            """
            UPDATE trade_runs
            SET
                status = ?,
                completed_at = ?,
                details = ?
            WHERE run_id = ?
            """,
            (
                normalized_status,
                completed_at,
                details,
                normalized_run_id,
            ),
        )

        connection.commit()

        return cursor.rowcount == 1


def get_trade_run(
    database_url: str,
    run_id: str,
) -> dict[str, object] | None:
    """
    Retrieve one trading-run record by run ID.
    """

    normalized_run_id = str(
        run_id
    ).strip()

    if not normalized_run_id:
        raise ValueError(
            "run_id cannot be empty."
        )

    with connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT
                id,
                run_id,
                mode,
                status,
                started_at,
                completed_at,
                details
            FROM trade_runs
            WHERE run_id = ?
            """,
            (normalized_run_id,),
        ).fetchone()

    if row is None:
        return None

    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "mode": row["mode"],
        "status": row["status"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "details": row["details"],
    }


def list_trade_runs(
    database_url: str,
    *,
    mode: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, object]]:
    """
    Retrieve trading runs using optional mode and status filters.
    """

    if limit < 1:
        raise ValueError(
            "limit must be at least 1."
        )

    query = """
        SELECT
            id,
            run_id,
            mode,
            status,
            started_at,
            completed_at,
            details
        FROM trade_runs
        WHERE 1 = 1
    """

    parameters: list[object] = []

    if mode is not None:
        normalized_mode = str(
            mode
        ).strip().lower()

        if normalized_mode not in VALID_MODES:
            raise ValueError(
                "Unsupported trading mode."
            )

        query += """
            AND mode = ?
        """

        parameters.append(
            normalized_mode
        )

    if status is not None:
        normalized_status = str(
            status
        ).strip().lower()

        if normalized_status not in VALID_STATUSES:
            raise ValueError(
                "Unsupported trading-run status."
            )

        query += """
            AND status = ?
        """

        parameters.append(
            normalized_status
        )

    query += """
        ORDER BY started_at DESC
        LIMIT ?
    """

    parameters.append(limit)

    with connect(database_url) as connection:
        rows = connection.execute(
            query,
            parameters,
        ).fetchall()

    return [
        {
            "id": row["id"],
            "run_id": row["run_id"],
            "mode": row["mode"],
            "status": row["status"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "details": row["details"],
        }
        for row in rows
  ]
