"""
Data normalization layer for Insider Trade Bot.

Normalization converts external records into stable internal representations.
Compatibility helpers return dictionaries for lightweight callers/tests,
while the existing model-based functions remain available for ingestion.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from core.models import (
    CorporateAction,
    InsiderTransaction,
    MarketPrice,
)


class NormalizationError(Exception):
    """Raised when external data cannot be normalized safely."""


def _text(value: Any) -> str | None:
    if value is None:
        return None

    result = str(value).strip()

    return result or None


def _required_text(
    value: Any,
    field_name: str,
) -> str:
    result = _text(value)

    if result is None:
        raise NormalizationError(
            f"{field_name} is required."
        )

    return result


def _number(
    value: Any,
    field_name: str,
) -> float | None:
    if value is None:
        return None

    if isinstance(value, bool):
        raise NormalizationError(
            f"{field_name} must be numeric."
        )

    if isinstance(value, (int, float)):
        result = float(value)
    else:
        text_value = str(value).strip()

        if not text_value:
            return None

        text_value = text_value.replace(
            ",",
            "",
        )

        try:
            result = float(
                text_value
            )
        except ValueError as exc:
            raise NormalizationError(
                f"{field_name} must be numeric."
            ) from exc

    if not math.isfinite(result):
        raise NormalizationError(
            f"{field_name} must be finite."
        )

    return result


def _mapping(
    value: Any,
    field_name: str,
) -> Mapping[str, Any]:
    if not isinstance(
        value,
        Mapping,
    ):
        raise NormalizationError(
            f"{field_name} must be an object or mapping."
        )

    return value


def _first_present(
    data: Mapping[str, Any],
    *keys: str,
) -> Any:
    """
    Return the first value whose key actually exists.

    Unlike `a or b`, this preserves legitimate zero values.
    """

    for key in keys:
        if (
            key in data
            and data[key] is not None
        ):
            return data[key]

    return None


def normalize_insider_transaction(
    payload: Mapping[str, Any],
    *,
    source: str,
) -> InsiderTransaction:
    data = _mapping(
        payload,
        "payload",
    )

    normalized_source = _required_text(
        source,
        "source",
    )

    accession_number = _required_text(
        _first_present(
            data,
            "accession_number",
            "accessionNumber",
            "accession",
        ),
        "accession_number",
    )

    issuer_cik = _required_text(
        _first_present(
            data,
            "issuer_cik",
            "issuerCik",
            "cik",
        ),
        "issuer_cik",
    )

    return InsiderTransaction(
        source=normalized_source,
        accession_number=accession_number,
        issuer_cik=issuer_cik,
        issuer_name=_text(
            _first_present(
                data,
                "issuer_name",
                "issuerName",
                "issuer",
            )
        ),
        insider_name=_text(
            _first_present(
                data,
                "insider_name",
                "insiderName",
                "reporting_owner_name",
                "insider",
            )
        ),
        insider_cik=_text(
            _first_present(
                data,
                "insider_cik",
                "insiderCik",
                "reporting_owner_cik",
            )
        ),
        transaction_date=_text(
            _first_present(
                data,
                "transaction_date",
                "transactionDate",
                "transaction_date_formatted",
            )
        ),
        filing_date=_text(
            _first_present(
                data,
                "filing_date",
                "filingDate",
            )
        ),
        form_type=_text(
            _first_present(
                data,
                "form_type",
                "formType",
                "form",
            )
        ),
        transaction_code=_text(
            _first_present(
                data,
                "transaction_code",
                "transactionCode",
                "code",
                "transaction_type",
            )
        ),
        shares=_number(
            _first_present(
                data,
                "shares",
            ),
            "shares",
        ),
        price=_number(
            _first_present(
                data,
                "price",
                "transaction_price",
            ),
            "price",
        ),
        ownership_type=_text(
            _first_present(
                data,
                "ownership_type",
                "ownershipType",
            )
        ),
    )


def normalize_market_price(
    payload: Mapping[str, Any],
    *,
    source: str | None = None,
) -> MarketPrice | dict[str, Any]:
    """
    Normalize a market-price record.

    When source is explicitly supplied, the normal domain-model
    MarketPrice representation is returned.

    When source is omitted, the source is read from the input record and
    a compatibility dictionary is returned for lightweight callers.
    """

    data = _mapping(
        payload,
        "payload",
    )

    source_was_explicit = source is not None

    if source is None:
        source = _first_present(
            data,
            "source",
        )

    normalized_source = _required_text(
        source,
        "source",
    )

    symbol = _required_text(
        _first_present(
            data,
            "symbol",
            "ticker",
        ),
        "symbol",
    )

    price_date = _required_text(
        _first_present(
            data,
            "price_date",
            "priceDate",
            "date",
        ),
        "price_date",
    )

    open_price = _number(
        _first_present(
            data,
            "open",
            "open_price",
        ),
        "open",
    )

    high_price = _number(
        _first_present(
            data,
            "high",
            "high_price",
        ),
        "high",
    )

    low_price = _number(
        _first_present(
            data,
            "low",
            "low_price",
        ),
        "low",
    )

    close_price = _number(
        _first_present(
            data,
            "close",
            "close_price",
        ),
        "close",
    )

    adjusted_close = _number(
        _first_present(
            data,
            "adjusted_close",
            "adjustedClose",
            "adj_close",
        ),
        "adjusted_close",
    )

    volume = _number(
        _first_present(
            data,
            "volume",
        ),
        "volume",
    )

    if not source_was_explicit:
        return {
            "symbol": symbol.upper(),
            "price_date": price_date,
            "open_price": open_price,
            "high_price": high_price,
            "low_price": low_price,
            "close_price": close_price,
            "adjusted_close": adjusted_close,
            "volume": volume,
            "source": normalized_source,
        }

    return MarketPrice(
        symbol=symbol.upper(),
        price_date=price_date,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        adjusted_close=adjusted_close,
        volume=volume,
        source=normalized_source,
    )


def normalize_corporate_action(
    payload: Mapping[str, Any],
    *,
    source: str,
) -> CorporateAction:
    data = _mapping(
        payload,
        "payload",
    )

    normalized_source = _required_text(
        source,
        "source",
    )

    symbol = _required_text(
        _first_present(
            data,
            "symbol",
            "ticker",
        ),
        "symbol",
    )

    action_type = _required_text(
        _first_present(
            data,
            "action_type",
            "actionType",
            "type",
        ),
        "action_type",
    )

    action_date = _required_text(
        _first_present(
            data,
            "action_date",
            "actionDate",
            "date",
        ),
        "action_date",
    )

    return CorporateAction(
        symbol=symbol.upper(),
        action_type=action_type,
        action_date=action_date,
        ratio=_text(
            _first_present(
                data,
                "ratio",
            )
        ),
        cash_amount=_number(
            _first_present(
                data,
                "cash_amount",
                "cashAmount",
                "amount",
            ),
            "cash_amount",
        ),
        source=normalized_source,
    )


def normalize_insider_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Compatibility normalizer used by lightweight callers.

    Returns a plain dictionary rather than a domain dataclass.
    """

    data = _mapping(
        record,
        "record",
    )

    symbol = _required_text(
        _first_present(
            data,
            "symbol",
            "ticker",
        ),
        "symbol",
    )

    insider_name = _text(
        _first_present(
            data,
            "insider_name",
            "insiderName",
            "insider",
            "reporting_owner_name",
        )
    )

    transaction_date = _text(
        _first_present(
            data,
            "transaction_date",
            "transactionDate",
        )
    )

    transaction_type = _text(
        _first_present(
            data,
            "transaction_type",
            "transactionType",
            "transaction_code",
            "transactionCode",
        )
    )

    shares = _number(
        _first_present(
            data,
            "shares",
        ),
        "shares",
    )

    price = _number(
        _first_present(
            data,
            "price",
            "transaction_price",
        ),
        "price",
    )

    source = _required_text(
        _first_present(
            data,
            "source",
        ),
        "source",
    )

    accession_number = _text(
        _first_present(
            data,
            "accession_number",
            "accessionNumber",
            "accession",
        )
    )

    return {
        "symbol": symbol.upper(),
        "insider_name": insider_name,
        "transaction_date": transaction_date,
        "transaction_type": transaction_type,
        "shares": shares,
        "price": price,
        "source": source,
        "accession_number": accession_number,
    }


def normalize_market_price_record(
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Compatibility dictionary normalizer for market-price records.
    """

    data = _mapping(
        record,
        "record",
    )

    symbol = _required_text(
        _first_present(
            data,
            "symbol",
            "ticker",
        ),
        "symbol",
    )

    price_date = _required_text(
        _first_present(
            data,
            "price_date",
            "priceDate",
            "date",
        ),
        "price_date",
    )

    return {
        "symbol": symbol.upper(),
        "price_date": price_date,
        "open_price": _number(
            _first_present(
                data,
                "open",
                "open_price",
            ),
            "open",
        ),
        "high_price": _number(
            _first_present(
                data,
                "high",
                "high_price",
            ),
            "high",
        ),
        "low_price": _number(
            _first_present(
                data,
                "low",
                "low_price",
            ),
            "low",
        ),
        "close_price": _number(
            _first_present(
                data,
                "close",
                "close_price",
            ),
            "close",
        ),
        "volume": _number(
            _first_present(
                data,
                "volume",
            ),
            "volume",
        ),
        "source": _required_text(
            _first_present(
                data,
                "source",
            ),
            "source",
        ),
    }


def normalize_batch(
    records: list[Mapping[str, Any]],
    *,
    record_type: str,
    source: str,
) -> list[
    InsiderTransaction
    | MarketPrice
    | CorporateAction
]:
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

    results: list[
        InsiderTransaction
        | MarketPrice
        | CorporateAction
    ] = []

    for index, record in enumerate(
        records
    ):
        try:
            if normalized_type == "insider_transaction":
                result = normalize_insider_transaction(
                    record,
                    source=source,
                )

            elif normalized_type == "market_price":
                result = normalize_market_price(
                    record,
                    source=source,
                )

            else:
                result = normalize_corporate_action(
                    record,
                    source=source,
                )

        except (
            NormalizationError,
            TypeError,
            ValueError,
        ) as exc:
            raise NormalizationError(
                f"Failed to normalize record {index}: {exc}"
            ) from exc

        results.append(
            result
        )

    return results
