"""
Market Data Acquisition Workflow CLI for Insider Trade Bot.

Executes controlled, provider-neutral historical market-data acquisition.
Flows strictly through Provider -> Acquisition Service -> Loader -> Normalization -> Validation -> Storage -> Provenance.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from typing import Any

from config.environment import (
    EnvironmentConfigurationError,
    load_environment,
    validate_market_data_config,
)
from data.market_data_acquisition import (
    MarketDataAcquisitionReport,
    MarketDataAcquisitionService,
)
from data.market_data_provider_factory import get_market_data_provider
from research.ticker_universe import get_ticker_universe


ISO_DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_iso_date(date_str: str, param_name: str) -> str:
    """
    Validate strict YYYY-MM-DD ISO format and calendar validity.
    """
    cleaned = str(date_str).strip()
    if not ISO_DATE_REGEX.match(cleaned):
        raise ValueError(
            f"{param_name} '{date_str}' must be in YYYY-MM-DD format."
        )
    try:
        dt = datetime.datetime.strptime(cleaned, "%Y-%m-%d").date()
        return dt.strftime("%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(
            f"{param_name} '{date_str}' is an invalid calendar date."
        ) from exc


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Acquire historical market data from configured providers."
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="fmp",
        help="Market data provider (default: fmp).",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="",
        help="Comma-separated list of ticker symbols (e.g., AAPL,MSFT).",
    )
    parser.add_argument(
        "--limit-symbols",
        type=int,
        default=None,
        help="Limit acquisition to the first N symbols from ticker universe.",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="",
        help="Acquisition start date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="",
        help="Acquisition end date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--preset",
        type=str,
        default="",
        choices=["", "smoke"],
        help="Supported date range preset (e.g., 'smoke' for 2006-01-03 to 2006-01-10).",
    )
    parser.add_argument(
        "--allow-future",
        action="store_true",
        help="Allow requested dates in the future.",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default="",
        help="Override database connection URL.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output acquisition report formatted as JSON.",
    )
    return parser.parse_args(args)


def run_acquisition(args: argparse.Namespace) -> tuple[MarketDataAcquisitionReport, int]:
    settings = load_environment()
    db_url = args.database_url.strip() or settings.database_url

    provider_name = str(args.provider).strip().lower()

    # Validate provider configuration before attempting acquisition
    validate_market_data_config(settings, provider=provider_name)

    # Resolve date range
    start_date: str | None = None
    end_date: str | None = None

    if args.preset == "smoke":
        start_date = "2006-01-03"
        end_date = "2006-01-10"
    else:
        if args.start_date:
            start_date = validate_iso_date(args.start_date, "start_date")
        if args.end_date:
            end_date = validate_iso_date(args.end_date, "end_date")

    if not start_date or not end_date:
        raise ValueError(
            "An explicit --start-date and --end-date or supported --preset is required. "
            "Never request 'all history'."
        )

    if start_date > end_date:
        raise ValueError(
            f"start_date ({start_date}) cannot be later than end_date ({end_date})."
        )

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    if not args.allow_future and end_date > today_str:
        raise ValueError(
            f"end_date ({end_date}) cannot be in the future (today is {today_str}) "
            "unless --allow-future is specified."
        )

    # Determine ticker universe
    if args.symbols and args.symbols.strip():
        raw_syms = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
        requested_symbols = tuple(dict.fromkeys(raw_syms))
        unique_ticker_count = len(requested_symbols)
    else:
        universe_res = get_ticker_universe(
            database_url=db_url,
            start_date=start_date,
            end_date=end_date,
        )
        requested_symbols = universe_res.tickers
        unique_ticker_count = universe_res.unique_ticker_count

    if args.limit_symbols is not None:
        if args.limit_symbols <= 0:
            raise ValueError("--limit-symbols must be greater than zero.")
        requested_symbols = requested_symbols[: args.limit_symbols]

    if not requested_symbols:
        raise ValueError("No valid target symbols resolved for market data acquisition.")

    # Initialize provider via factory
    provider = get_market_data_provider(
        provider_name=provider_name,
        settings=settings,
    )

    # Execute acquisition through standard pipeline
    service = MarketDataAcquisitionService(provider)
    report = service.acquire_historical_data(
        database_url=db_url,
        symbols=requested_symbols,
        start_date=start_date,
        end_date=end_date,
        source_reference=f"cli_acquisition:{provider_name}:{start_date}:{end_date}",
    )

    return report, unique_ticker_count


def format_report_dict(
    report: MarketDataAcquisitionReport,
    unique_ticker_count: int,
) -> dict[str, Any]:
    symbol_outcomes = [
        {
            "symbol": res.symbol,
            "status": res.status,
            "records_received": res.records_received,
            "records_inserted": res.records_inserted,
            "records_duplicate": res.duplicates_count,
            "records_rejected": res.rejected_count,
            "conflicts": res.conflicts_count,
            "record_failures": res.record_failures,
            "provider_request_failures": res.provider_request_failures,
            "error_message": res.error_message,
        }
        for res in report.symbol_results
    ]

    return {
        "provider": report.source,
        "unique_ticker_count": unique_ticker_count,
        "date_range": {
            "start_date": report.requested_start_date,
            "end_date": report.requested_end_date,
        },
        "requested_symbols": list(report.requested_symbols),
        "successful_symbols": list(report.successful_symbols),
        "failed_symbols": list(report.failed_symbols),
        "summary": {
            "records_received": report.records_received,
            "records_inserted": report.records_inserted,
            "records_duplicate": report.records_duplicate,
            "records_rejected": report.records_rejected,
            "records_failed": report.records_failed,
            "conflicts": report.conflicts,
            "provider_request_failures": report.provider_request_failures,
        },
        "coverage_summary": {
            "requested_symbol_count": len(report.requested_symbols),
            "successful_symbol_count": len(report.successful_symbols),
            "failed_symbol_count": len(report.failed_symbols),
        },
        "provider_failures": list(report.provider_failures),
        "per_symbol_outcomes": symbol_outcomes,
    }


def main(args: list[str] | None = None) -> None:
    parsed_args = parse_args(args)
    try:
        report, unique_ticker_count = run_acquisition(parsed_args)
        report_data = format_report_dict(report, unique_ticker_count)

        if parsed_args.json:
            print(json.dumps(report_data, indent=2))
        else:
            print("=" * 60)
            print("MARKET DATA ACQUISITION REPORT")
            print("=" * 60)
            print(f"Provider:                  {report_data['provider']}")
            print(f"Requested Date Range:      {report_data['date_range']['start_date']} to {report_data['date_range']['end_date']}")
            print(f"Unique Tickers in DB:      {report_data['unique_ticker_count']}")
            print(f"Requested Symbols Count:   {len(report_data['requested_symbols'])}")
            print(f"Successful Symbols Count:  {len(report_data['successful_symbols'])}")
            print(f"Failed Symbols Count:      {len(report_data['failed_symbols'])}")
            print("-" * 60)
            print("RECORD ACCOUNTING SUMMARY:")
            summary = report_data['summary']
            print(f"  Records Received:        {summary['records_received']}")
            print(f"  Records Inserted:        {summary['records_inserted']}")
            print(f"  Records Duplicate:       {summary['records_duplicate']}")
            print(f"  Records Rejected:        {summary['records_rejected']}")
            print(f"  Records Failed:          {summary['records_failed']}")
            print(f"  Conflicts:               {summary['conflicts']}")
            print(f"  Provider Request Errors: {summary['provider_request_failures']}")
            print("=" * 60)

    except (ValueError, EnvironmentConfigurationError) as exc:
        print(f"Acquisition Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
