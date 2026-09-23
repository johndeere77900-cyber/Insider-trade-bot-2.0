"""
Permanent backtest-result repository for Insider Trade Bot.

This module stores completed backtest runs and their simulated trades.
Backtest records are historical research artifacts and are completely
separate from live order execution.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from backtesting.engine import (
    BacktestResult,
    BacktestSummary,
)
from database.connection import connect
from storage.repository import utc_now


def store_backtest_result(
    database_url: str,
    *,
    run_id: str,
    methodology_version: str,
    result: BacktestResult,
) -> bool:
    """
    Store a completed backtest as a research event.

    Returns:
        True when inserted.
        False when the run already exists.

    Backtest results are stored in the existing research_events table so
    that research outputs remain centrally auditable.
    """

    normalized_run_id = str(
        run_id
    ).strip()

    if not normalized_run_id:
        raise ValueError(
            "run_id cannot be empty."
        )

    normalized_methodology = str(
        methodology_version
    ).strip()

    if not normalized_methodology:
        raise ValueError(
            "methodology_version cannot be empty."
        )

    if not isinstance(
        result,
        BacktestResult,
    ):
        raise TypeError(
            "result must be a BacktestResult."
        )

    summary = result.summary

    payload: dict[str, Any] = {
        "run_id": normalized_run_id,
        "methodology_version": normalized_methodology,
        "summary": asdict(summary),
        "trades": [
            asdict(trade)
            for trade in result.trades
        ],
    }

    event_key = (
        f"backtest:{normalized_run_id}"
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
                "backtest",
                None,
                None,
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


def get_backtest_result(
    database_url: str,
    run_id: str,
) -> dict[str, Any] | None:
    """
    Retrieve a stored backtest result.

    The returned dictionary contains the stored payload and metadata.
    """

    normalized_run_id = str(
        run_id
    ).strip()

    if not normalized_run_id:
        raise ValueError(
            "run_id cannot be empty."
        )

    event_key = (
        f"backtest:{normalized_run_id}"
    )

    with connect(database_url) as connection:
        row = connection.execute(
            """
            SELECT
                id,
                event_key,
                event_type,
                methodology_version,
                result_payload,
                created_at
            FROM research_events
            WHERE event_key = ?
              AND event_type = 'backtest'
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
            "Stored backtest result contains invalid JSON."
        ) from exc

    return {
        "id": row["id"],
        "event_key": row["event_key"],
        "event_type": row["event_type"],
        "methodology_version": (
            row["methodology_version"]
        ),
        "result": payload,
        "created_at": row["created_at"],
    }


def extract_backtest_summary(
    stored_result: dict[str, Any],
) -> BacktestSummary:
    """
    Convert a stored backtest payload back into a BacktestSummary model.
    """

    if not isinstance(
        stored_result,
        dict,
    ):
        raise TypeError(
            "stored_result must be a dictionary."
        )

    payload = stored_result.get(
        "result"
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise ValueError(
            "Stored backtest result has no valid result payload."
        )

    summary_data = payload.get(
        "summary"
    )

    if not isinstance(
        summary_data,
        dict,
    ):
        raise ValueError(
            "Stored backtest result has no valid summary."
        )

    return BacktestSummary(
        trade_count=int(
            summary_data["trade_count"]
        ),
        total_return_pct=summary_data[
            "total_return_pct"
        ],
        mean_trade_return_pct=summary_data[
            "mean_trade_return_pct"
        ],
        winning_trade_count=int(
            summary_data["winning_trade_count"]
        ),
        losing_trade_count=int(
            summary_data["losing_trade_count"]
        ),
        zero_return_trade_count=int(
            summary_data["zero_return_trade_count"]
        ),
        win_rate_pct=summary_data[
            "win_rate_pct"
        ],
        average_holding_periods=summary_data[
            "average_holding_periods"
        ],
      )
