"""
Record validation for Insider Trade Bot.

Validation happens before permanent storage. These functions validate
the basic structural and logical requirements expected by the agent's
record-processing layer.

Validation failures raise RecordValidationError.
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


def _require_fields(
    data: dict[str, Any],
    fields: tuple[str, ...],
) -> None:
    """Ensure required fields are present and non-empty."""

    missing = [
        field
        for field in fields
        if data.get(field) is None
        or str(data.get(field)).strip() == ""
    ]

    if missing:
        raise RecordValidationError(
            "Missing required field(s): "
            + ", ".join(missing)
        )


def validate_insider_record(record: Any) -> bool:
    """
    Validate an insider transaction record.

    Returns True when valid.
    Raises RecordValidationError when invalid.
    """

    data = _record_to_dict(record)

    _require_fields(
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

    transaction_type = str(
        data["transaction_type"]
    ).strip().upper()

    allowed_transaction_types = {
        "BUY",
        "SELL",
        "PURCHASE",
        "SALE",
    }

    if transaction_type not in allowed_transaction_types:
        raise RecordValidationError(
            f"Invalid transaction_type: "
            f"{data['transaction_type']}"
        )

    shares = data.get("shares")

    if shares is not None:
        if not isinstance(shares, (int, float)):
            raise RecordValidationError(
                "shares must be numeric."
            )

        if shares < 0:
            raise RecordValidationError(
                "shares cannot be negative."
            )

    price = data.get("price")

    if price is not None:
        if not isinstance(price, (int, float)):
            raise RecordValidationError(
                "price must be numeric."
            )

        if price < 0:
            raise RecordValidationError(
                "price cannot be negative."
            )

    return True


def validate_market_price_record(record: Any) -> bool:
    """
    Validate a market-price record.

    Returns True when valid.
    Raises RecordValidationError when invalid.
    """

    data = _record_to_dict(record)

    _require_fields(
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

        if value is not None:
            if not isinstance(value, (int, float)):
                raise RecordValidationError(
                    f"{field} must be numeric."
                )

            if value < 0:
                raise RecordValidationError(
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
        raise RecordValidationError(
            "high_price cannot be lower than low_price."
        )

    if (
        open_price is not None
        and high_price is not None
        and open_price > high_price
    ):
        raise RecordValidationError(
            "open_price cannot exceed high_price."
        )

    if (
        open_price is not None
        and low_price is not None
        and open_price < low_price
    ):
        raise RecordValidationError(
            "open_price cannot be below low_price."
        )

    if (
        close_price is not None
        and high_price is not None
        and close_price > high_price
    ):
        raise RecordValidationError(
            "close_price cannot exceed high_price."
        )

    if (
        close_price is not None
        and low_price is not None
        and close_price < low_price
    ):
        raise RecordValidationError(
            "close_price cannot be below low_price."
        )

    return True


def validate_required_text(
    value: Any,
    field_name: str,
) -> list[str]:
    """Validate a required text field."""

    if value is None or str(value).strip() == "":
        return [f"{field_name} is required."]

    return []
