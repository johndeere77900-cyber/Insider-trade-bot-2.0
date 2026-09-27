from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


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
    """
    Normalize one SEC historical filing record.

    The function accepts common SEC field-name variants without changing
    the original payload.
    """
    if not isinstance(record, Mapping):
        raise SECHistoricalLoaderError(
            "Historical SEC record must be a mapping."
        )

    accession_number = _text(
        _first(
            record,
            "accession_number",
            "accessionNumber",
            "accession",
        )
    )

    filing_date = _text(
        _first(
            record,
            "filing_date",
            "filingDate",
            "filed",
        )
    )

    form_type = _text(
        _first(
            record,
            "form_type",
            "formType",
            "form",
        )
    )

    issuer_cik = _text(
        _first(
            record,
            "issuer_cik",
            "issuerCik",
            "cik",
        )
    )

    issuer_name = _text(
        _first(
            record,
            "issuer_name",
            "issuerName",
            "company_name",
            "companyName",
        )
    )

    return SECHistoricalRecord(
        accession_number=accession_number,
        filing_date=filing_date,
        form_type=form_type,
        issuer_cik=issuer_cik,
        issuer_name=issuer_name,
        raw=dict(record),
    )


def load_historical_records(
    records: Iterable[Mapping[str, Any]],
) -> list[SECHistoricalRecord]:
    """
    Normalize a collection of SEC historical records.
    """
    if records is None:
        return []

    normalized: list[SECHistoricalRecord] = []

    for record in records:
        normalized.append(normalize_historical_record(record))

    return normalized


def load_historical_data(
    payload: Any,
) -> list[SECHistoricalRecord]:
    """
    Load historical SEC records from common payload shapes.

    Supported inputs:
      - a list/tuple of records
      - a mapping containing a list under common SEC keys
      - a single record mapping
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


class SECHistoricalLoader:
    """
    Compatibility/service wrapper for SEC historical data loading.

    This class intentionally keeps loading and normalization separate from
    network retrieval. A caller may supply already-retrieved SEC data.
    """

    def __init__(self, client: Any | None = None) -> None:
        self.client = client

    def load(
        self,
        payload: Any = None,
    ) -> list[SECHistoricalRecord]:
        """
        Normalize supplied SEC historical data.

        If no payload is supplied, a configured client is used when it
        exposes a compatible historical-loading method.
        """
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
            method = getattr(self.client, method_name, None)

            if callable(method):
                return load_historical_data(method())

        raise SECHistoricalLoaderError(
            "Configured SEC client does not provide a historical-data method."
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


# Backward-compatible function name.
def sec_historical_loader(
    payload: Any,
) -> list[SECHistoricalRecord]:
    return load_historical_data(payload)
