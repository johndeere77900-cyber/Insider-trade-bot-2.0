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
    Deduplicate transactions where an explicit SEC amendment replaces an original filing.
    Preserves all records in operational storage, but selects only effective, authoritative transactions for research.

    Rules:
    1. Authoritative Same-Accession Match:
       If an amendment filing (/A) shares the EXACT same accession_number as an original filing
       record (or represents an updated transaction inside the same accession), the original transaction
       is deterministically superseded (REJECTED_AMENDMENT_SUPERSEDED), and the amendment is kept as effective.
    2. Non-Authoritative / Cross-Accession Amendment:
       When an amendment specifies `is_amendment=True` or form_type `/A` or `date_of_orig_submission`, but exists
       in a different accession_number from original filings in the dataset:
       - The SEC bulk dataset does NOT provide an original accession_number link.
       - DATE_OF_ORIG_SUB is a date string and NOT an authoritative unique filing identifier.
       - A single candidate matching by DATE_OF_ORIG_SUB + CIKs + transaction date is NOT treated as an authoritative supersession.
       - Guessing is strictly avoided: original filings across different accessions are NOT marked superseded.
       - The uncertain amendment transaction is excluded from research-event selection with REJECTED_AMENDMENT_UNRESOLVED_ORIGINAL
         to prevent double-counting.
    3. Legitimate Same-Day Transactions:
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

    effective_txs: List[NormalizedBulkTransaction] = []
    rejections: List[EventAdapterRejection] = []
    excluded_hashes = set()

    for amend_tx in amendments:
        amend_hash = amend_tx.record_hash or id(amend_tx)

        # 1. Authoritative same-accession match
        same_accession_candidates = [
            orig_tx for orig_tx in originals
            if orig_tx.accession_number and orig_tx.accession_number == amend_tx.accession_number
        ]

        if len(same_accession_candidates) == 1:
            # Case A: Exactly 1 deterministic original candidate in same accession
            orig_tx = same_accession_candidates[0]
            orig_hash = orig_tx.record_hash or id(orig_tx)
            excluded_hashes.add(orig_hash)
            rejections.append(
                EventAdapterRejection(
                    accession_number=orig_tx.accession_number or "UNKNOWN",
                    record_hash=orig_tx.record_hash,
                    reason=REJECTION_AMENDMENT_SUPERSEDED,
                    details=(
                        f"Original transaction superseded by authoritative same-accession amendment filing "
                        f"(Accession: {amend_tx.accession_number})."
                    ),
                )
            )
        elif len(same_accession_candidates) > 1:
            # Case B: Ambiguous match (>1 same-accession candidates) -> Do not guess; exclude amendment and candidates
            excluded_hashes.add(amend_hash)
            for cand in same_accession_candidates:
                cand_hash = cand.record_hash or id(cand)
                excluded_hashes.add(cand_hash)
                rejections.append(
                    EventAdapterRejection(
                        accession_number=cand.accession_number or "UNKNOWN",
                        record_hash=cand.record_hash,
                        reason=REJECTED_AMENDMENT_AMBIGUOUS,
                        details=(
                            f"Ambiguous same-accession filing relationship: multiple candidates ({len(same_accession_candidates)}) "
                            f"in accession {amend_tx.accession_number}."
                        ),
                    )
                )
            rejections.append(
                EventAdapterRejection(
                    accession_number=amend_tx.accession_number or "UNKNOWN",
                    record_hash=amend_tx.record_hash,
                    reason=REJECTED_AMENDMENT_AMBIGUOUS,
                    details=(
                        f"Ambiguous amendment relationship: matches {len(same_accession_candidates)} candidate original filings in accession. "
                        f"Guessing avoided."
                    ),
                )
            )
        else:
            # Case C: Cross-accession amendment or no same-accession original found.
            # Do NOT guess or use DATE_OF_ORIG_SUB heuristics to supersede originals in different accessions.
            # Exclude the uncertain amendment transaction from research events to prevent double-counting.
            excluded_hashes.add(amend_hash)
            rejections.append(
                EventAdapterRejection(
                    accession_number=amend_tx.accession_number or "UNKNOWN",
                    record_hash=amend_tx.record_hash,
                    reason=REJECTED_AMENDMENT_UNRESOLVED_ORIGINAL,
                    details=(
                        f"Unresolved cross-accession amendment: SEC bulk dataset lacks authoritative original accession link "
                        f"(date_of_orig_submission: '{amend_tx.date_of_orig_submission}'). "
                        f"Guessing avoided; original filings preserved."
                    ),
                )
            )

    for tx in transactions:
        key = tx.record_hash or id(tx)
        if key not in excluded_hashes:
            effective_txs.append(tx)

    return effective_txs, rejections


def prepare_event_study_inputs(
    database_url: str,
    transactions: List[NormalizedBulkTransaction],
    horizon_days: int = 1,
) -> EventAdapterResult:
    """
    Convert normalized insider transactions into event-study engine inputs.

    Data Quality & Safety rules:
    - Missing ticker -> REJECTED_MISSING_TICKER
    - Missing or invalid filing_date / transaction_date -> REJECTED_MISSING_DATE / REJECTED_INVALID_DATE
    - Missing market price on filing date -> REJECTED_MISSING_PRICE
    - Insufficient future observations for horizon_days -> REJECTED_INSUFFICIENT_OBSERVATIONS
    - Superseded amendments -> REJECTED_AMENDMENT_SUPERSEDED
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

        # 2. Date check (Point-In-Time safety: event_date is public filing_date)
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

        event_date = tx.filing_date.strip()

        # 3. Market price lookup for ticker
        if ticker not in price_cache:
            price_cache[ticker] = get_market_prices_for_ticker(database_url, ticker)

        prices = price_cache[ticker]

        if not prices or event_date not in prices:
            rejections.append(
                EventAdapterRejection(
                    accession_number=acc,
                    record_hash=rec_hash,
                    reason=REJECTION_MISSING_PRICE,
                    details=f"No market price found for {ticker} on filing date {event_date}.",
                )
            )
            continue

        event_price = prices[event_date]

        # 4. Insufficient future observations check
        future_dates = [d for d in sorted(prices.keys()) if d > event_date]
        if len(future_dates) < horizon_days:
            rejections.append(
                EventAdapterRejection(
                    accession_number=acc,
                    record_hash=rec_hash,
                    reason=REJECTION_INSUFFICIENT_OBSERVATIONS,
                    details=(
                        f"Insufficient price observations ({len(future_dates)}) after filing date {event_date} "
                        f"for horizon {horizon_days}."
                    ),
                )
            )
            continue

        # 5. Deterministic event_key
        event_key = f"{ticker}|{event_date}|{acc}|{rec_hash or 'nohash'}"

        valid_events.append(
            ResearchEventInput(
                event_key=event_key,
                symbol=ticker,
                event_date=event_date,
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
