"""
Historical-data loading utilities for Insider Trade Bot.

This module provides controlled loading of historical records into the
ingestion pipeline. It does not decide which records are historically
complete; source coverage and reconciliation remain separate concerns.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from data.ingestion_pipeline import (
    IngestionError,
    ingest_batch,
)


@dataclass(frozen=True)
class HistoricalLoadResult:
    """
    Result of one historical-data loading operation.
    """

    record_type: str
    source: str

    attempted_count: int
    accepted_count: int

    record_hashes: tuple[str, ...]


class HistoricalLoadError(Exception):
    """Raised when a historical-data load cannot be completed safely."""


def load_historical_records(
    database_url: str,
    records: Iterable[Mapping[str, Any]],
    *,
    record_type: str,
    source: str,
) -> HistoricalLoadResult:
    """
    Load a collection of historical records through the controlled
    ingestion pipeline.

    The records must already have been retrieved from an external source.
    This function does not bypass normalization or validation.
    """

    normalized_type = str(
        record_type
    ).strip().lower()

    normalized_source = str(
        source
    ).strip()

    if not normalized_source:
        raise HistoricalLoadError(
            "source cannot be empty."
        )

    record_list = list(records)

    attempted_count = len(
        record_list
    )

    if attempted_count == 0:
        return HistoricalLoadResult(
            record_type=normalized_type,
            source=normalized_source,
            attempted_count=0,
            accepted_count=0,
            record_hashes=(),
        )

    try:
        record_hashes = ingest_batch(
            database_url,
            record_list,
            record_type=normalized_type,
            source=normalized_source,
        )
    except (
        IngestionError,
        TypeError,
        ValueError,
    ) as exc:
        raise HistoricalLoadError(
            f"Historical load failed: {exc}"
        ) from exc

    return HistoricalLoadResult(
        record_type=normalized_type,
        source=normalized_source,
        attempted_count=attempted_count,
        accepted_count=len(record_hashes),
        record_hashes=tuple(
            record_hashes
        ),
    )


def load_historical_insider_transactions(
    database_url: str,
    records: Iterable[Mapping[str, Any]],
    *,
    source: str,
) -> HistoricalLoadResult:
    """
    Load historical insider transactions.
    """

    return load_historical_records(
        database_url,
        records,
        record_type="insider_transaction",
        source=source,
    )


def load_historical_market_prices(
    database_url: str,
    records: Iterable[Mapping[str, Any]],
    *,
    source: str,
) -> HistoricalLoadResult:
    """
    Load historical market-price records.
    """

    return load_historical_records(
        database_url,
        records,
        record_type="market_price",
        source=source,
    )


def load_historical_corporate_actions(
    database_url: str,
    records: Iterable[Mapping[str, Any]],
    *,
    source: str,
) -> HistoricalLoadResult:
    """
    Load historical corporate-action records.
    """

    return load_historical_records(
        database_url,
        records,
        record_type="corporate_action",
        source=source,
        )
