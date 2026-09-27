"""
Corporate-actions loading layer for Insider Trade Bot.

This module converts provider responses into normalized corporate-action
records and sends them through the standard validation, storage, and
provenance pipeline.

It does not bypass validation or write directly to the database.
"""

from __future__ import annotations

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


def load_corporate_actions(
    database_url: str,
    payload: Any,
    *,
    source: str,
    source_reference: str | None = None,
) -> tuple[str, ...]:
    """
    Normalize, validate, store, and provenance-track corporate actions.
    """

    normalized_source = str(source).strip()

    if not normalized_source:
        raise CorporateActionsLoadError(
            "source cannot be empty."
        )

    records = _extract_records(payload)

    hashes: list[str] = []

    for index, record in enumerate(records):
        try:
            record_hash = ingest_corporate_action(
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
            raise CorporateActionsLoadError(
                "Corporate-action ingestion failed at "
                f"record {index}: {exc}"
            ) from exc

        hashes.append(record_hash)

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
        return ingest_corporate_action(
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
        raise CorporateActionsLoadError(
            f"Corporate-action ingestion failed: {exc}"
        ) from exc


class CorporateActionsLoader:
    """
    Compatibility loader around CorporateActionsClient.

    The current test/application layer requires a constructible loader
    that can receive a configured client.
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
        """
        Retrieve corporate actions through the configured client.

        A client must be configured before fetching.
        """

        if self.client is None:
            raise CorporateActionsLoadError(
                "Corporate-actions client is not configured."
            )

        return self.client.get_actions(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

    def load(
        self,
        database_url: str,
        payload: Any,
        *,
        source: str,
        source_reference: str | None = None,
    ) -> tuple[str, ...]:
        """Load provider data through the existing ingestion pipeline."""

        return load_corporate_actions(
            database_url,
            payload,
            source=source,
            source_reference=source_reference,
        )
