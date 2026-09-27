"""
SEC Form 3/4/5 transaction parser for Insider Trade Bot.

This module converts detailed SEC insider-filing data into normalized
transaction records.

It supports common SEC JSON/XML-derived dictionary structures while keeping
source-specific parsing separate from validation and permanent storage.

The parser does not decide whether a transaction is a trading signal.
"""

from __future__ import annotations

from typing import Any, Mapping


class SECFormParserError(Exception):
    """Raised when an SEC insider filing cannot be parsed safely."""


class SECFormParser:
    """
    Object-oriented compatibility interface for the SEC form parser.

    The underlying parsing implementation remains in the module-level
    parse_transaction() and parse_filing() functions.
    """

    def parse_transaction(
        self,
        transaction: Mapping[str, Any],
        *,
        form_type: str,
        source: str = "SEC",
    ) -> dict[str, Any]:
        """Parse one SEC transaction."""

        return parse_transaction(
            transaction,
            form_type=form_type,
            source=source,
        )

    def parse_filing(
        self,
        payload: Mapping[str, Any],
        *,
        issuer_cik: str,
        accession_number: str,
        form_type: str,
        issuer_name: str | None = None,
        insider_name: str | None = None,
        insider_cik: str | None = None,
        filing_date: str | None = None,
        source: str = "SEC",
    ) -> list[dict[str, Any]]:
        """Parse all identifiable transactions from an SEC filing."""

        return parse_filing(
            payload,
            issuer_cik=issuer_cik,
            accession_number=accession_number,
            form_type=form_type,
            issuer_name=issuer_name,
            insider_name=insider_name,
            insider_cik=insider_cik,
            filing_date=filing_date,
            source=source,
        )


def _text(
    value: Any,
) -> str | None:
    """Convert a value to stripped text."""

    if value is None:
        return None

    result = str(value).strip()

    if not result:
        return None

    return result


def _number(
    value: Any,
    field_name: str,
) -> float | None:
    """Convert a numeric SEC field to float."""

    if value is None:
        return None

    if isinstance(value, bool):
        raise SECFormParserError(
            f"{field_name} cannot be boolean."
        )

    if isinstance(value, (int, float)):
        return float(value)

    text_value = str(value).strip()

    if not text_value:
        return None

    text_value = text_value.replace(",", "")

    try:
        return float(text_value)
    except ValueError as exc:
        raise SECFormParserError(
            f"{field_name} must be numeric."
        ) from exc


def _first(
    data: Mapping[str, Any],
    *keys: str,
) -> Any:
    """Return the first present and non-empty value from several aliases."""

    for key in keys:
        if key not in data:
            continue

        value = data[key]

        if value is None:
            continue

        if isinstance(value, str) and not value.strip():
            continue

        return value

    return None


def _normalize_form(
    value: Any,
) -> str:
    """Normalize an SEC insider form identifier."""

    form = _text(value)

    if form is None:
        raise SECFormParserError(
            "SEC form type is required."
        )

    normalized = form.upper()

    if normalized not in {
        "3",
        "4",
        "5",
        "3/A",
        "4/A",
        "5/A",
    }:
        raise SECFormParserError(
            f"Unsupported insider form: {form}"
        )

    return normalized


def _extract_transaction_list(
    payload: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    """Extract transaction dictionaries from common SEC structures."""

    transaction_lists: list[list[Any]] = []

    for key in (
        "transactions",
        "nonDerivativeTransactions",
        "nonDerivativeTable",
        "derivativeTransactions",
        "derivativeTable",
    ):
        value = payload.get(key)

        if isinstance(value, list):
            transaction_lists.append(value)

        elif isinstance(value, Mapping):
            for nested_key in (
                "transactions",
                "transaction",
                "items",
            ):
                nested = value.get(nested_key)

                if isinstance(nested, list):
                    transaction_lists.append(nested)

    records: list[Mapping[str, Any]] = []

    for transaction_list in transaction_lists:
        for item in transaction_list:
            if isinstance(item, Mapping):
                records.append(item)

    return records


def parse_transaction(
    transaction: Mapping[str, Any],
    *,
    form_type: str,
    source: str = "SEC",
) -> dict[str, Any]:
    """Parse one SEC transaction."""

    if not isinstance(transaction, Mapping):
        raise TypeError(
            "transaction must be a mapping."
        )

    normalized_form = _normalize_form(form_type)

    normalized_source = _text(source)

    if normalized_source is None:
        raise SECFormParserError(
            "source cannot be empty."
        )

    transaction_code = _first(
        transaction,
        "transactionCode",
        "transaction_code",
        "code",
    )

    shares = _first(
        transaction,
        "shares",
        "transactionShares",
        "transaction_shares",
        "amount",
    )

    price = _first(
        transaction,
        "transactionPricePerShare",
        "transactionPrice",
        "transaction_price",
        "price",
    )

    transaction_date = _first(
        transaction,
        "transactionDate",
        "transaction_date",
        "date",
    )

    ownership_type = _first(
        transaction,
        "ownershipType",
        "ownership_type",
        "directOrIndirectOwnership",
        "direct_indirect",
    )

    return {
        "source": normalized_source,
        "form_type": normalized_form,
        "transaction_code": _text(transaction_code),
        "transaction_date": _text(transaction_date),
        "shares": _number(shares, "shares"),
        "price": _number(price, "price"),
        "ownership_type": _text(ownership_type),
        "security_title": _text(
            _first(
                transaction,
                "securityTitle",
                "security_title",
                "security",
            )
        ),
        "transaction_type": _text(
            _first(
                transaction,
                "transactionType",
                "transaction_type",
            )
        ),
    }


def parse_filing(
    payload: Mapping[str, Any],
    *,
    issuer_cik: str,
    accession_number: str,
    form_type: str,
    issuer_name: str | None = None,
    insider_name: str | None = None,
    insider_cik: str | None = None,
    filing_date: str | None = None,
    source: str = "SEC",
) -> list[dict[str, Any]]:
    """Parse all identifiable transactions from one SEC Form 3/4/5 filing."""

    if not isinstance(payload, Mapping):
        raise TypeError(
            "SEC filing payload must be a mapping."
        )

    normalized_cik = _text(issuer_cik)

    if normalized_cik is None:
        raise SECFormParserError(
            "issuer_cik is required."
        )

    if not normalized_cik.isdigit():
        raise SECFormParserError(
            "issuer_cik must contain digits only."
        )

    normalized_cik = normalized_cik.zfill(10)

    normalized_accession = _text(accession_number)

    if normalized_accession is None:
        raise SECFormParserError(
            "accession_number is required."
        )

    normalized_form = _normalize_form(form_type)

    transactions = _extract_transaction_list(payload)

    parsed: list[dict[str, Any]] = []

    for index, transaction in enumerate(transactions):
        try:
            parsed_transaction = parse_transaction(
                transaction,
                form_type=normalized_form,
                source=source,
            )
        except (
            SECFormParserError,
            TypeError,
            ValueError,
        ) as exc:
            raise SECFormParserError(
                f"Failed to parse SEC transaction {index}: {exc}"
            ) from exc

        parsed_transaction.update(
            {
                "issuer_cik": normalized_cik,
                "accession_number": normalized_accession,
                "issuer_name": _text(issuer_name),
                "insider_name": _text(insider_name),
                "insider_cik": _text(insider_cik),
                "filing_date": _text(filing_date),
            }
        )

        parsed.append(parsed_transaction)

    return parsed
