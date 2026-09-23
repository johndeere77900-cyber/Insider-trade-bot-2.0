"""
SEC historical-data preparation and loading layer for Insider Trade Bot.

This module converts SEC submission data into controlled historical
ingestion requests.

It does not assume that every SEC submission is an insider transaction.
Only records that can be identified as Form 3, Form 4, or Form 5 filings
are prepared for the insider-transaction ingestion pipeline.

The module preserves the original SEC submission payload so that later
validation and audit work can trace normalized records back to source data.
"""

from __future__ import annotations

from typing import Any, Mapping

from data.ingestion_pipeline import (
    ingest_insider_transaction,
)
from data.historical_loader import (
    HistoricalLoadError,
    HistoricalLoadResult,
)
from data.normalization import (
    NormalizationError,
)
from storage.repository import utc_now


INSIDER_FORMS = {
    "3",
    "4",
    "5",
    "3/A",
    "4/A",
    "5/A",
}


def _text(
    value: Any,
) -> str | None:
    """
    Convert a value to stripped text.

    Empty values become None.
    """

    if value is None:
        return None

    result = str(
        value
    ).strip()

    if not result:
        return None

    return result


def _first_value(
    data: Mapping[str, Any],
    *keys: str,
) -> Any:
    """
    Return the first present, non-empty value from the supplied keys.

    Unlike a simple ``or`` chain, this preserves legitimate zero values.
    """

    for key in keys:
        if key not in data:
            continue

        value = data[key]

        if value is None:
            continue

        if isinstance(
            value,
            str,
        ) and not value.strip():
            continue

        return value

    return None


def _normalize_cik(
    value: Any,
) -> str:
    """
    Normalize a CIK into the SEC's ten-digit representation.
    """

    text = _text(value)

    if text is None:
        raise NormalizationError(
            "SEC CIK is required."
        )

    if not text.isdigit():
        raise NormalizationError(
            "SEC CIK must contain digits only."
        )

    return text.zfill(10)


def _extract_submission_rows(
    submissions: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """
    Extract the SEC recent-filing arrays from a submissions response.

    SEC submissions data normally contains a ``filings.recent`` object.
    The function returns one dictionary per filing.
    """

    filings = submissions.get(
        "filings"
    )

    if not isinstance(
        filings,
        Mapping,
    ):
        raise HistoricalLoadError(
            "SEC submissions response has no valid 'filings' object."
        )

    recent = filings.get(
        "recent"
    )

    if not isinstance(
        recent,
        Mapping,
    ):
        raise HistoricalLoadError(
            "SEC submissions response has no valid 'filings.recent' object."
        )

    if not recent:
        return []

    lengths = [
        len(value)
        for value in recent.values()
        if isinstance(value, list)
    ]

    if not lengths:
        return []

    row_count = max(
        lengths
    )

    rows: list[dict[str, Any]] = []

    for index in range(row_count):
        row: dict[str, Any] = {}

        for field, values in recent.items():
            if not isinstance(
                values,
                list,
            ):
                continue

            if index < len(values):
                row[field] = values[index]

        rows.append(row)

    return rows


def _is_insider_form(
    form_type: Any,
) -> bool:
    """
    Determine whether an SEC filing form is an insider Form 3, 4, or 5.
    """

    normalized = _text(
        form_type
    )

    if normalized is None:
        return False

    return normalized.upper() in {
        form.upper()
        for form in INSIDER_FORMS
    }


def prepare_submission_record(
    row: Mapping[str, Any],
    *,
    issuer_cik: str,
    issuer_name: str | None = None,
) -> dict[str, Any] | None:
    """
    Convert one SEC submissions row into an ingestion payload.

    Returns None for filings that are not Form 3, 4, or 5.
    """

    if not isinstance(
        row,
        Mapping,
    ):
        raise TypeError(
            "SEC submission row must be a mapping."
        )

    form_type = _first_value(
        row,
        "form",
        "form_type",
        "formType",
    )

    if not _is_insider_form(
        form_type
    ):
        return None

    accession_number = _first_value(
        row,
        "accessionNumber",
        "accession_number",
    )

    if accession_number is None:
        raise HistoricalLoadError(
            "SEC insider filing has no accession number."
        )

    accession = str(
        accession_number
    ).strip()

    if not accession:
        raise HistoricalLoadError(
            "SEC insider filing has an empty accession number."
        )

    normalized_issuer_cik = _normalize_cik(
        issuer_cik
    )

    filing_date = _first_value(
        row,
        "filingDate",
        "filing_date",
    )

    transaction_date = _first_value(
        row,
        "reportDate",
        "transactionDate",
        "transaction_date",
    )

    return {
        "source": "SEC",
        "accession_number": accession,
        "issuer_cik": normalized_issuer_cik,
        "issuer_name": _text(
            issuer_name
        ),
        "insider_name": _first_value(
            row,
            "reportingOwnerName",
            "insider_name",
            "insiderName",
        ),
        "insider_cik": _first_value(
            row,
            "reportingOwnerCik",
            "reportingOwnerCIK",
            "insider_cik",
            "insiderCik",
        ),
        "transaction_date": _text(
            transaction_date
        ),
        "filing_date": _text(
            filing_date
        ),
        "form_type": _text(
            form_type
        ),
        "transaction_code": _first_value(
            row,
            "transactionCode",
            "transaction_code",
        ),
        "shares": _first_value(
            row,
            "shares",
        ),
        "price": _first_value(
            row,
            "transactionPrice",
            "price",
            "transaction_price",
        ),
        "ownership_type": _first_value(
            row,
            "ownershipType",
            "ownership_type",
        ),
    }


def prepare_submissions(
    submissions: Mapping[str, Any],
    *,
    issuer_cik: str,
    issuer_name: str | None = None,
) -> list[dict[str, Any]]:
    """
    Extract and prepare all identifiable insider filings from an SEC
    submissions response.
    """

    rows = _extract_submission_rows(
        submissions
    )

    prepared: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        try:
            record = prepare_submission_record(
                row,
                issuer_cik=issuer_cik,
                issuer_name=issuer_name,
            )

        except (
            HistoricalLoadError,
            NormalizationError,
            TypeError,
        ) as exc:
            raise HistoricalLoadError(
                f"Failed to prepare SEC submission row "
                f"{index}: {exc}"
            ) from exc

        if record is not None:
            prepared.append(
                record
            )

    return prepared


def load_sec_submissions(
    database_url: str,
    submissions: Mapping[str, Any],
    *,
    issuer_cik: str,
    issuer_name: str | None = None,
) -> HistoricalLoadResult:
    """
    Prepare and ingest SEC insider filings from one submissions response.

    Every accepted record passes through the standard normalization,
    validation, storage, and provenance pipeline.

    No non-insider SEC filings are inserted.
    """

    prepared = prepare_submissions(
        submissions,
        issuer_cik=issuer_cik,
        issuer_name=issuer_name,
    )

    if not prepared:
        return HistoricalLoadResult(
            record_type="insider_transaction",
            source="SEC",
            attempted_count=0,
            accepted_count=0,
            record_hashes=(),
        )

    hashes: list[str] = []

    for index, payload in enumerate(
        prepared
    ):
        try:
            record_hash = ingest_insider_transaction(
                database_url,
                payload,
                source="SEC",
                source_reference=(
                    f"SEC submission:"
                    f"{payload['accession_number']}"
                ),
            )

        except Exception as exc:
            raise HistoricalLoadError(
                f"SEC historical ingestion failed at "
                f"prepared record {index}: {exc}"
            ) from exc

        hashes.append(
            record_hash
        )

    return HistoricalLoadResult(
        record_type="insider_transaction",
        source="SEC",
        attempted_count=len(prepared),
        accepted_count=len(hashes),
        record_hashes=tuple(
            hashes
        ),
)
