from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from data.historical_loader import load_historical_insider_transactions


class SECHistoricalLoaderError(Exception):
    """Raised when SEC historical data cannot be loaded or normalized."""


@dataclass(frozen=True)
class SECHistoricalRecord:
    """Normalized representation of one SEC historical filing record."""

    accession_number: str | None
    filing_date: str | None
    form_type: str | None
    issuer_cik: str | None
    issuer_name: str | None
    raw: Mapping[str, Any]


def _text(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _first(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def normalize_historical_record(
    record: Mapping[str, Any],
) -> SECHistoricalRecord:
    """Normalize one SEC historical filing record."""

    if not isinstance(record, Mapping):
        raise SECHistoricalLoaderError(
            "Historical SEC record must be a mapping."
        )

    return SECHistoricalRecord(
        accession_number=_text(
            _first(
                record,
                "accession_number",
                "accessionNumber",
                "accession",
            )
        ),
        filing_date=_text(
            _first(
                record,
                "filing_date",
                "filingDate",
                "filed",
            )
        ),
        form_type=_text(
            _first(
                record,
                "form_type",
                "formType",
                "form",
            )
        ),
        issuer_cik=_text(
            _first(
                record,
                "issuer_cik",
                "issuerCik",
                "cik",
            )
        ),
        issuer_name=_text(
            _first(
                record,
                "issuer_name",
                "issuerName",
                "company_name",
                "companyName",
            )
        ),
        raw=dict(record),
    )


def load_historical_records(
    records: Iterable[Mapping[str, Any]],
) -> list[SECHistoricalRecord]:
    """Normalize a collection of SEC historical records."""

    if records is None:
        return []

    return [
        normalize_historical_record(record)
        for record in records
    ]


def load_historical_data(
    payload: Any,
) -> list[SECHistoricalRecord]:
    """
    Load historical SEC records from common payload shapes.
    """

    if payload is None:
        return []

    if isinstance(payload, (list, tuple)):
        return load_historical_records(payload)

    if isinstance(payload, Mapping):
        for key in (
            "filings",
            "records",
            "data",
            "results",
            "recent",
        ):
            value = payload.get(key)

            if isinstance(value, (list, tuple)):
                return load_historical_records(value)

        return [normalize_historical_record(payload)]

    raise SECHistoricalLoaderError(
        "Unsupported SEC historical data payload."
    )


def _extract_recent_rows(
    submissions: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """
    Convert the SEC submissions `filings.recent` column-oriented
    structure into row-oriented dictionaries.
    """

    filings = submissions.get("filings")

    if not isinstance(filings, Mapping):
        return []

    recent = filings.get("recent")

    if not isinstance(recent, Mapping):
        return []

    columns: dict[str, list[Any]] = {}

    for key, value in recent.items():
        if isinstance(value, list):
            columns[str(key)] = value

    if not columns:
        return []

    row_count = max(
        (len(values) for values in columns.values()),
        default=0,
    )

    rows: list[dict[str, Any]] = []

    for index in range(row_count):
        row: dict[str, Any] = {}

        for key, values in columns.items():
            row[key] = values[index] if index < len(values) else None

        rows.append(row)

    return rows


def _prepare_submission_records(
    submissions: Mapping[str, Any],
    *,
    issuer_cik: str,
    issuer_name: str,
) -> list[dict[str, Any]]:
    """
    Prepare SEC submission rows for the existing historical ingestion
    pipeline.

    This function does not invent insider transaction fields. It only
    maps SEC submission metadata that is actually present.
    """

    rows = _extract_recent_rows(submissions)

    prepared: list[dict[str, Any]] = []

    for row in rows:
        record = dict(row)

        record.setdefault(
            "issuer_cik",
            issuer_cik,
        )

        record.setdefault(
            "issuer_name",
            issuer_name,
        )

        accession_number = _first(
            record,
            "accessionNumber",
            "accession_number",
            "accession",
        )

        if accession_number is not None:
            record.setdefault(
                "accession_number",
                accession_number,
            )

        filing_date = _first(
            record,
            "filingDate",
            "filing_date",
            "filed",
        )

        if filing_date is not None:
            record.setdefault(
                "filing_date",
                filing_date,
            )

        form_type = _first(
            record,
            "form",
            "formType",
            "form_type",
        )

        if form_type is not None:
            record.setdefault(
                "form_type",
                form_type,
            )

        prepared.append(record)

    return prepared


def load_sec_submissions(
    database_url: str,
    submissions: Mapping[str, Any],
    *,
    issuer_cik: str,
    issuer_name: str,
):
    """
    Load SEC submissions through the existing controlled historical
    ingestion pipeline.

    The orchestrator depends on this function as the bridge between
    SEC submissions retrieval and historical ingestion.
    """

    if not isinstance(submissions, Mapping):
        raise SECHistoricalLoaderError(
            "SEC submissions must be a mapping."
        )

    normalized_cik = _text(issuer_cik)

    if not normalized_cik:
        raise SECHistoricalLoaderError(
            "issuer_cik cannot be empty."
        )

    normalized_name = _text(issuer_name) or ""

    records = _prepare_submission_records(
        submissions,
        issuer_cik=normalized_cik,
        issuer_name=normalized_name,
    )

    if not records:
        return load_historical_insider_transactions(
            database_url,
            [],
            source="SEC",
        )

    return load_historical_insider_transactions(
        database_url,
        records,
        source="SEC",
    )


class SECHistoricalLoader:
    """
    Compatibility/service wrapper for SEC historical data loading.
    """

    def __init__(self, client: Any | None = None) -> None:
        self.client = client

    def load(
        self,
        payload: Any = None,
    ) -> list[SECHistoricalRecord]:
        if payload is not None:
            return load_historical_data(payload)

        if self.client is None:
            return []

        for method_name in (
            "get_historical_data",
            "get_historical_filings",
            "fetch_historical_data",
            "fetch_historical_filings",
        ):
            method = getattr(
                self.client,
                method_name,
                None,
            )

            if callable(method):
                return load_historical_data(
                    method()
                )

        raise SECHistoricalLoaderError(
            "Configured SEC client does not provide a "
            "historical-data method."
        )

    def load_records(
        self,
        records: Iterable[Mapping[str, Any]],
    ) -> list[SECHistoricalRecord]:
        return load_historical_records(records)

    def normalize(
        self,
        record: Mapping[str, Any],
    ) -> SECHistoricalRecord:
        return normalize_historical_record(record)


def sec_historical_loader(
    payload: Any,
) -> list[SECHistoricalRecord]:
    """Backward-compatible historical loader function."""

    return load_historical_data(payload)
