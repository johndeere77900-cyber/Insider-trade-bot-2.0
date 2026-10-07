"""
Ticker Universe Helper for Insider Trade Bot.

Extracts deterministic ticker universes from SEC insider transaction data.
"""

from __future__ import annotations

from dataclasses import dataclass

from database.connection import connect, initialize_database, is_postgresql_url


@dataclass(frozen=True)
class TickerUniverseResult:
    """Diagnostic result for ticker universe extraction."""

    tickers: tuple[str, ...]
    unique_ticker_count: int
    source_transaction_count: int


def get_ticker_universe(
    database_url: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> TickerUniverseResult:
    """
    Extract a deterministic ticker universe from stored insider_transactions records.

    Rules:
        - Exclude NULL/blank tickers.
        - Trim whitespace.
        - Normalize uppercase.
        - Deduplicate.
        - Return deterministic alphabetical ordering.
        - Optionally filter by transaction_date or filing_date range.
        - Report total source transactions scanned and unique tickers found.
    """
    initialize_database(database_url)

    placeholder = "%s" if is_postgresql_url(database_url) else "?"

    query = """
        SELECT ticker, filing_date, transaction_date
        FROM insider_transactions
        WHERE ticker IS NOT NULL
          AND ticker != ''
    """
    params: list[str] = []

    if start_date is not None or end_date is not None:
        norm_start = str(start_date).strip() if start_date else "0000-01-01"
        norm_end = str(end_date).strip() if end_date else "9999-12-31"

        query += f"""
            AND (
                (filing_date IS NOT NULL AND filing_date >= {placeholder} AND filing_date <= {placeholder})
                OR
                (transaction_date IS NOT NULL AND transaction_date >= {placeholder} AND transaction_date <= {placeholder})
            )
        """
        params.extend([norm_start, norm_end, norm_start, norm_end])

    with connect(database_url) as connection:
        cursor = connection.execute(query, tuple(params))
        rows = cursor.fetchall()

    source_transaction_count = len(rows)
    unique_tickers: set[str] = set()

    for row in rows:
        raw_ticker = row[0] if isinstance(row, (tuple, list)) else row["ticker"]
        if raw_ticker is None:
            continue
        cleaned = str(raw_ticker).strip().upper()
        if cleaned:
            unique_tickers.add(cleaned)

    sorted_tickers = tuple(sorted(unique_tickers))

    return TickerUniverseResult(
        tickers=sorted_tickers,
        unique_ticker_count=len(sorted_tickers),
        source_transaction_count=source_transaction_count,
    )
