"""
Adapter module connecting normalized insider transactions to event-study research calculations.

Converts `NormalizedBulkTransaction` domain objects into structured research event inputs
for `research.research.event_study.run_event_study`, enforcing data quality rules and producing
explicit rejection diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

from data.sec_dataset_pipeline import NormalizedBulkTransaction
from research.research_data_access import get_market_prices_for_ticker


REJECTION_MISSING_TICKER = "REJECTED_MISSING_TICKER"
REJECTION_MISSING_DATE = "REJECTED_MISSING_DATE"
REJECTION_INVALID_DATE = "REJECTED_INVALID_DATE"
REJECTION_MISSING_PRICE = "REJECTED_MISSING_PRICE"
REJECTION_INSUFFICIENT_OBSERVATIONS = "REJECTED_INSUFFICIENT_OBSERVATIONS"
REJECTION_AMENDMENT_SUPERSEDED = "REJECTED_AMENDMENT_SUPERSEDED"
REJECTED_AMENDMENT_AMBIGUOUS = "REJECTED_AMENDMENT_AMBIGUOUS"
REJECTED_AMENDMENT_UNRESOLVED_ORIGINAL = "REJECTED_AMENDMENT_UNRESOLVED_ORIGINAL"


@dataclass(frozen=True)
class ResearchEventInput:
    """
    Prepared event input ready for the event-study engine.
    """
    event_key: str
    symbol: str
    event_date: str
    event_price: float
    prices: Dict[str, float]
    transaction: NormalizedBulkTransaction


@dataclass(frozen=True)
class EventAdapterRejection:
    """
    Diagnostic report for an insider transaction that could not be mapped to a research event.
    """
    accession_number: str
    record_hash: Optional[str]
    reason: str
    details: str


@dataclass(frozen=True)
class EventAdapterResult:
    """
    Container for adapter output: valid research event inputs and rejection diagnostics.
    """
    valid_events: Tuple[ResearchEventInput, ...]
    rejections: Tuple[EventAdapterRejection, ...]


def _deduplicate_amendments(
    transactions: List[NormalizedBulkTransaction],
) -> Tuple[List[NormalizedBulkTransaction], List[EventAdapterRejection]]:
    """
    Deduplicate transactions where an SEC amendment occurs.
    Preserves all records in operational storage (`insider_transactions`).

    Rules:
    1. SEC Bulk Dataset Limitation:
       The SEC Form 3/4/5 bulk dataset does NOT provide an authoritative original accession
       number link or original transaction key linking amendments across separate submissions.
       DATE_OF_ORIG_SUB is solely a date string and NOT an authoritative unique filing identifier.
    2. Zero Supersession by Heuristics:
       Original filings are NEVER superseded based on DATE_OF_ORIG_SUB, same accession numbers,
       or business-key matching heuristics.
    3. Unresolved Amendment Handling:
       Any amendment filing (`is_amendment=True`, `/A` form type, or non-empty `date_of_orig_submission`)
       where an authoritative original link is absent in the source data is treated as an unresolved amendment.
       The original transaction is kept as the valid research event.
       The unresolved amendment is excluded from research-event selection with `REJECTED_AMENDMENT_UNRESOLVED_ORIGINAL`
       to prevent double-counting without guessing or corrupting effective events.
    4. Legitimate Non-Amended Transactions:
       Non-amended transactions (even matching issuer, insider, transaction date, and security) are NEVER collapsed.
    """
    amendments: List[NormalizedBulkTransaction] = []
    originals: List[NormalizedBulkTransaction] = []

    for tx in transactions:
        form = (tx.form_type or "4").upper()
        if tx.is_amendment or "/A" in form or bool(tx.date_of_orig_submission):
            amendments.append(tx)
        else:
            originals.append(tx)

    if not amendments:
        return transactions, []

    effective_txs: List[NormalizedBulkTransaction] = list(originals)
    rejections: List[EventAdapterRejection] = []

    for amend_tx in amendments:
        # Since SEC bulk data lacks an authoritative original link field, cross-filing amendments
        # cannot be linked deterministically to an original filing without guessing.
        # Exclude the unresolved amendment from research events to prevent double counting,
        # while keeping the original transaction intact and valid.
        rejections.append(
            EventAdapterRejection(
                accession_number=amend_tx.accession_number or "UNKNOWN",
                record_hash=amend_tx.record_hash,
                reason=REJECTED_AMENDMENT_UNRESOLVED_ORIGINAL,
                details=(
                    f"Unresolved SEC amendment filing (Accession: {amend_tx.accession_number}, "
                    f"date_of_orig_submission: '{amend_tx.date_of_orig_submission}'): "
                    f"SEC bulk dataset lacks an authoritative original filing key link. "
                    f"Guessing avoided; original filings preserved."
                ),
            )
        )

    return effective_txs, rejections


def prepare_event_study_inputs(
    database_url: str,
    transactions: List[NormalizedBulkTransaction],
    horizon_days: int = 1,
) -> EventAdapterResult:
    """
    Convert normalized insider transactions into event-study engine inputs.

    Data Quality & Point-In-Time Safety rules:
    - Missing ticker -> REJECTED_MISSING_TICKER
    - Missing or invalid filing_date / transaction_date -> REJECTED_MISSING_DATE / REJECTED_INVALID_DATE
    - Point-In-Time safety: event_price is strictly sourced from the first available market-price
      observation STRICTLY AFTER filing_date (never same-day closing price on filing_date).
    - Missing price observation strictly after filing_date -> REJECTED_MISSING_PRICE
    - Insufficient price observations after post-filing entry date for horizon_days -> REJECTED_INSUFFICIENT_OBSERVATIONS
    - Superseded / unresolved amendments -> REJECTED_AMENDMENT_UNRESOLVED_ORIGINAL
    """
    valid_events: List[ResearchEventInput] = []

    # 0. Deduplicate superseded filings/transactions
    effective_transactions, rejections = _deduplicate_amendments(transactions)

    # Cache market prices per ticker to avoid repetitive queries
    price_cache: Dict[str, Dict[str, float]] = {}

    for tx in effective_transactions:
        acc = tx.accession_number or "UNKNOWN"
        rec_hash = tx.record_hash

        # 1. Ticker check
        if not tx.ticker or not tx.ticker.strip():
            rejections.append(
                EventAdapterRejection(
                    accession_number=acc,
                    record_hash=rec_hash,
                    reason=REJECTION_MISSING_TICKER,
                    details="Transaction record has no valid ticker symbol.",
                )
            )
            continue

        ticker = tx.ticker.strip().upper()

        # 2. Date check (Point-In-Time safety: public information date is filing_date)
        if not tx.filing_date or not tx.filing_date.strip():
            rejections.append(
                EventAdapterRejection(
                    accession_number=acc,
                    record_hash=rec_hash,
                    reason=REJECTION_MISSING_DATE,
                    details="Transaction record has no valid filing date.",
                )
            )
            continue

        filing_date = tx.filing_date.strip()

        # 3. Market price lookup for ticker
        if ticker not in price_cache:
            price_cache[ticker] = get_market_prices_for_ticker(database_url, ticker)

        prices = price_cache[ticker]

        # Strict Point-In-Time boundary:
        # event_price MUST come from the first available price observation STRICTLY AFTER filing_date.
        post_filing_dates = [d for d in sorted(prices.keys()) if d > filing_date]

        if not post_filing_dates:
            rejections.append(
                EventAdapterRejection(
                    accession_number=acc,
                    record_hash=rec_hash,
                    reason=REJECTION_MISSING_PRICE,
                    details=f"No market price observation strictly after filing date {filing_date} for {ticker}.",
                )
            )
            continue

        post_filing_date = post_filing_dates[0]
        event_price = prices[post_filing_date]

        # 4. Insufficient future observations check after post_filing_date
        future_dates_after_entry = [d for d in post_filing_dates if d > post_filing_date]
        if len(future_dates_after_entry) < horizon_days:
            rejections.append(
                EventAdapterRejection(
                    accession_number=acc,
                    record_hash=rec_hash,
                    reason=REJECTION_INSUFFICIENT_OBSERVATIONS,
                    details=(
                        f"Insufficient price observations ({len(future_dates_after_entry)}) after entry date {post_filing_date} "
                        f"(filing date {filing_date}) for horizon {horizon_days}."
                    ),
                )
            )
            continue

        # 5. Deterministic event_key
        event_key = f"{ticker}|{filing_date}|{acc}|{rec_hash or 'nohash'}"

        valid_events.append(
            ResearchEventInput(
                event_key=event_key,
                symbol=ticker,
                event_date=post_filing_date,
                event_price=event_price,
                prices=prices,
                transaction=tx,
            )
        )

    return EventAdapterResult(
        valid_events=tuple(valid_events),
        rejections=tuple(rejections),
    )


def convert_events_to_event_study_payloads(
    events: Tuple[ResearchEventInput, ...],
) -> List[Dict[str, Any]]:
    """
    Format valid ResearchEventInputs into dictionary dict payloads accepted by `run_event_study`.
    """
    payloads = []
    for ev in events:
        payloads.append(
            {
                "event_key": ev.event_key,
                "symbol": ev.symbol,
                "event_date": ev.event_date,
                "event_price": ev.event_price,
                "prices": ev.prices,
            }
        )
    return payloads


def convert_events_to_backtest_trades(
    events: Tuple[ResearchEventInput, ...],
    holding_periods: int = 1,
) -> List[Dict[str, Any]]:
    """
    Convert ResearchEventInput items into simulated trade inputs compatible with
    `backtesting.engine.run_backtest`.
    """
    trades = []
    for ev in events:
        trades.append(
            {
                "signal_key": ev.event_key,
                "symbol": ev.symbol,
                "entry_date": ev.event_date,
                "entry_price": ev.event_price,
                "prices": ev.prices,
                "holding_periods": holding_periods,
            }
        )
    return trades
