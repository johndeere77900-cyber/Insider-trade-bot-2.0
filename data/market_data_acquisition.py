"""
Market-Data Acquisition Service for Insider Trade Bot.

Orchestrates market-data retrieval from external providers through the standard
loader/normalization/validation/storage pipeline.

Safety boundaries:
- Bypasses neither validation nor normalization.
- Does not write directly to the database (delegates to MarketDataLoader/pipeline).
- Never calls research or trading modules.
- Supports symbol batching based on provider capabilities.
- Supports deterministic retry for specified symbol and date ranges.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from data.market_data_client import MarketDataClientError, MarketDataProvider
from data.market_data_loader import MarketDataLoadError, load_market_prices
from storage.repository import MarketDataConflictError, count_records


@dataclass(frozen=True)
class SymbolAcquisitionResult:
    """Summary result for a single symbol or batch retrieval."""

    symbol: str
    status: str  # 'SUCCESS', 'FAILED', 'PARTIAL'
    records_received: int
    records_inserted: int
    duplicates_count: int
    rejected_count: int
    error_message: str | None = None


@dataclass(frozen=True)
class MarketDataAcquisitionReport:
    """Overall acquisition process report."""

    requested_symbols: tuple[str, ...]
    successful_symbols: tuple[str, ...]
    failed_symbols: tuple[str, ...]
    records_received: int
    records_inserted: int
    duplicates: int
    rejected_records: int
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
        """
        normalized_symbols = tuple(
            dict.fromkeys(
                str(s).strip().upper()
                for s in symbols
                if str(s).strip()
            )
        )

        if not normalized_symbols:
            return MarketDataAcquisitionReport(
                requested_symbols=(),
                successful_symbols=(),
                failed_symbols=(),
                records_received=0,
                records_inserted=0,
                duplicates=0,
                rejected_records=0,
                provider_failures=(),
                symbol_results=(),
            )

        provider_source = self.provider.source
        successful_symbols: list[str] = []
        failed_symbols: list[str] = []
        provider_failures: list[dict[str, Any]] = []
        symbol_results: list[SymbolAcquisitionResult] = []

        total_received = 0
        total_inserted = 0
        total_duplicates = 0
        total_rejected = 0

        # Decide strategy: batch or single symbol
        if self.provider.supports_batch and len(normalized_symbols) > 1:
            try:
                response = self.provider.get_historical_prices_batch(
                    symbols=normalized_symbols,
                    start_date=start_date,
                    end_date=end_date,
                )

                initial_count = count_records(database_url, "market_prices")
                hashes = load_market_prices(
                    database_url,
                    response,
                    source=provider_source,
                    source_reference=source_reference,
                )
                final_count = count_records(database_url, "market_prices")

                inserted = final_count - initial_count
                received = len(hashes)
                duplicates = max(0, received - inserted)

                total_received += received
                total_inserted += inserted
                total_duplicates += duplicates

                successful_symbols.extend(normalized_symbols)

                for sym in normalized_symbols:
                    symbol_results.append(
                        SymbolAcquisitionResult(
                            symbol=sym,
                            status="SUCCESS",
                            records_received=received,
                            records_inserted=inserted,
                            duplicates_count=duplicates,
                            rejected_count=0,
                        )
                    )

            except (
                MarketDataClientError,
                MarketDataLoadError,
                MarketDataConflictError,
                ValueError,
            ) as exc:
                failed_symbols.extend(normalized_symbols)
                err_msg = str(exc)
                provider_failures.append(
                    {
                        "symbols": normalized_symbols,
                        "error": err_msg,
                    }
                )
                for sym in normalized_symbols:
                    symbol_results.append(
                        SymbolAcquisitionResult(
                            symbol=sym,
                            status="FAILED",
                            records_received=0,
                            records_inserted=0,
                            duplicates_count=0,
                            rejected_count=0,
                            error_message=err_msg,
                        )
                    )
        else:
            # Per-symbol processing
            for sym in normalized_symbols:
                try:
                    response = self.provider.get_historical_prices(
                        symbol=sym,
                        start_date=start_date,
                        end_date=end_date,
                    )

                    initial_count = count_records(database_url, "market_prices")
                    hashes = load_market_prices(
                        database_url,
                        response,
                        source=provider_source,
                        source_reference=source_reference or f"request:{sym}",
                    )
                    final_count = count_records(database_url, "market_prices")

                    inserted = final_count - initial_count
                    received = len(hashes)
                    duplicates = max(0, received - inserted)

                    total_received += received
                    total_inserted += inserted
                    total_duplicates += duplicates

                    successful_symbols.append(sym)
                    symbol_results.append(
                        SymbolAcquisitionResult(
                            symbol=sym,
                            status="SUCCESS",
                            records_received=received,
                            records_inserted=inserted,
                            duplicates_count=duplicates,
                            rejected_count=0,
                        )
                    )

                except (
                    MarketDataClientError,
                    MarketDataLoadError,
                    MarketDataConflictError,
                    ValueError,
                ) as exc:
                    failed_symbols.append(sym)
                    err_msg = str(exc)
                    total_rejected += 1
                    provider_failures.append(
                        {
                            "symbol": sym,
                            "error": err_msg,
                        }
                    )
                    symbol_results.append(
                        SymbolAcquisitionResult(
                            symbol=sym,
                            status="FAILED",
                            records_received=0,
                            records_inserted=0,
                            duplicates_count=0,
                            rejected_count=1,
                            error_message=err_msg,
                        )
                    )

        return MarketDataAcquisitionReport(
            requested_symbols=normalized_symbols,
            successful_symbols=tuple(successful_symbols),
            failed_symbols=tuple(failed_symbols),
            records_received=total_received,
            records_inserted=total_inserted,
            duplicates=total_duplicates,
            rejected_records=total_rejected,
            provider_failures=tuple(provider_failures),
            symbol_results=tuple(symbol_results),
        )
