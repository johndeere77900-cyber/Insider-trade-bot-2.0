"""
Point-in-time research price adjustment boundary for Insider Trade Bot.

Provides deterministic research-time adjustment from raw market prices + corporate actions.
This module strictly NEVER modifies stored raw market prices or corporate-action database semantics.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence


class UnsupportedCorporateActionError(ValueError):
    """Raised when a corporate action cannot be deterministically interpreted."""


@dataclass(frozen=True)
class PriceAdjustmentFactor:
    """Explicit adjustment factor derived from a corporate action."""

    symbol: str
    action_date: str
    action_type: str
    factor: float
    source: str


def _parse_ratio_factor(ratio_str: str) -> float:
    """
    Parse split ratio string into a multiplicative factor for historical price adjustment.

    Common formats:
    - "4:1" or "4/1" (4-for-1 forward split -> factor = 1 / 4 = 0.25)
    - "1:10" or "1/10" (1-for-10 reverse split -> factor = 1 / (1/10) = 10.0)
    - "4" or "0.25"
    """
    if not ratio_str:
        raise UnsupportedCorporateActionError("Corporate action ratio is missing or empty.")

    cleaned = str(ratio_str).strip()

    # Match "A:B" or "A/B"
    match = re.match(r"^([\d.]+)\s*[:/]\s*([\d.]+)$", cleaned)
    if match:
        num = float(match.group(1))
        den = float(match.group(2))
        if num <= 0 or den <= 0:
            raise UnsupportedCorporateActionError(f"Invalid non-positive numbers in ratio '{cleaned}'.")
        ratio_val = num / den
    else:
        try:
            ratio_val = float(cleaned)
        except ValueError as exc:
            raise UnsupportedCorporateActionError(f"Unparseable ratio format '{cleaned}'.") from exc

    if ratio_val <= 0:
        raise UnsupportedCorporateActionError(f"Corporate action ratio must be positive: '{cleaned}'.")

    # If ratio_val > 0, multiplicative adjustment factor for historical price before split ratio R = 1 / R.
    # E.g. A 4:1 split (ratio_val = 4.0) turns a pre-split $100 price into $25 (factor = 0.25).
    return 1.0 / ratio_val


def apply_point_in_time_adjustment(
    *,
    symbol: str,
    price_date: str,
    raw_price: float,
    corporate_actions: Sequence[Mapping[str, object]],
    as_of_date: str | None = None,
) -> float:
    """
    Apply corporate-action price adjustment to a raw historical price as of a point-in-time date.

    Rules:
    1. Never mutate original raw price.
    2. Never apply an action whose action_date is after as_of_date.
    3. If as_of_date is omitted, use price_date as the knowledge cutoff for historical PIT calculation.
    4. Ignore actions for another symbol.
    5. Ignore malformed actions rather than inventing a factor.
    6. Never apply an action twice.
    7. Preserve deterministic ordering by (action_date, action_type, source).
    8. Split/reverse-split/stock-dividend actions must be represented using an explicit factor.
    9. Cash dividends must NOT be treated as a split factor unless explicitly supported with a total-return factor.
    10. Unsupported action types must remain visible to the caller and must not silently alter the price.
    """
    if raw_price is None or not isinstance(raw_price, (int, float)):
        raise TypeError("raw_price must be numeric.")
    if raw_price <= 0:
        raise ValueError("raw_price must be greater than zero.")

    norm_symbol = str(symbol).strip().upper()
    if not norm_symbol:
        raise ValueError("symbol cannot be empty.")

    norm_price_date = str(price_date).strip()
    if not norm_price_date:
        raise ValueError("price_date cannot be empty.")

    cutoff_date = str(as_of_date).strip() if as_of_date is not None else norm_price_date

    # Filter actions for symbol and sort deterministically by (action_date, action_type, source)
    applicable_raw: list[Mapping[str, object]] = []
    seen_keys: set[tuple[str, str, str, str]] = set()

    for item in corporate_actions:
        if not isinstance(item, Mapping):
            continue

        item_symbol = str(item.get("symbol") or "").strip().upper()
        if item_symbol != norm_symbol:
            continue

        item_date = str(item.get("action_date") or item.get("actionDate") or item.get("date") or "").strip()
        if not item_date:
            continue

        # Rule 2: Never apply an action whose action_date is after as_of_date
        if item_date > cutoff_date:
            continue

        # Rule 3 & adjustment rule: Only actions effective AFTER the price_date adjust historical price before action_date!
        # If price_date >= action_date, the raw price was ALREADY observed post-action!
        if norm_price_date >= item_date:
            continue

        action_type = str(item.get("action_type") or item.get("actionType") or item.get("type") or "").strip().lower()
        source = str(item.get("source") or "").strip()

        # Rule 6: Never apply an action twice (deduplicate by identity key)
        dedup_key = (norm_symbol, item_date, action_type, source)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        applicable_raw.append({
            "symbol": norm_symbol,
            "action_date": item_date,
            "action_type": action_type,
            "source": source,
            "ratio": item.get("ratio"),
            "cash_amount": item.get("cash_amount") or item.get("cashAmount"),
        })

    # Sort deterministically by (action_date, action_type, source)
    applicable_raw.sort(key=lambda x: (x["action_date"], x["action_type"], x["source"]))

    adjusted_price = float(raw_price)

    for item in applicable_raw:
        action_type = item["action_type"]

        if action_type in {"split", "stock_split", "forward_split", "reverse_split", "stock_dividend"}:
            ratio_val = item.get("ratio")
            if ratio_val is None:
                raise UnsupportedCorporateActionError(
                    f"Corporate action '{action_type}' for {norm_symbol} on {item['action_date']} is missing required 'ratio'."
                )
            factor = _parse_ratio_factor(str(ratio_val))
            adjusted_price *= factor

        elif action_type in {"dividend", "cash_dividend"}:
            # Cash dividends are ignored for split adjustment unless a supported factor exists
            continue
        else:
            # Unsupported action type
            raise UnsupportedCorporateActionError(
                f"Unsupported corporate action type '{action_type}' for {norm_symbol} on {item['action_date']}."
            )

    return float(adjusted_price)
