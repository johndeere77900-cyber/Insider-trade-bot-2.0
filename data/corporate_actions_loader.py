"""
Corporate-actions loading layer for Insider Trade Bot.

This module converts provider responses into normalized corporate-action
records and sends them through the standard validation, storage, and
provenance pipeline.

It does not bypass validation or write directly to the database.
"""

from __future__ import annotations

from typing import Any, Mapping

from data.ingestion_pipeline import (
    IngestionError,
    ingest_corporate_action,
)
from data.normalization import (
    NormalizationError,
)


class CorporateActionsLoadError(
    Exception
):
    """Raised when corporate-action loading fails."""


def _extract_records(
    payload: Any,
) -> list[Mapping[str, Any]]:
    """
    Extract a list of corporate-action records from a provider response.

    Supported response shapes:

        1. A direct list of records.
        2. A mapping containing a list under one of:
           data, results, actions, corporate_actions.
    """

    if isinstance(
        payload,
        list,
    ):
        records = payload

    elif isinstance(
        payload,
        Mapping,
    ):
        records = None

        for key in (
            "data",
            "results",
            "actions",
            "corporate_actions",
        ):
            candidate = payload.get(
                key
            )

            if isinstance(
                candidate,
                list,
            ):
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

    normalized: list[
        Mapping[str, Any]
    ] = []

    for index, record in enumerate(
        records
    ):
        if not isinstance(
            record,
            Mapping,
        ):
            raise CorporateActionsLoadError(
                f"Corporate-action record {index} "
                "is not an object."
            )

        normalized.append(
            record
        )

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

    Returns:
        Tuple containing the deterministic record hashes of accepted
        records.

    No record is silently substituted when normalization or validation
    fails.
    """

    normalized_source = str(
        source
    ).strip()

    if not normalized_source:
        raise CorporateActionsLoadError(
            "source cannot be empty."
        )

    records = _extract_records(
        payload
    )

    hashes: list[str] = []

    for index, record in enumerate(
        records
    ):
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

        hashes.append(
            record_hash
        )

    return tuple(
        hashes
    )


def load_single_corporate_action(
    database_url: str,
    record: Mapping[str, Any],
    *,
    source: str,
    source_reference: str | None = None,
) -> str:
    """
    Load exactly one corporate-action record.

    This function is useful when the upstream provider returns individual
    action records rather than a batch.
    """

    if not isinstance(
        record,
        Mapping,
    ):
        raise TypeError(
            "record must be a mapping."
        )

    normalized_source = str(
        source
    ).strip()

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
