"""
Corporate-actions loading layer for Insider Trade Bot.

This module converts provider responses into normalized corporate-action
records and sends them through the standard validation, storage, and
provenance pipeline.

It does not bypass validation or write directly to the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from data.corporate_actions_client import CorporateActionsClient
from data.ingestion_pipeline import (
    IngestionError,
    ingest_corporate_action,
)
from data.normalization import (
    NormalizationError,
)


class CorporateActionsLoadError(Exception):
    """Raised when corporate-action loading fails."""


@dataclass(frozen=True)
class CorporateActionLoadOutcome:
    """Detailed load outcome for a single corporate-action record."""

    index: int
    symbol: str | None
    action_type: str | None
    action_date: str | None
    outcome: str  # 'INSERTED', 'DUPLICATE', 'CONFLICT', 'REJECTED', 'FAILED'
    record_hash: str | None = None
    reason: str | None = None


def _extract_records(
    payload: Any,
) -> list[Mapping[str, Any]]:
    """
    Extract a list of corporate-action records from a provider response.
    """

    if isinstance(payload, list):
        records = payload

    elif isinstance(payload, Mapping):
        records = None

        for key in (
            "data",
            "results",
            "actions",
            "corporate_actions",
        ):
            candidate = payload.get(key)

            if isinstance(candidate, list):
                records = candidate
                break

        if records is None:
            raise CorporateActionsLoadError(
                "Corporate-actions response does not contain "
                "a supported record list."
            )

    else:
        raise CorporateActionsLoadError(
            "Corporate-actions response must be a list or mapping."
        )

    normalized: list[Mapping[str, Any]] = []

    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise CorporateActionsLoadError(
                f"Corporate-action record {index} is not an object."
            )

        normalized.append(record)

    return normalized


def load_corporate_actions_detailed(
    database_url: str,
    payload: Any,
    *,
    source: str,
    source_reference: str | None = None,
) -> tuple[CorporateActionLoadOutcome, ...]:
    """
    Normalize, validate, store, and provenance-track corporate actions with detailed record outcomes.

    Returns:
        Tuple of CorporateActionLoadOutcome for every element in payload.
    """
    normalized_source = str(source).strip()
    if not normalized_source:
        raise CorporateActionsLoadError("source cannot be empty.")

    raw_records = _extract_records(payload)
    outcomes: list[CorporateActionLoadOutcome] = []

    for index, record in enumerate(raw_records):
        if not isinstance(record, Mapping):
            outcomes.append(
                CorporateActionLoadOutcome(
                    index=index,
                    symbol=None,
                    action_type=None,
                    action_date=None,
                    outcome="REJECTED",
                    reason="Record is not an object/mapping.",
                )
            )
            continue

        sym_str = str(record.get("symbol") or record.get("ticker")).strip().upper() if record.get("symbol") or record.get("ticker") else None
        act_type = str(record.get("action_type") or record.get("type")).strip().lower() if record.get("action_type") or record.get("type") else None
        act_date = str(record.get("action_date") or record.get("date")).strip() if record.get("action_date") or record.get("date") else None

        try:
            record_hash, outcome_status = ingest_corporate_action(
                database_url,
                record,
                source=normalized_source,
                source_reference=source_reference,
            )
            outcomes.append(
                CorporateActionLoadOutcome(
                    index=index,
                    symbol=sym_str,
                    action_type=act_type,
                    action_date=act_date,
                    outcome=outcome_status,
                    record_hash=record_hash,
                )
            )
        except (IngestionError, NormalizationError, TypeError, ValueError) as exc:
            outcomes.append(
                CorporateActionLoadOutcome(
                    index=index,
                    symbol=sym_str,
                    action_type=act_type,
                    action_date=act_date,
                    outcome="REJECTED",
                    reason=str(exc),
                )
            )
        except Exception as exc:
            outcomes.append(
                CorporateActionLoadOutcome(
                    index=index,
                    symbol=sym_str,
                    action_type=act_type,
                    action_date=act_date,
                    outcome="FAILED",
                    reason=f"Storage error: {exc}",
                )
            )

    return tuple(outcomes)


def load_corporate_actions(
    database_url: str,
    payload: Any,
    *,
    source: str,
    source_reference: str | None = None,
) -> tuple[str, ...]:
    """
    Normalize, validate, store, and provenance-track corporate actions.
    Compatibility wrapper returning record hashes for accepted (INSERTED or DUPLICATE) records.
    """

    outcomes = load_corporate_actions_detailed(
        database_url,
        payload,
        source=source,
        source_reference=source_reference,
    )

    hashes: list[str] = []

    for outcome in outcomes:
        if outcome.outcome in ("REJECTED", "FAILED"):
            raise CorporateActionsLoadError(
                f"Corporate-action ingestion failed at record {outcome.index}: {outcome.reason}"
            )
        if outcome.record_hash and outcome.outcome in ("INSERTED", "DUPLICATE"):
            hashes.append(outcome.record_hash)

    return tuple(hashes)


def load_single_corporate_action(
    database_url: str,
    record: Mapping[str, Any],
    *,
    source: str,
    source_reference: str | None = None,
) -> str:
    """Load exactly one corporate-action record."""

    if not isinstance(record, Mapping):
        raise TypeError("record must be a mapping.")

    normalized_source = str(source).strip()

    if not normalized_source:
        raise CorporateActionsLoadError(
            "source cannot be empty."
        )

    try:
        record_hash, outcome = ingest_corporate_action(
            database_url,
            record,
            source=normalized_source,
            source_reference=source_reference,
        )
        return record_hash

    except (
        IngestionError,
        NormalizationError,
        TypeError,
        ValueError,
    ) as exc:
        raise CorporateActionsLoadError(
            f"Corporate-action ingestion failed: {exc}"
        ) from exc


class CorporateActionsLoader:
    """
    Compatibility loader around CorporateActionsClient.
    """

    def __init__(
        self,
        client: CorporateActionsClient | None = None,
    ) -> None:
        self.client = client

    def fetch(
        self,
        *,
        symbol: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> object:
        if self.client is None:
            raise CorporateActionsLoadError(
                "Corporate-actions client is not configured."
            )

        return self.client.get_actions(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

    def load_detailed(
        self,
        database_url: str,
        payload: Any,
        *,
        source: str,
        source_reference: str | None = None,
    ) -> tuple[CorporateActionLoadOutcome, ...]:
        return load_corporate_actions_detailed(
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
        return load_corporate_actions(
            database_url,
            payload,
            source=source,
            source_reference=source_reference,
        )
