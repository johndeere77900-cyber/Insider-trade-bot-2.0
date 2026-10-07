"""
Controlled ingestion pipeline for Insider Trade Bot.

This module connects retrieval, normalization, validation, hashing,
permanent storage, and provenance tracking.

The pipeline deliberately keeps these responsibilities separate:

    retrieve
        -> normalize
        -> validate
        -> hash/store
        -> provenance

Successful retrieval alone never means that a record is accepted.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable, Mapping

from core.hashing import generate_market_price_hash, sha256_record
from core.models import (
    CorporateAction,
    InsiderTransaction,
    MarketPrice,
)
from data.normalization import (
    NormalizationError,
    normalize_corporate_action,
    normalize_insider_transaction,
    normalize_market_price,
)
from storage.repository import (
    store_corporate_action,
    store_insider_transaction,
    store_market_price,
    store_provenance,
)
from validation.records import (
    validate_corporate_action,
    validate_insider_transaction,
    validate_market_price,
)


class IngestionError(Exception):
    """Base exception for ingestion-pipeline failures."""


class RecordRejectedError(
    IngestionError
):
    """Raised when a normalized record fails validation."""


def _validation_failure(
    errors: list[str],
) -> RecordRejectedError:
    """
    Build a consistent validation-rejection exception.
    """

    return RecordRejectedError(
        "Record failed validation: "
        + "; ".join(errors)
    )


def ingest_insider_transaction(
    database_url: str,
    payload: Mapping[str, Any],
    *,
    source: str,
    source_reference: str | None = None,
) -> str:
    """
    Normalize, validate, store, and provenance-track one insider record.

    Returns:
        Deterministic record hash.
    """

    try:
        record = normalize_insider_transaction(
            payload,
            source=source,
        )
    except (
        NormalizationError,
        TypeError,
        ValueError,
    ) as exc:
        raise IngestionError(
            f"Insider transaction normalization failed: {exc}"
        ) from exc

    errors = validate_insider_transaction(
        record
    )

    if errors:
        raise _validation_failure(
            errors
        )

    raw_payload = dict(payload)

    record_hash = store_insider_transaction(
        database_url,
        source=record.source,
        accession_number=record.accession_number,
        issuer_cik=record.issuer_cik,
        issuer_name=record.issuer_name,
        insider_name=record.insider_name,
        insider_cik=record.insider_cik,
        transaction_date=record.transaction_date,
        filing_date=record.filing_date,
        form_type=record.form_type,
        transaction_code=record.transaction_code,
        shares=record.shares,
        price=record.price,
        ownership_type=record.ownership_type,
        raw_payload=raw_payload,
    )

    store_provenance(
        database_url,
        record_type="insider_transaction",
        record_id=record_hash,
        source=record.source,
        source_reference=source_reference,
        checksum=record_hash,
        validation_status="validated",
    )

    return record_hash


def ingest_market_price(
    database_url: str,
    payload: Mapping[str, Any],
    *,
    source: str,
    source_reference: str | None = None,
) -> str:
    """
    Normalize, validate, store, and provenance-track one market-price
    record.

    Returns:
        Deterministic record hash.
    """

    try:
        record = normalize_market_price(
            payload,
            source=source,
        )
    except (
        NormalizationError,
        TypeError,
        ValueError,
    ) as exc:
        raise IngestionError(
            f"Market-price normalization failed: {exc}"
        ) from exc

    errors = validate_market_price(
        record
    )

    if errors:
        raise _validation_failure(
            errors
        )

    raw_payload = dict(payload)

    record_hash, _outcome = store_market_price(
        database_url,
        symbol=record.symbol,
        price_date=record.price_date,
        open_price=record.open,
        high=record.high,
        low=record.low,
        close=record.close,
        adjusted_close=record.adjusted_close,
        volume=record.volume,
        source=record.source,
        raw_payload=raw_payload,
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

    return record_hash


def ingest_corporate_action(
    database_url: str,
    payload: Mapping[str, Any],
    *,
    source: str,
    source_reference: str | None = None,
) -> tuple[str, str]:
    """
    Normalize, validate, store, and provenance-track one corporate action.

    Returns:
        Tuple of (record_hash, outcome), where outcome is 'INSERTED', 'DUPLICATE', or 'CONFLICT'.
    """

    try:
        record = normalize_corporate_action(
            payload,
            source=source,
        )
    except (
        NormalizationError,
        TypeError,
        ValueError,
    ) as exc:
        raise IngestionError(
            f"Corporate-action normalization failed: {exc}"
        ) from exc

    errors = validate_corporate_action(
        record
    )

    if errors:
        raise _validation_failure(
            errors
        )

    raw_payload = dict(payload)

    record_hash, outcome = store_corporate_action(
        database_url,
        symbol=record.symbol,
        action_type=record.action_type,
        action_date=record.action_date,
        ratio=record.ratio,
        cash_amount=record.cash_amount,
        source=record.source,
        raw_payload=raw_payload,
    )

    # Store provenance for accepted and duplicate records (avoiding provenance on conflicts)
    if outcome in ("INSERTED", "DUPLICATE"):
        store_provenance(
            database_url,
            record_type="corporate_action",
            record_id=record_hash,
            source=record.source,
            source_reference=source_reference,
            checksum=record_hash,
            validation_status="validated",
        )

    return record_hash, outcome


def calculate_normalized_record_hash(
    record: (
        InsiderTransaction
        | MarketPrice
        | CorporateAction
    ),
) -> str:
    """
    Calculate a deterministic hash from a normalized domain record.

    This helper does not write anything to the database.
    """

    if isinstance(record, MarketPrice):
        return generate_market_price_hash(
            symbol=record.symbol,
            price_date=record.price_date,
            source=record.source,
            open_price=record.open,
            high=record.high,
            low=record.low,
            close=record.close,
            adjusted_close=record.adjusted_close,
            volume=record.volume,
        )

    if not isinstance(
        record,
        (
            InsiderTransaction,
            CorporateAction,
        ),
    ):
        raise TypeError(
            "Unsupported normalized record type."
        )

    return sha256_record(
        asdict(record)
    )


def ingest_batch(
    database_url: str,
    records: Iterable[Mapping[str, Any]],
    *,
    record_type: str,
    source: str,
) -> list[str]:
    """
    Ingest a homogeneous collection of records.

    Processing is performed sequentially so that a failure identifies the
    specific record that could not be accepted.

    Supported record types:

        insider_transaction
        market_price
        corporate_action
    """

    normalized_type = str(
        record_type
    ).strip().lower()

    if normalized_type not in {
        "insider_transaction",
        "market_price",
        "corporate_action",
    }:
        raise ValueError(
            "Unsupported record_type."
        )

    hashes: list[str] = []

    for index, payload in enumerate(records):
        try:
            if normalized_type == "insider_transaction":
                record_hash = ingest_insider_transaction(
                    database_url,
                    payload,
                    source=source,
                )

            elif normalized_type == "market_price":
                record_hash = ingest_market_price(
                    database_url,
                    payload,
                    source=source,
                )

            else:
                res = ingest_corporate_action(
                    database_url,
                    payload,
                    source=source,
                )
                record_hash = res[0]

        except IngestionError as exc:
            raise IngestionError(
                f"Batch ingestion failed at record "
                f"{index}: {exc}"
            ) from exc

        hashes.append(
            record_hash
        )

    return hashes
