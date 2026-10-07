"""
Corporate Actions Acquisition Service for Insider Trade Bot.

Orchestrates corporate-action retrieval from external providers through the standard
loader/ingestion/validation/storage/provenance pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence
from urllib.error import HTTPError, URLError

from data.corporate_actions_client import CorporateActionsClientError
from data.corporate_actions_loader import load_corporate_actions_detailed
from data.providers.fmp_corporate_actions import FMPCorporateActionsProvider


@dataclass(frozen=True)
class SymbolCorporateActionsResult:
    """Summary result for a single symbol's corporate actions acquisition."""

    symbol: str
    status: str  # 'SUCCESS', 'FAILED', 'PARTIAL'
    splits_received: int
    dividends_received: int
    records_inserted: int
    duplicates_count: int
    conflicts_count: int
    rejected_count: int
    record_failures: int
    provider_failures: int
    error_message: str | None = None


@dataclass(frozen=True)
class CorporateActionsAcquisitionReport:
    """Overall corporate-actions acquisition process report."""

    requested_symbols: tuple[str, ...]
    requested_start_date: str | None
    requested_end_date: str | None
    successful_symbols: tuple[str, ...]
    failed_symbols: tuple[str, ...]
    splits_received: int
    dividends_received: int
    records_inserted: int
    records_duplicate: int
    records_conflict: int
    records_rejected: int
    records_failed: int
    provider_request_failures: int
    source: str
    provider_failures: tuple[dict[str, Any], ...]
    symbol_results: tuple[SymbolCorporateActionsResult, ...]


class CorporateActionsAcquisitionService:
    """
    Acquisition orchestrator for corporate actions (splits and dividends).
    """

    def __init__(self, provider: FMPCorporateActionsProvider) -> None:
        self.provider = provider

    def acquire_corporate_actions(
        self,
        database_url: str,
        symbols: Sequence[str],
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> CorporateActionsAcquisitionReport:
        """
        Acquire historical stock splits and dividends for requested symbols.
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
            return CorporateActionsAcquisitionReport(
                requested_symbols=(),
                requested_start_date=start_date,
                requested_end_date=end_date,
                successful_symbols=(),
                failed_symbols=(),
                splits_received=0,
                dividends_received=0,
                records_inserted=0,
                records_duplicate=0,
                records_conflict=0,
                records_rejected=0,
                records_failed=0,
                provider_request_failures=0,
                source=provider_source,
                provider_failures=(),
                symbol_results=(),
            )

        total_splits = 0
        total_dividends = 0
        total_inserted = 0
        total_duplicate = 0
        total_conflict = 0
        total_rejected = 0
        total_failed = 0
        total_provider_failures = 0

        provider_failures_list: list[dict[str, Any]] = []
        symbol_results: list[SymbolCorporateActionsResult] = []
        successful_symbols: list[str] = []
        failed_symbols: list[str] = []

        for sym in requested_symbols:
            sym_splits = 0
            sym_dividends = 0
            sym_inserted = 0
            sym_duplicate = 0
            sym_conflict = 0
            sym_rejected = 0
            sym_failed = 0
            sym_provider_fail = 0
            sym_errors: list[str] = []

            source_ref = f"fmp_corporate_actions:{sym}:{start_date or 'ALL'}:{end_date or 'ALL'}"

            # 1. Fetch splits (provider errors ONLY)
            split_records: list[dict[str, Any]] | None = None
            try:
                split_records = self.provider.get_splits(
                    symbol=sym,
                    start_date=start_date,
                    end_date=end_date,
                )
                sym_splits = len(split_records) if split_records else 0
            except (CorporateActionsClientError, TimeoutError, URLError, HTTPError, OSError) as exc:
                err_msg = f"Splits provider error: {exc}"
                sym_errors.append(err_msg)
                sym_provider_fail += 1
                provider_failures_list.append(
                    {
                        "symbol": sym,
                        "action": "splits",
                        "error": str(exc),
                    }
                )
                split_records = None

            # Ingest splits (storage/processing errors MUST NOT become provider failures)
            if split_records:
                try:
                    outcomes = load_corporate_actions_detailed(
                        database_url,
                        split_records,
                        source=provider_source,
                        source_reference=source_ref,
                    )
                    for o in outcomes:
                        if o.outcome == "INSERTED":
                            sym_inserted += 1
                        elif o.outcome == "DUPLICATE":
                            sym_duplicate += 1
                        elif o.outcome == "CONFLICT":
                            sym_conflict += 1
                        elif o.outcome == "REJECTED":
                            sym_rejected += 1
                        elif o.outcome == "FAILED":
                            sym_failed += 1
                except Exception as exc:
                    sym_failed += len(split_records)
                    sym_errors.append(f"Splits ingestion error: {exc}")

            # 2. Fetch dividends (provider errors ONLY)
            div_records: list[dict[str, Any]] | None = None
            try:
                div_records = self.provider.get_dividends(
                    symbol=sym,
                    start_date=start_date,
                    end_date=end_date,
                )
                sym_dividends = len(div_records) if div_records else 0
            except (CorporateActionsClientError, TimeoutError, URLError, HTTPError, OSError) as exc:
                err_msg = f"Dividends provider error: {exc}"
                sym_errors.append(err_msg)
                sym_provider_fail += 1
                provider_failures_list.append(
                    {
                        "symbol": sym,
                        "action": "dividends",
                        "error": str(exc),
                    }
                )
                div_records = None

            # Ingest dividends (storage/processing errors MUST NOT become provider failures)
            if div_records:
                try:
                    outcomes = load_corporate_actions_detailed(
                        database_url,
                        div_records,
                        source=provider_source,
                        source_reference=source_ref,
                    )
                    for o in outcomes:
                        if o.outcome == "INSERTED":
                            sym_inserted += 1
                        elif o.outcome == "DUPLICATE":
                            sym_duplicate += 1
                        elif o.outcome == "CONFLICT":
                            sym_conflict += 1
                        elif o.outcome == "REJECTED":
                            sym_rejected += 1
                        elif o.outcome == "FAILED":
                            sym_failed += 1
                except Exception as exc:
                    sym_failed += len(div_records)
                    sym_errors.append(f"Dividends ingestion error: {exc}")

            has_rec_failures = (
                sym_rejected > 0 or sym_failed > 0 or sym_conflict > 0
            )
            if sym_provider_fail == 0 and not has_rec_failures:
                status = "SUCCESS"
                successful_symbols.append(sym)
            elif sym_inserted > 0 or sym_duplicate > 0:
                status = "PARTIAL"
                failed_symbols.append(sym)
            else:
                status = "FAILED"
                failed_symbols.append(sym)

            err_str = "; ".join(sym_errors) if sym_errors else None

            symbol_results.append(
                SymbolCorporateActionsResult(
                    symbol=sym,
                    status=status,
                    splits_received=sym_splits,
                    dividends_received=sym_dividends,
                    records_inserted=sym_inserted,
                    duplicates_count=sym_duplicate,
                    conflicts_count=sym_conflict,
                    rejected_count=sym_rejected,
                    record_failures=sym_failed,
                    provider_failures=sym_provider_fail,
                    error_message=err_str,
                )
            )

            total_splits += sym_splits
            total_dividends += sym_dividends
            total_inserted += sym_inserted
            total_duplicate += sym_duplicate
            total_conflict += sym_conflict
            total_rejected += sym_rejected
            total_failed += sym_failed
            total_provider_failures += sym_provider_fail

        return CorporateActionsAcquisitionReport(
            requested_symbols=requested_symbols,
            requested_start_date=start_date,
            requested_end_date=end_date,
            successful_symbols=tuple(successful_symbols),
            failed_symbols=tuple(failed_symbols),
            splits_received=total_splits,
            dividends_received=total_dividends,
            records_inserted=total_inserted,
            records_duplicate=total_duplicate,
            records_conflict=total_conflict,
            records_rejected=total_rejected,
            records_failed=total_failed,
            provider_request_failures=total_provider_failures,
            source=provider_source,
            provider_failures=tuple(provider_failures_list),
            symbol_results=tuple(symbol_results),
        )
