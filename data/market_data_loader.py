"""
Market-data loading layer for Insider Trade Bot.

This module converts provider responses into normalized market-price
records and sends them through the standard validation, storage, and
provenance pipeline.

It does not bypass validation or write directly to the database.
"""

from __future__ import annotations

from typing import Any, Mapping

from data.ingestion_pipeline import (
    IngestionError,
    ingest_market_price,
)
from data.normalization import (
    NormalizationError,
)


class MarketDataLoadError(Exception):
    """Raised when market-data loading fails."""


def _extract_records(
    payload: Any,
) -> list[Mapping[str, Any]]:
    """
    Extract market-price records from a provider response.

    Supported response shapes:

        1. A direct list of records.
        2. A mapping containing a list under:
           data, results, prices, historical, or records.
    """

    if isinstance(payload, list):
        records = payload

    elif isinstance(payload, Mapping):
        records = None

        for key in (
            "data",
            "results",
            "prices",
            "historical",
            "records",
        ):
            candidate = payload.get(key)

            if isinstance(candidate, list):
                records = candidate
                break

        if records is None:
            raise MarketDataLoadError(
                "Market-data response does not contain "
                "a supported record list."
            )

    else:
        raise MarketDataLoadError(
            "Market-data response must be a list or mapping."
        )

    normalized: list[Mapping[str, Any]] = []

    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise MarketDataLoadError(
                f"Market-price record {index} "
                "is not an object."
            )

        normalized.append(record)

    return normalized


def load_market_prices(
    database_url: str,
    payload: Any,
    *,
    source: str,
    source_reference: str | None = None,
) -> tuple[str, ...]:
    """
    Normalize, validate, store, and provenance-track market-price records.

    Returns:
        Tuple containing deterministic record hashes for accepted records.

    No record is silently substituted when normalization or validation
    fails.
    """

    normalized_source = str(source).strip()

    if not normalized_source:
        raise MarketDataLoadError(
            "source cannot be empty."
        )

    records = _extract_records(payload)

    hashes: list[str] = []

    for index, record in enumerate(records):
        try:
            record_hash = ingest_market_price(
                database_url,
                record,
                source=normalized_source,
                source_reference=source_reference,
            )

        except (
            IngestionError,
            NormalizationError,
            TypeError,
            ValueError,
        ) as exc:
            raise MarketDataLoadError(
                "Market-price ingestion failed at "
                f"record {index}: {exc}"
            ) from exc

        hashes.append(record_hash)

    return tuple(hashes)


def load_single_market_price(
    database_url: str,
    record: Mapping[str, Any],
    *,
    source: str,
    source_reference: str | None = None,
) -> str:
    """
    Load exactly one market-price record.
    """

    if not isinstance(record, Mapping):
        raise TypeError(
            "record must be a mapping."
        )

    normalized_source = str(source).strip()

    if not normalized_source:
        raise MarketDataLoadError(
            "source cannot be empty."
        )

    try:
        return ingest_market_price(
            database_url,
            record,
            source=normalized_source,
            source_reference=source_reference,
        )

    except (
        IngestionError,
        NormalizationError,
        TypeError,
        ValueError,
    ) as exc:
        raise MarketDataLoadError(
            f"Market-price ingestion failed: {exc}"
        ) from exc


class MarketDataLoader:
    """
    Compatibility wrapper around the market-data loading functions.

    The client is retained for future/provider-backed loading and does
    not alter the existing ingestion functions.
    """

    def __init__(self, client: Any | None = None) -> None:
        self.client = client

    def load(
        self,
        database_url: str,
        payload: Any,
        *,
        source: str,
        source_reference: str | None = None,
    ) -> tuple[str, ...]:
        return load_market_prices(
            database_url,
            payload,
            source=source,
            source_reference=source_reference,
        )

    def load_one(
        self,
        database_url: str,
        record: Mapping[str, Any],
        *,
        source: str,
        source_reference: str | None = None,
    ) -> str:
        return load_single_market_price(
            database_url,
            record,
            source=source,
            source_reference=source_reference,
        )
