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
    Preserves both in operational storage, but selects only effective transactions for research.
    Does NOT collapse legitimate same-day non-amended transactions.

    Rules:
    - Case A (Deterministic Match - 1 candidate): Mark original transaction superseded, retain amendment as effective event.
    - Case B (Ambiguous Match - >1 candidates): Do not guess; exclude amendment and all candidate originals.
    - Case C (Unresolved Match - 0 candidates): Exclude amendment with unresolved original rejection.
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
        candidates: List[NormalizedBulkTransaction] = []
        amend_hash = amend_tx.record_hash or id(amend_tx)

        for orig_tx in originals:
            same_accession = bool(orig_tx.accession_number and orig_tx.accession_number == amend_tx.accession_number)
            matches_orig_sub_date = bool(
                amend_tx.date_of_orig_submission
                and orig_tx.filing_date == amend_tx.date_of_orig_submission
                and orig_tx.issuer_cik == amend_tx.issuer_cik
                and orig_tx.reporting_owner_cik == amend_tx.reporting_owner_cik
                and orig_tx.transaction_date == amend_tx.transaction_date
            )

            if same_accession or matches_orig_sub_date:
                candidates.append(orig_tx)

        if len(candidates) == 1:
            # Case A: Exactly 1 deterministic original candidate
            orig_tx = candidates[0]
            orig_hash = orig_tx.record_hash or id(orig_tx)
            excluded_hashes.add(orig_hash)
            rejections.append(
                EventAdapterRejection(
                    accession_number=orig_tx.accession_number or "UNKNOWN",
                    record_hash=orig_tx.record_hash,
                    reason=REJECTION_AMENDMENT_SUPERSEDED,
                    details=(
                        f"Original transaction superseded by explicit SEC amendment filing "
                        f"(Accession: {amend_tx.accession_number})."
                    ),
                )
            )
        elif len(candidates) > 1:
            # Case B: Ambiguous match (>1 candidates) -> Do not guess; exclude amendment and candidate originals
            excluded_hashes.add(amend_hash)
            for cand in candidates:
                cand_hash = cand.record_hash or id(cand)
                excluded_hashes.add(cand_hash)
                rejections.append(
                    EventAdapterRejection(
                        accession_number=cand.accession_number or "UNKNOWN",
                        record_hash=cand.record_hash,
                        reason=REJECTED_AMENDMENT_AMBIGUOUS,
                        details=(
                            f"Ambiguous original filing relationship: multiple candidates ({len(candidates)}) "
                            f"match amendment filing {amend_tx.accession_number}."
                        ),
                    )
                )
            rejections.append(
                EventAdapterRejection(
                    accession_number=amend_tx.accession_number or "UNKNOWN",
                    record_hash=amend_tx.record_hash,
                    reason=REJECTED_AMENDMENT_AMBIGUOUS,
                    details=(
                        f"Ambiguous amendment relationship: matches {len(candidates)} candidate original filings. "
                        f"Guessing avoided."
                    ),
                )
            )
        else:
            # Case C: Unresolved match (0 candidates) -> Amendment exists but original is missing in dataset
            excluded_hashes.add(amend_hash)
            rejections.append(
                EventAdapterRejection(
                    accession_number=amend_tx.accession_number or "UNKNOWN",
                    record_hash=amend_tx.record_hash,
                    reason=REJECTED_AMENDMENT_UNRESOLVED_ORIGINAL,
                    details=(
                        f"Unresolved amendment relationship: original filing referenced by date_of_orig_submission "
                        f"'{amend_tx.date_of_orig_submission}' was not found in operational dataset."
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
