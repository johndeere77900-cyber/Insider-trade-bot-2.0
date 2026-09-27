"""
SEC Form 3/4/5 transaction parser for Insider Trade Bot.

This module converts detailed SEC insider-filing data into normalized
transaction records.

It supports:
    - normalized dictionary payloads
    - SEC ownership XML converted to dictionaries
    - common JSON-derived SEC structures
    - non-derivative transactions
    - derivative transactions

The parser does not decide whether a transaction is a trading signal.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


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


def _text(value: Any) -> str | None:
    """Convert a value to stripped text."""

    if value is None:
        return None

    if isinstance(value, Mapping):
        nested_value = value.get("value")

        if nested_value is not None:
            return _text(nested_value)

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

    if isinstance(value, Mapping):
        value = value.get("value")

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


def _tag_name(key: Any) -> str:
    """
    Return an XML-local tag name.

    Handles both plain tags and namespace-qualified tags such as:
        {namespace}transactionCode
    """

    text = str(key)

    if "}" in text:
        text = text.rsplit("}", 1)[1]

    if ":" in text:
        text = text.rsplit(":", 1)[1]

    return text


def _first(
    data: Mapping[str, Any],
    *keys: str,
) -> Any:
    """
    Return the first present and non-empty direct value.

    This preserves compatibility with the existing flat dictionary API.
    """

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


def _deep_find(
    data: Any,
    keys: tuple[str, ...],
) -> Any:
    """
    Recursively locate the first matching SEC/XML field.

    SEC ownership XML commonly produces structures such as:

        {
            "transactionCoding": {
                "transactionCode": "P"
            }
        }

    or:

        {
            "transactionCoding": {
                "transactionCode": {
                    "value": "P"
                }
            }
        }

    This helper supports both representations.
    """

    wanted = {
        _tag_name(key)
        for key in keys
    }

    if isinstance(data, Mapping):
        for key, value in data.items():
            if _tag_name(key) in wanted:
                if value is not None:
                    return value

        for value in data.values():
            found = _deep_find(
                value,
                keys,
            )

            if found is not None:
                return found

        return None

    if isinstance(data, list):
        for item in data:
            found = _deep_find(
                item,
                keys,
            )

            if found is not None:
                return found

    return None


def _deep_find_section(
    data: Any,
    section_names: tuple[str, ...],
) -> list[Mapping[str, Any]]:
    """
    Recursively find mappings belonging to named SEC XML sections.

    Used primarily for nonDerivativeTransaction and
    derivativeTransaction nodes.
    """

    wanted = {
        _tag_name(name)
        for name in section_names
    }

    results: list[Mapping[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if _tag_name(key) in wanted:
                    if isinstance(child, Mapping):
                        results.append(child)
                    elif isinstance(child, list):
                        for item in child:
                            if isinstance(item, Mapping):
                                results.append(item)

                walk(child)

        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(data)

    return results


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
    """
    Extract transaction dictionaries from common SEC structures.

    Supports both normalized structures and the nested structure generated
    by data.sec_filing_pipeline._xml_to_dict().
    """

    records: list[Mapping[str, Any]] = []

    # Real SEC ownership XML structures.
    records.extend(
        _deep_find_section(
            payload,
            (
                "nonDerivativeTransaction",
                "derivativeTransaction",
            ),
        )
    )

    # Existing normalized/common JSON structures.
    for key in (
        "transactions",
        "nonDerivativeTransactions",
        "derivativeTransactions",
    ):
        value = payload.get(key)

        if isinstance(value, Mapping):
            for nested_key in (
                "transactions",
                "transaction",
                "items",
                "nonDerivativeTransaction",
                "derivativeTransaction",
            ):
                nested = value.get(nested_key)

                if isinstance(nested, Mapping):
                    records.append(nested)

                elif isinstance(nested, list):
                    records.extend(
                        item
                        for item in nested
                        if isinstance(item, Mapping)
                    )

        elif isinstance(value, list):
            records.extend(
                item
                for item in value
                if isinstance(item, Mapping)
            )

    # Some callers may provide one transaction directly.
    for key in (
        "transaction",
        "nonDerivativeTransaction",
        "derivativeTransaction",
    ):
        value = payload.get(key)

        if isinstance(value, Mapping):
            records.append(value)

        elif isinstance(value, list):
            records.extend(
                item
                for item in value
                if isinstance(item, Mapping)
            )

    # De-duplicate transaction object references/content without requiring
    # the transaction itself to be hashable.
    unique: list[Mapping[str, Any]] = []
    seen: set[int] = set()

    for record in records:
        identity = id(record)

        if identity in seen:
            continue

        seen.add(identity)
        unique.append(record)

    return unique


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

    if transaction_code is None:
        transaction_code = _deep_find(
            transaction,
            (
                "transactionCode",
            ),
        )

    shares = _first(
        transaction,
        "shares",
        "transactionShares",
        "transaction_shares",
        "amount",
    )

    if shares is None:
        shares = _deep_find(
            transaction,
            (
                "transactionShares",
                "shares",
            ),
        )

    price = _first(
        transaction,
        "transactionPricePerShare",
        "transactionPrice",
        "transaction_price",
        "price",
    )

    if price is None:
        price = _deep_find(
            transaction,
            (
                "transactionPricePerShare",
                "transactionPrice",
                "price",
            ),
        )

    transaction_date = _first(
        transaction,
        "transactionDate",
        "transaction_date",
        "date",
    )

    if transaction_date is None:
        transaction_date = _deep_find(
            transaction,
            (
                "transactionDate",
                "date",
            ),
        )

    ownership_type = _first(
        transaction,
        "ownershipType",
        "ownership_type",
        "directOrIndirectOwnership",
        "direct_indirect",
    )

    if ownership_type is None:
        ownership_type = _deep_find(
            transaction,
            (
                "directOrIndirectOwnership",
                "ownershipType",
            ),
        )

    security_title = _first(
        transaction,
        "securityTitle",
        "security_title",
        "security",
    )

    if security_title is None:
        security_title = _deep_find(
            transaction,
            (
                "securityTitle",
            ),
        )

    transaction_type = _first(
        transaction,
        "transactionType",
        "transaction_type",
    )

    if transaction_type is None:
        transaction_type = _deep_find(
            transaction,
            (
                "transactionType",
            ),
        )

    return {
        "source": normalized_source,
        "form_type": normalized_form,
        "transaction_code": _text(transaction_code),
        "transaction_date": _text(transaction_date),
        "shares": _number(shares, "shares"),
        "price": _number(price, "price"),
        "ownership_type": _text(ownership_type),
        "security_title": _text(security_title),
        "transaction_type": _text(transaction_type),
    }


def _extract_issuer_name(
    payload: Mapping[str, Any],
) -> str | None:
    """Extract issuer name from a real SEC ownership filing when available."""

    issuer = payload.get("issuer")

    if isinstance(issuer, Mapping):
        return _text(
            _deep_find(
                issuer,
                (
                    "issuerName",
                    "name",
                ),
            )
        )

    return _text(
        _deep_find(
            payload,
            (
                "issuerName",
            ),
        )
    )


def _extract_insider_metadata(
    payload: Mapping[str, Any],
) -> tuple[str | None, str | None]:
    """
    Extract reporting-owner name and CIK from SEC ownership XML when present.

    SEC XML converted to dictionaries may contain reportingOwner beneath
    the ownershipDocument root. Therefore this function searches the full
    payload recursively instead of requiring reportingOwner to be a
    top-level key.
    """

    reporting_owner = _deep_find(
        payload,
        (
            "reportingOwner",
        ),
    )

    if isinstance(reporting_owner, list):
        reporting_owner = (
            reporting_owner[0]
            if reporting_owner
            else None
        )

    if not isinstance(reporting_owner, Mapping):
        return None, None

    owner_name = _deep_find(
        reporting_owner,
        (
            "rptOwnerName",
            "reportingOwnerName",
        ),
    )

    owner_cik = _deep_find(
        reporting_owner,
        (
            "rptOwnerCik",
            "reportingOwnerCik",
        ),
    )

    return (
        _text(owner_name),
        _text(owner_cik),
    )


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

    transactions = _extract_transaction_list(
        payload
    )

    if not transactions:
        raise SECFormParserError(
            "SEC filing contains no identifiable insider transactions."
        )

    parsed: list[dict[str, Any]] = []

    payload_issuer_name = (
        _extract_issuer_name(payload)
        if issuer_name is None
        else issuer_name
    )

    payload_insider_name, payload_insider_cik = (
        _extract_insider_metadata(payload)
    )

    normalized_insider_name = (
        _text(insider_name)
        if insider_name is not None
        else payload_insider_name
    )

    normalized_insider_cik = (
        _text(insider_cik)
        if insider_cik is not None
        else payload_insider_cik
    )

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
                "issuer_name": _text(
                    payload_issuer_name
                ),
                "insider_name": normalized_insider_name,
                "insider_cik": normalized_insider_cik,
                "filing_date": _text(filing_date),
            }
        )

        parsed.append(
            parsed_transaction
        )

    return parsed
