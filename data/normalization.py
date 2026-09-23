"""
Data normalization layer for Insider Trade Bot.

This module converts externally retrieved data into the normalized domain
models used by validation, storage, research, and downstream components.

Normalization does not prove that the source data is correct or complete.
That responsibility belongs to validation and reconciliation layers.
"""

from __future__ import annotations

from typing import Any, Mapping

from core.models import (
    CorporateAction,
    InsiderTransaction,
    MarketPrice,
)


class NormalizationError(Exception):
    """Raised when external data cannot be normalized safely."""


def _text(
    value: Any,
) -> str | None:
    """
    Normalize a value into stripped text.

    Empty values become None.
    """

    if value is None:
        return None

    result = str(value).strip()

    if not result:
        return None

    return result


def _required_text(
    value: Any,
    field_name: str,
) -> str:
    """
    Normalize a required text field.
    """

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
    """
    Normalize a numeric value.

    Commas and surrounding whitespace are accepted for textual numbers.
    """

    if value is None:
        return None

    if isinstance(
        value,
        bool,
    ):
        raise NormalizationError(
            f"{field_name} must be numeric."
        )

    if isinstance(
        value,
        (int, float),
    ):
        return float(value)

    text_value = str(
        value
    ).strip()

    if not text_value:
        return None

    text_value = text_value.replace(
        ",",
        "",
    )

    try:
        return float(
            text_value
        )
    except ValueError as exc:
        raise NormalizationError(
            f"{field_name} must be numeric."
        ) from exc


def _mapping(
    value: Any,
    field_name: str,
) -> Mapping[str, Any]:
    """
    Ensure a supplied object behaves like a mapping.
    """

    if not isinstance(
        value,
        Mapping,
    ):
        raise NormalizationError(
            f"{field_name} must be an object or mapping."
        )

    return value


def normalize_insider_transaction(
    payload: Mapping[str, Any],
    *,
    source: str,
) -> InsiderTransaction:
    """
    Normalize one externally retrieved insider transaction.

    The function accepts common field aliases so that different upstream
    data representations can be mapped into one internal model.
    """

    data = _mapping(
        payload,
        "payload",
    )

    normalized_source = _required_text(
        source,
        "source",
    )

    accession_number = _required_text(
        data.get("accession_number")
        or data.get("accessionNumber")
        or data.get("accession"),
        "accession_number",
    )

    issuer_cik = _required_text(
        data.get("issuer_cik")
        or data.get("issuerCik")
        or data.get("cik"),
        "issuer_cik",
    )

    return InsiderTransaction(
        source=normalized_source,
        accession_number=accession_number,
        issuer_cik=issuer_cik,
        issuer_name=_text(
            data.get("issuer_name")
            or data.get("issuerName")
            or data.get("issuer")
        ),
        insider_name=_text(
            data.get("insider_name")
            or data.get("insiderName")
            or data.get("reporting_owner_name")
        ),
        insider_cik=_text(
            data.get("insider_cik")
            or data.get("insiderCik")
            or data.get("reporting_owner_cik")
        ),
        transaction_date=_text(
            data.get("transaction_date")
            or data.get("transactionDate")
            or data.get("transaction_date_formatted")
        ),
        filing_date=_text(
            data.get("filing_date")
            or data.get("filingDate")
        ),
        form_type=_text(
            data.get("form_type")
            or data.get("formType")
            or data.get("form")
        ),
        transaction_code=_text(
            data.get("transaction_code")
            or data.get("transactionCode")
            or data.get("code")
        ),
        shares=_number(
            data.get("shares"),
            "shares",
        ),
        price=_number(
            data.get("price")
            or data.get("transaction_price"),
            "price",
        ),
        ownership_type=_text(
            data.get("ownership_type")
            or data.get("ownershipType")
        ),
    )


def normalize_market_price(
    payload: Mapping[str, Any],
    *,
    source: str,
) -> MarketPrice:
    """
    Normalize one market-price record.
    """

    data = _mapping(
        payload,
        "payload",
    )

    normalized_source = _required_text(
        source,
        "source",
    )

    symbol = _required_text(
        data.get("symbol")
        or data.get("ticker"),
        "symbol",
    )

    price_date = _required_text(
        data.get("price_date")
        or data.get("priceDate")
        or data.get("date"),
        "price_date",
    )

    return MarketPrice(
        symbol=symbol.upper(),
        price_date=price_date,
        open=_number(
            data.get("open"),
            "open",
        ),
        high=_number(
            data.get("high"),
            "high",
        ),
        low=_number(
            data.get("low"),
            "low",
        ),
        close=_number(
            data.get("close"),
            "close",
        ),
        adjusted_close=_number(
            data.get("adjusted_close")
            or data.get("adjustedClose")
            or data.get("adj_close"),
            "adjusted_close",
        ),
        volume=_number(
            data.get("volume"),
            "volume",
        ),
        source=normalized_source,
    )


def normalize_corporate_action(
    payload: Mapping[str, Any],
    *,
    source: str,
) -> CorporateAction:
    """
    Normalize one corporate-action record.
    """

    data = _mapping(
        payload,
        "payload",
    )

    normalized_source = _required_text(
        source,
        "source",
    )

    symbol = _required_text(
        data.get("symbol")
        or data.get("ticker"),
        "symbol",
    )

    action_type = _required_text(
        data.get("action_type")
        or data.get("actionType")
        or data.get("type"),
        "action_type",
    )

    action_date = _required_text(
        data.get("action_date")
        or data.get("actionDate")
        or data.get("date"),
        "action_date",
    )

    return CorporateAction(
        symbol=symbol.upper(),
        action_type=action_type,
        action_date=action_date,
        ratio=_text(
            data.get("ratio")
        ),
        cash_amount=_number(
            data.get("cash_amount")
            or data.get("cashAmount")
            or data.get("amount"),
            "cash_amount",
        ),
        source=normalized_source,
    )


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
    """
    Normalize a homogeneous batch of records.

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

    results: list[
        InsiderTransaction
        | MarketPrice
        | CorporateAction
    ] = []

    for index, record in enumerate(records):
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

        results.append(result)

    return results
