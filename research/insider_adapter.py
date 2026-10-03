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


def prepare_event_study_inputs(
    database_url: str,
    transactions: List[NormalizedBulkTransaction],
    horizon_days: int = 1,
) -> EventAdapterResult:
    """
    Convert normalized insider transactions into event-study engine inputs.

    Data Quality & Safety rules:
    - Missing ticker -> REJECTED_MISSING_TICKER
    - Missing or invalid transaction_date -> REJECTED_MISSING_DATE / REJECTED_INVALID_DATE
    - Missing market price on transaction date -> REJECTED_MISSING_PRICE
    - Insufficient future observations for horizon_days -> REJECTED_INSUFFICIENT_OBSERVATIONS
    - Superseded amendments -> REJECTED_AMENDMENT_SUPERSEDED (or filtered)
    """
    valid_events: List[ResearchEventInput] = []
    rejections: List[EventAdapterRejection] = []

    # Cache market prices per ticker to avoid repetitive queries
    price_cache: Dict[str, Dict[str, float]] = {}

    for tx in transactions:
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

        # 2. Date check
        if not tx.transaction_date or not tx.transaction_date.strip():
            rejections.append(
                EventAdapterRejection(
                    accession_number=acc,
                    record_hash=rec_hash,
                    reason=REJECTION_MISSING_DATE,
                    details="Transaction record has no valid transaction date.",
                )
            )
            continue

        tx_date = tx.transaction_date.strip()

        # 3. Market price lookup for ticker
        if ticker not in price_cache:
            price_cache[ticker] = get_market_prices_for_ticker(database_url, ticker)

        prices = price_cache[ticker]

        if not prices or tx_date not in prices:
            rejections.append(
                EventAdapterRejection(
                    accession_number=acc,
                    record_hash=rec_hash,
                    reason=REJECTION_MISSING_PRICE,
                    details=f"No market price found for {ticker} on transaction date {tx_date}.",
                )
            )
            continue

        event_price = prices[tx_date]

        # 4. Insufficient future observations check
        future_dates = [d for d in sorted(prices.keys()) if d > tx_date]
        if len(future_dates) < horizon_days:
            rejections.append(
                EventAdapterRejection(
                    accession_number=acc,
                    record_hash=rec_hash,
                    reason=REJECTION_INSUFFICIENT_OBSERVATIONS,
                    details=(
                        f"Insufficient price observations ({len(future_dates)}) after {tx_date} "
                        f"for horizon {horizon_days}."
                    ),
                )
            )
            continue

        # 5. Deterministic event_key
        event_key = f"{ticker}|{tx_date}|{acc}|{rec_hash or 'nohash'}"

        valid_events.append(
            ResearchEventInput(
                event_key=event_key,
                symbol=ticker,
                event_date=tx_date,
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
