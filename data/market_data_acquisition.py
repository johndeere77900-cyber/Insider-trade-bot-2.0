"""
Market-Data Acquisition Service for Insider Trade Bot.

Orchestrates market-data retrieval from external providers through the standard
loader/normalization/validation/storage pipeline.

Safety boundaries:
- Bypasses neither validation nor normalization.
- Does not write directly to the database (delegates to MarketDataLoader/pipeline).
- Never calls research or trading modules.
- Supports symbol batching based on provider capabilities.
- Supports deterministic single-pass fallback for failed batch requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from data.market_data_client import MarketDataProvider
from data.market_data_loader import (
    MarketDataLoadError,
    RecordLoadOutcome,
    load_market_prices_detailed,
)


@dataclass(frozen=True)
class SymbolAcquisitionResult:
    """Summary result for a single symbol."""

    symbol: str
    status: str  # 'SUCCESS', 'FAILED', 'PARTIAL'
    requested: bool
    records_received: int
    records_inserted: int
    duplicates_count: int
    rejected_count: int
    conflicts_count: int
    record_failures: int
    provider_request_failures: int
    error_message: str | None = None

    @property
    def failed_count(self) -> int:
        """Compatibility alias for record failures."""
        return self.record_failures


@dataclass(frozen=True)
class MarketDataAcquisitionReport:
    """Overall acquisition process report."""

    requested_symbols: tuple[str, ...]
    requested_start_date: str | None
    requested_end_date: str | None
    successful_symbols: tuple[str, ...]
    failed_symbols: tuple[str, ...]
    records_received: int
    records_inserted: int
    records_duplicate: int
    records_rejected: int
    records_failed: int  # record-level failures
    conflicts: int
    provider_request_failures: int  # provider/network request failures
    source: str
    provider_failures: tuple[dict[str, Any], ...]
    symbol_results: tuple[SymbolAcquisitionResult, ...]


class MarketDataAcquisitionService:
    """
    Acquisition orchestrator for market data.
    """

    def __init__(self, provider: MarketDataProvider) -> None:
        self.provider = provider

    def acquire_historical_data(
        self,
        database_url: str,
        symbols: Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
        source_reference: str | None = None,
    ) -> MarketDataAcquisitionReport:
        """
        Acquire historical market data for symbols across start_date..end_date.
        Separates Provider Fetch (Phase A) from Record Ingestion (Phase B).
        """
        requested_symbols = tuple(
            dict.fromkeys(
                str(s).strip().upper()
                for s in symbols
                if str(s).strip()
            )
        )

        provider_source = self.provider.source

        if not requested_symbols:
            return MarketDataAcquisitionReport(
                requested_symbols=(),
                requested_start_date=start_date,
                requested_end_date=end_date,
                successful_symbols=(),
                failed_symbols=(),
                records_received=0,
                records_inserted=0,
                records_duplicate=0,
                records_rejected=0,
                records_failed=0,
                conflicts=0,
                provider_request_failures=0,
                source=provider_source,
                provider_failures=(),
                symbol_results=(),
            )

        # Per-symbol counters
        symbol_counts: dict[str, dict[str, Any]] = {
            sym: {
                "received": 0,
                "inserted": 0,
                "duplicate": 0,
                "rejected": 0,
                "conflict": 0,
                "record_failures": 0,
                "provider_request_failures": 0,
                "errors": [],
            }
            for sym in requested_symbols
        }

        unmapped_key = "_UNMAPPED_"
        symbol_counts[unmapped_key] = {
            "received": 0,
            "inserted": 0,
            "duplicate": 0,
            "rejected": 0,
            "conflict": 0,
            "record_failures": 0,
            "provider_request_failures": 0,
            "errors": [],
        }

        provider_failures: list[dict[str, Any]] = []
        total_provider_request_failures = 0

        # Strategy decision
        if self.provider.supports_batch and len(requested_symbols) > 1:
            batch_response: list[dict[str, Any]] | None = None

            # Phase A — Batch Provider Fetch
            try:
                batch_response = self.provider.get_historical_prices_batch(
                    symbols=requested_symbols,
                    start_date=start_date,
                    end_date=end_date,
                )
            except Exception as exc:
                err_msg = str(exc)
                total_provider_request_failures += 1
                provider_failures.append({"type": "batch", "symbols": requested_symbols, "error": err_msg})
                batch_response = None

            # Phase B — Batch Ingestion (if provider fetch succeeded)
            if batch_response is not None:
                try:
                    outcomes = load_market_prices_detailed(
                        database_url,
                        batch_response,
                        source=provider_source,
                        source_reference=source_reference or "batch_request",
                    )
                    self._accumulate_outcomes(outcomes, requested_symbols, symbol_counts)
                except Exception as exc:
                    err_msg = f"Batch ingestion storage error: {exc}"
                    rec_cnt = len(batch_response) if isinstance(batch_response, list) else 1
                    # Attribute unmapped batch storage failure to requested symbols evenly or unmapped
                    symbol_counts[unmapped_key]["received"] += rec_cnt
                    symbol_counts[unmapped_key]["record_failures"] += rec_cnt
                    symbol_counts[unmapped_key]["errors"].append(err_msg)
            else:
                # Fallback to individual requests per symbol ONLY when batch provider fetch failed
                for sym in requested_symbols:
                    sym_resp: list[dict[str, Any]] | None = None

                    # Phase A — Individual Provider Fetch
                    try:
                        sym_resp = self.provider.get_historical_prices(
                            symbol=sym,
                            start_date=start_date,
                            end_date=end_date,
                        )
                    except Exception as exc:
                        err_msg = str(exc)
                        total_provider_request_failures += 1
                        symbol_counts[sym]["provider_request_failures"] += 1
                        symbol_counts[sym]["errors"].append(err_msg)
                        provider_failures.append({"type": "individual", "symbol": sym, "error": err_msg})
                        sym_resp = None

                    # Phase B — Individual Ingestion
                    if sym_resp is not None:
                        try:
                            outcomes = load_market_prices_detailed(
                                database_url,
                                sym_resp,
                                source=provider_source,
                                source_reference=source_reference or f"request:{sym}",
                            )
                            self._accumulate_outcomes(outcomes, requested_symbols, symbol_counts, fallback_symbol=sym)
                        except Exception as exc:
                            err_msg = f"Storage error for {sym}: {exc}"
                            rec_cnt = len(sym_resp) if isinstance(sym_resp, list) else 1
                            symbol_counts[sym]["received"] += rec_cnt
                            symbol_counts[sym]["record_failures"] += rec_cnt
                            symbol_counts[sym]["errors"].append(err_msg)
        else:
            # Direct per-symbol processing
            for sym in requested_symbols:
                sym_resp = None

                # Phase A — Provider Fetch
                try:
                    sym_resp = self.provider.get_historical_prices(
                        symbol=sym,
                        start_date=start_date,
                        end_date=end_date,
                    )
                except Exception as exc:
                    err_msg = str(exc)
                    total_provider_request_failures += 1
                    symbol_counts[sym]["provider_request_failures"] += 1
                    symbol_counts[sym]["errors"].append(err_msg)
                    provider_failures.append({"type": "individual", "symbol": sym, "error": err_msg})
                    sym_resp = None

                # Phase B — Record Ingestion
                if sym_resp is not None:
                    try:
                        outcomes = load_market_prices_detailed(
                            database_url,
                            sym_resp,
                            source=provider_source,
                            source_reference=source_reference or f"request:{sym}",
                        )
                        self._accumulate_outcomes(outcomes, requested_symbols, symbol_counts, fallback_symbol=sym)
                    except Exception as exc:
                        err_msg = f"Storage error for {sym}: {exc}"
                        rec_cnt = len(sym_resp) if isinstance(sym_resp, list) else 1
                        symbol_counts[sym]["received"] += rec_cnt
                        symbol_counts[sym]["record_failures"] += rec_cnt
                        symbol_counts[sym]["errors"].append(err_msg)

        # Calculate totals
        total_received = sum(c["received"] for c in symbol_counts.values())
        total_inserted = sum(c["inserted"] for c in symbol_counts.values())
        total_duplicate = sum(c["duplicate"] for c in symbol_counts.values())
        total_rejected = sum(c["rejected"] for c in symbol_counts.values())
        total_conflicts = sum(c["conflict"] for c in symbol_counts.values())
        total_record_failures = sum(c["record_failures"] for c in symbol_counts.values())

        # Enforce global accounting invariant
        expected_total = (
            total_inserted
            + total_duplicate
            + total_rejected
            + total_conflicts
            + total_record_failures
        )
        if total_received != expected_total:
            raise MarketDataLoadError(
                f"Market-data acquisition accounting invariant violated: received {total_received} != {expected_total}"
            )

        # Enforce per-symbol invariant
        for sym_k, c in symbol_counts.items():
            sym_expected = (
                c["inserted"]
                + c["duplicate"]
                + c["rejected"]
                + c["conflict"]
                + c["record_failures"]
            )
            if c["received"] != sym_expected:
                raise MarketDataLoadError(
                    f"Market-data acquisition per-symbol invariant violated for {sym_k}: received {c['received']} != {sym_expected}"
                )

        successful_symbols: list[str] = []
        failed_symbols: list[str] = []
        symbol_results: list[SymbolAcquisitionResult] = []

        for sym in requested_symbols:
            c = symbol_counts[sym]
            has_record_failures = c["record_failures"] > 0 or c["conflict"] > 0
            has_req_failures = c["provider_request_failures"] > 0

            if (c["inserted"] > 0 or c["duplicate"] > 0 or c["received"] > 0) and not has_record_failures and not has_req_failures:
                successful_symbols.append(sym)
                status = "SUCCESS"
            elif c["inserted"] > 0 or c["duplicate"] > 0:
                status = "PARTIAL"
                failed_symbols.append(sym)
            else:
                status = "FAILED"
                failed_symbols.append(sym)

            err_str = "; ".join(c["errors"]) if c["errors"] else None

            symbol_results.append(
                SymbolAcquisitionResult(
                    symbol=sym,
                    status=status,
                    requested=True,
                    records_received=c["received"],
                    records_inserted=c["inserted"],
                    duplicates_count=c["duplicate"],
                    rejected_count=c["rejected"],
                    conflicts_count=c["conflict"],
                    record_failures=c["record_failures"],
                    provider_request_failures=c["provider_request_failures"],
                    error_message=err_str,
                )
            )

        # Unmapped symbol results if any existed
        unmapped_c = symbol_counts[unmapped_key]
        if unmapped_c["received"] > 0 or unmapped_c["rejected"] > 0 or unmapped_c["record_failures"] > 0:
            err_str = "; ".join(unmapped_c["errors"]) if unmapped_c["errors"] else "Unidentified or unmapped provider symbol"
            symbol_results.append(
                SymbolAcquisitionResult(
                    symbol="UNMAPPED",
                    status="FAILED",
                    requested=False,
                    records_received=unmapped_c["received"],
                    records_inserted=unmapped_c["inserted"],
                    duplicates_count=unmapped_c["duplicate"],
                    rejected_count=unmapped_c["rejected"],
                    conflicts_count=unmapped_c["conflict"],
                    record_failures=unmapped_c["record_failures"],
                    provider_request_failures=0,
                    error_message=err_str,
                )
            )

        return MarketDataAcquisitionReport(
            requested_symbols=requested_symbols,
            requested_start_date=start_date,
            requested_end_date=end_date,
            successful_symbols=tuple(successful_symbols),
            failed_symbols=tuple(failed_symbols),
            records_received=total_received,
            records_inserted=total_inserted,
            records_duplicate=total_duplicate,
            records_rejected=total_rejected,
            records_failed=total_record_failures,
            conflicts=total_conflicts,
            provider_request_failures=total_provider_request_failures,
            source=provider_source,
            provider_failures=tuple(provider_failures),
            symbol_results=tuple(symbol_results),
        )

    def _accumulate_outcomes(
        self,
        outcomes: Sequence[RecordLoadOutcome],
        requested_symbols: tuple[str, ...],
        symbol_counts: dict[str, dict[str, Any]],
        fallback_symbol: str | None = None,
    ) -> None:
        for outcome in outcomes:
            rec_sym = outcome.symbol or fallback_symbol
            if rec_sym and rec_sym in symbol_counts:
                target_key = rec_sym
            elif rec_sym is None and len(requested_symbols) == 1:
                target_key = requested_symbols[0]
            else:
                target_key = "_UNMAPPED_"

            c = symbol_counts[target_key]
            c["received"] += 1

            if target_key == "_UNMAPPED_" and outcome.outcome != "REJECTED":
                c["rejected"] += 1
                if outcome.reason:
                    c["errors"].append(outcome.reason)
                continue

            if outcome.outcome == "INSERTED":
                c["inserted"] += 1
            elif outcome.outcome == "DUPLICATE":
                c["duplicate"] += 1
            elif outcome.outcome == "REJECTED":
                c["rejected"] += 1
            elif outcome.outcome == "CONFLICT":
                c["conflict"] += 1
            elif outcome.outcome == "FAILED":
                c["record_failures"] += 1

            if outcome.reason:
                c["errors"].append(outcome.reason)
