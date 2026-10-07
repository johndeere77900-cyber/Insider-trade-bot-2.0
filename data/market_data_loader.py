"""
Market-data loading layer for Insider Trade Bot.

This module converts provider responses into normalized market-price
records and sends them through the standard validation, storage, and
provenance pipeline.

It processes payloads record-by-record to produce deterministic outcomes:
- INSERTED
- DUPLICATE
- REJECTED
- CONFLICT
- FAILED
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from data.normalization import (
    NormalizationError,
    normalize_market_price,
)
from storage.repository import (
    MarketDataConflictError,
    store_market_price,
    store_provenance,
)
from validation.records import validate_market_price


class MarketDataLoadError(Exception):
    """Raised when market-data loading fails abruptly due to response envelope errors."""


@dataclass(frozen=True)
class RecordLoadOutcome:
    """Detailed load outcome for a single market-price record."""

    index: int
    symbol: str | None
    price_date: str | None
    outcome: str  # 'INSERTED', 'DUPLICATE', 'REJECTED', 'CONFLICT', 'FAILED'
    record_hash: str | None = None
    reason: str | None = None


def _extract_records(
    payload: Any,
) -> list[Any]:
    """
    Extract market-price record elements from a provider response envelope.

    Supported response shapes:

        1. A direct list of records.
        2. A mapping containing a list under:
           data, results, prices, historical, or records.

    Only invalid response envelopes raise MarketDataLoadError.
    Individual element typing (e.g. non-Mapping) is deferred to record-level processing.
    """

    if isinstance(payload, list):
        return payload

    if isinstance(payload, Mapping):
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

        return records

    raise MarketDataLoadError(
        "Market-data response must be a list or mapping."
    )


def load_market_prices_detailed(
    database_url: str,
    payload: Any,
    *,
    source: str,
    source_reference: str | None = None,
) -> tuple[RecordLoadOutcome, ...]:
    """
    Normalize, validate, store, and provenance-track market-price records record-by-record.

    Returns:
        Tuple of RecordLoadOutcome for every record element in the response payload.
    """

    normalized_source = str(source).strip()

    if not normalized_source:
        raise MarketDataLoadError(
            "source cannot be empty."
        )

    raw_records = _extract_records(payload)
    outcomes: list[RecordLoadOutcome] = []

    for index, raw_record in enumerate(raw_records):
        if not isinstance(raw_record, Mapping):
            outcomes.append(
                RecordLoadOutcome(
                    index=index,
                    symbol=None,
                    price_date=None,
                    outcome="REJECTED",
                    reason="Record is not an object/mapping.",
                )
            )
            continue

        # Extract potential symbol/date for diagnostic reporting before full normalization
        candidate_symbol = raw_record.get("symbol") or raw_record.get("ticker")
        sym_str = str(candidate_symbol).strip().upper() if candidate_symbol else None
        candidate_date = raw_record.get("price_date") or raw_record.get("date")
        date_str = str(candidate_date).strip() if candidate_date else None

        # 1. Normalization
        try:
            record = normalize_market_price(
                raw_record,
                source=normalized_source,
            )
        except (NormalizationError, TypeError, ValueError) as exc:
            outcomes.append(
                RecordLoadOutcome(
                    index=index,
                    symbol=sym_str,
                    price_date=date_str,
                    outcome="REJECTED",
                    reason=f"Normalization failed: {exc}",
                )
            )
            continue

        symbol = record.symbol
        price_date = record.price_date

        # 2. Validation
        validation_errors = validate_market_price(record)
        if validation_errors:
            outcomes.append(
                RecordLoadOutcome(
                    index=index,
                    symbol=symbol,
                    price_date=price_date,
                    outcome="REJECTED",
                    reason="Validation failed: " + "; ".join(validation_errors),
                )
            )
            continue

        # 3. Storage and conflict check
        try:
            record_hash, outcome_status = store_market_price(
                database_url,
                symbol=symbol,
                price_date=price_date,
                open_price=record.open,
                high=record.high,
                low=record.low,
                close=record.close,
                adjusted_close=record.adjusted_close,
                volume=record.volume,
                source=record.source,
                raw_payload=dict(raw_record),
            )

            store_provenance(
                database_url,
                record_type="market_price",
                record_id=record_hash,
                source=record.source,
                source_reference=source_reference,
                checksum=record_hash,
                validation_status="validated",
            )

            outcomes.append(
                RecordLoadOutcome(
                    index=index,
                    symbol=symbol,
                    price_date=price_date,
                    outcome=outcome_status,  # 'INSERTED' or 'DUPLICATE'
                    record_hash=record_hash,
                )
            )

        except MarketDataConflictError as exc:
            outcomes.append(
                RecordLoadOutcome(
                    index=index,
                    symbol=symbol,
                    price_date=price_date,
                    outcome="CONFLICT",
                    reason=str(exc),
                )
            )
        except Exception as exc:
            outcomes.append(
                RecordLoadOutcome(
                    index=index,
                    symbol=symbol,
                    price_date=price_date,
                    outcome="FAILED",
                    reason=f"Storage error: {exc}",
                )
            )

    return tuple(outcomes)


def load_market_prices(
    database_url: str,
    payload: Any,
    *,
    source: str,
    source_reference: str | None = None,
) -> tuple[str, ...]:
    """
    Compatibility wrapper returning deterministic record hashes for valid records,
    raising MarketDataLoadError if any record fails.
    """

    outcomes = load_market_prices_detailed(
        database_url,
        payload,
        source=source,
        source_reference=source_reference,
    )

    hashes: list[str] = []

    for outcome in outcomes:
        if outcome.outcome in {"REJECTED", "CONFLICT", "FAILED"}:
            raise MarketDataLoadError(
                f"Market-price ingestion failed at record {outcome.index}: {outcome.reason}"
            )
        if outcome.record_hash:
            hashes.append(outcome.record_hash)

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

    outcomes = load_market_prices_detailed(
        database_url,
        [record],
        source=source,
        source_reference=source_reference,
    )

    if not outcomes:
        raise MarketDataLoadError("Empty record payload.")

    outcome = outcomes[0]

    if outcome.outcome in {"REJECTED", "CONFLICT", "FAILED"}:
        raise MarketDataLoadError(
            f"Market-price ingestion failed: {outcome.reason}"
        )

    if not outcome.record_hash:
        raise MarketDataLoadError("Record hash missing.")

    return outcome.record_hash


class MarketDataLoader:
    """
    Compatibility wrapper around the market-data loading functions.
    """

    def __init__(self, client: Any | None = None) -> None:
        self.client = client

    def load_detailed(
        self,
        database_url: str,
        payload: Any,
        *,
        source: str,
        source_reference: str | None = None,
    ) -> tuple[RecordLoadOutcome, ...]:
        return load_market_prices_detailed(
            database_url,
            payload,
            source=source,
            source_reference=source_reference,
        )

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
