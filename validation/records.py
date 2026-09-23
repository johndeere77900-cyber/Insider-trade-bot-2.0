"""
Record validation for Insider Trade Bot.

Validation happens before permanent storage. These functions check the
basic structural and logical requirements of normalized records.

Validation does not claim that a record is historically complete or that
the source itself is authoritative. Source verification and reconciliation
are handled by higher-level components.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any


def _record_to_dict(record: Any) -> dict[str, Any]:
    """
    Convert a supported record object into a dictionary.
    """

    if is_dataclass(record):
        return asdict(record)

    if isinstance(record, dict):
        return dict(record)

    raise TypeError(
        "Record must be a dataclass instance or dictionary."
    )


def validate_insider_transaction(
    record: Any,
) -> list[str]:
    """
    Validate an insider transaction.

    Returns:
        A list of validation errors.

    An empty list means that the basic structural validation passed.
    """

    data = _record_to_dict(record)
    errors: list[str] = []

    required_fields = (
        "source",
        "accession_number",
        "issuer_cik",
    )

    for field in required_fields:
        value = data.get(field)

        if value is None or str(value).strip() == "":
            errors.append(
                f"{field} is required."
            )

    shares = data.get("shares")

    if shares is not None:
        if not isinstance(shares, (int, float)):
            errors.append(
                "shares must be numeric."
            )

    price = data.get("price")

    if price is not None:
        if not isinstance(price, (int, float)):
            errors.append(
                "price must be numeric."
            )

    return errors


def validate_market_price(
    record: Any,
) -> list[str]:
    """
    Validate a normalized market-price record.
    """

    data = _record_to_dict(record)
    errors: list[str] = []

    required_fields = (
        "symbol",
        "price_date",
        "source",
    )

    for field in required_fields:
        value = data.get(field)

        if value is None or str(value).strip() == "":
            errors.append(
                f"{field} is required."
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

        if value is not None and not isinstance(
            value,
            (int, float),
        ):
            errors.append(
                f"{field} must be numeric."
            )

    for field in (
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
    ):
        value = data.get(field)

        if isinstance(value, (int, float)) and value < 0:
            errors.append(
                f"{field} cannot be negative."
            )

    return errors


def validate_corporate_action(
    record: Any,
) -> list[str]:
    """
    Validate a normalized corporate-action record.
    """

    data = _record_to_dict(record)
    errors: list[str] = []

    required_fields = (
        "symbol",
        "action_type",
        "action_date",
        "source",
    )

    for field in required_fields:
        value = data.get(field)

        if value is None or str(value).strip() == "":
            errors.append(
                f"{field} is required."
            )

    cash_amount = data.get("cash_amount")

    if cash_amount is not None:
        if not isinstance(
            cash_amount,
            (int, float),
        ):
            errors.append(
                "cash_amount must be numeric."
            )
        elif cash_amount < 0:
            errors.append(
                "cash_amount cannot be negative."
            )

    return errors


def validate_required_text(
    value: Any,
    field_name: str,
) -> list[str]:
    """
    Validate a required text field.
    """

    if value is None or str(value).strip() == "":
        return [f"{field_name} is required."]

    return []
