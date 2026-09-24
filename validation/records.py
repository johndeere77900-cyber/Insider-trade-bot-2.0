"""
Record validation for Insider Trade Bot.

This module provides two compatible validation interfaces:

1. Legacy ingestion-pipeline validators:
   - validate_insider_transaction()
   - validate_market_price()
   - validate_corporate_action()

   These return a list of validation errors.

2. Record-level validators used by the test/domain API:
   - validate_insider_record()
   - validate_market_price_record()

   These return True when valid and raise RecordValidationError when invalid.

Both interfaces operate on normalized records or dictionaries.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


class RecordValidationError(ValueError):
    """Raised when a record fails validation."""


def _record_to_dict(record: Any) -> dict[str, Any]:
    """Convert a supported record object into a dictionary."""

    if is_dataclass(record):
        return asdict(record)

    if isinstance(record, dict):
        return dict(record)

    raise RecordValidationError(
        "Record must be a dataclass instance or dictionary."
    )


def _required_field_errors(
    data: dict[str, Any],
    fields: tuple[str, ...],
) -> list[str]:
    """Return errors for missing or empty required fields."""

    errors: list[str] = []

    for field in fields:
        value = data.get(field)

        if value is None or str(value).strip() == "":
            errors.append(
                f"{field} is required."
            )

    return errors


def _numeric_error(
    value: Any,
    field: str,
) -> str | None:
    """Return a numeric-type error when applicable."""

    if value is None:
        return None

    if not isinstance(value, (int, float)):
        return f"{field} must be numeric."

    return None


def validate_insider_transaction(
    record: Any,
) -> list[str]:
    """
    Validate a normalized insider transaction.

    Returns:
        A list of validation errors.

    An empty list means the record passed validation.
    """

    data = _record_to_dict(record)

    errors = _required_field_errors(
        data,
        (
            "source",
            "accession_number",
            "issuer_cik",
        ),
    )

    shares_error = _numeric_error(
        data.get("shares"),
        "shares",
    )

    if shares_error:
        errors.append(shares_error)

    elif data.get("shares") is not None:
        if data["shares"] < 0:
            errors.append(
                "shares cannot be negative."
            )

    price_error = _numeric_error(
        data.get("price"),
        "price",
    )

    if price_error:
        errors.append(price_error)

    elif data.get("price") is not None:
        if data["price"] < 0:
            errors.append(
                "price cannot be negative."
            )

    return errors


def validate_market_price(
    record: Any,
) -> list[str]:
    """
    Validate a normalized market-price record.

    Returns:
        A list of validation errors.

    An empty list means the record passed validation.
    """

    data = _record_to_dict(record)

    errors = _required_field_errors(
        data,
        (
            "symbol",
            "price_date",
            "source",
        ),
    )

    numeric_fields = (
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
    )

    for field in numeric_fields:
        value = data.get(field)

        numeric_error = _numeric_error(
            value,
            field,
        )

        if numeric_error:
            errors.append(numeric_error)
            continue

        if value is not None and value < 0:
            errors.append(
                f"{field} cannot be negative."
            )

    return errors


def validate_corporate_action(
    record: Any,
) -> list[str]:
    """
    Validate a normalized corporate-action record.

    Returns:
        A list of validation errors.

    An empty list means the record passed validation.
    """

    data = _record_to_dict(record)

    errors = _required_field_errors(
        data,
        (
            "symbol",
            "action_type",
            "action_date",
            "source",
        ),
    )

    cash_amount = data.get("cash_amount")

    numeric_error = _numeric_error(
        cash_amount,
        "cash_amount",
    )

    if numeric_error:
        errors.append(numeric_error)

    elif cash_amount is not None and cash_amount < 0:
        errors.append(
            "cash_amount cannot be negative."
        )

    return errors


def validate_insider_record(
    record: Any,
) -> bool:
    """
    Validate an insider record using the strict record API.

    Returns:
        True when valid.

    Raises:
        RecordValidationError when invalid.
    """

    data = _record_to_dict(record)

    errors = _required_field_errors(
        data,
        (
            "symbol",
            "insider_name",
            "transaction_date",
            "transaction_type",
            "source",
            "accession_number",
        ),
    )

    transaction_type = data.get(
        "transaction_type"
    )

    if transaction_type is not None:
        normalized_type = str(
            transaction_type
        ).strip().upper()

        allowed_types = {
            "BUY",
            "SELL",
            "PURCHASE",
            "SALE",
        }

        if normalized_type not in allowed_types:
            errors.append(
                f"Invalid transaction_type: "
                f"{transaction_type}"
            )

    shares = data.get("shares")

    numeric_error = _numeric_error(
        shares,
        "shares",
    )

    if numeric_error:
        errors.append(numeric_error)

    elif shares is not None and shares < 0:
        errors.append(
            "shares cannot be negative."
        )

    price = data.get("price")

    numeric_error = _numeric_error(
        price,
        "price",
    )

    if numeric_error:
        errors.append(numeric_error)

    elif price is not None and price < 0:
        errors.append(
            "price cannot be negative."
        )

    if errors:
        raise RecordValidationError(
            "Record validation failed: "
            + "; ".join(errors)
        )

    return True


def validate_market_price_record(
    record: Any,
) -> bool:
    """
    Validate a market-price record using the strict record API.

    Returns:
        True when valid.

    Raises:
        RecordValidationError when invalid.
    """

    data = _record_to_dict(record)

    errors = _required_field_errors(
        data,
        (
            "symbol",
            "price_date",
            "source",
        ),
    )

    numeric_fields = (
        "open_price",
        "high_price",
        "low_price",
        "close_price",
        "volume",
    )

    for field in numeric_fields:
        value = data.get(field)

        numeric_error = _numeric_error(
            value,
            field,
        )

        if numeric_error:
            errors.append(numeric_error)
            continue

        if value is not None and value < 0:
            errors.append(
                f"{field} cannot be negative."
            )

    open_price = data.get("open_price")
    high_price = data.get("high_price")
    low_price = data.get("low_price")
    close_price = data.get("close_price")

    if (
        high_price is not None
        and low_price is not None
        and high_price < low_price
    ):
        errors.append(
            "high_price cannot be lower than low_price."
        )

    if (
        open_price is not None
        and high_price is not None
        and open_price > high_price
    ):
        errors.append(
            "open_price cannot exceed high_price."
        )

    if (
        open_price is not None
        and low_price is not None
        and open_price < low_price
    ):
        errors.append(
            "open_price cannot be below low_price."
        )

    if (
        close_price is not None
        and high_price is not None
        and close_price > high_price
    ):
        errors.append(
            "close_price cannot exceed high_price."
        )

    if (
        close_price is not None
        and low_price is not None
        and close_price < low_price
    ):
        errors.append(
            "close_price cannot be below low_price."
        )

    if errors:
        raise RecordValidationError(
            "Record validation failed: "
            + "; ".join(errors)
        )

    return True


def validate_required_text(
    value: Any,
    field_name: str,
) -> list[str]:
    """Validate a required text field."""

    if value is None or str(value).strip() == "":
        return [
            f"{field_name} is required."
        ]

    return []
