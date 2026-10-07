"""
Corporate Actions Acquisition Workflow CLI for Insider Trade Bot.

Executes controlled, provider-neutral historical corporate-actions acquisition (splits and dividends).
Flows strictly through Provider -> Acquisition Service -> Loader -> Ingestion -> Storage -> Provenance.
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
)
from data.corporate_actions_acquisition import (
    CorporateActionsAcquisitionReport,
    CorporateActionsAcquisitionService,
)
from data.providers.fmp_corporate_actions import FMPCorporateActionsProvider


ISO_DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_iso_date(date_str: str, param_name: str) -> str:
    """Validate strict YYYY-MM-DD ISO format and calendar validity."""
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
        description="Acquire historical corporate actions (splits/dividends) from configured providers."
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="fmp",
        help="Corporate actions provider (default: fmp).",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        required=True,
        help="Comma-separated list of target ticker symbols (e.g., AAPL,MSFT). Required.",
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


def run_corporate_actions_acquisition(
    args: argparse.Namespace,
) -> CorporateActionsAcquisitionReport:
    settings = load_environment()
    db_url = args.database_url.strip() or settings.database_url

    provider_name = str(args.provider).strip().lower()
    if provider_name != "fmp":
        raise ValueError(f"Unknown or unsupported corporate-actions provider: '{provider_name}'.")

    # Validate FMP key
    fmp_key = settings.fmp_api_key
    if not fmp_key:
        raise EnvironmentConfigurationError("FMP_API_KEY is required for corporate actions acquisition.")

    # Validate symbols
    raw_symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    requested_symbols = tuple(dict.fromkeys(raw_symbols))

    if not requested_symbols:
        raise ValueError("An explicit non-empty --symbols argument is required. Mass acquisition is prohibited.")

    # Resolve date range
    start_date: str | None = None
    end_date: str | None = None

    if args.start_date:
        start_date = validate_iso_date(args.start_date, "start_date")
    if args.end_date:
        end_date = validate_iso_date(args.end_date, "end_date")

    if start_date and end_date and start_date > end_date:
        raise ValueError(f"start_date ({start_date}) cannot be later than end_date ({end_date}).")

    provider = FMPCorporateActionsProvider(
        api_key=fmp_key,
        base_url=settings.fmp_base_url,
    )

    service = CorporateActionsAcquisitionService(provider)
    return service.acquire_corporate_actions(
        database_url=db_url,
        symbols=requested_symbols,
        start_date=start_date,
        end_date=end_date,
    )


def format_ca_report_dict(
    report: CorporateActionsAcquisitionReport,
) -> dict[str, Any]:
    symbol_outcomes = [
        {
            "symbol": res.symbol,
            "status": res.status,
            "splits_received": res.splits_received,
            "dividends_received": res.dividends_received,
            "records_inserted": res.records_inserted,
            "duplicates_count": res.duplicates_count,
            "rejected_count": res.rejected_count,
            "provider_failures": res.provider_failures,
            "error_message": res.error_message,
        }
        for res in report.symbol_results
    ]

    return {
        "provider": report.source,
        "date_range": {
            "start_date": report.requested_start_date,
            "end_date": report.requested_end_date,
        },
        "requested_symbols": list(report.requested_symbols),
        "successful_symbols": list(report.successful_symbols),
        "failed_symbols": list(report.failed_symbols),
        "summary": {
            "splits_received": report.splits_received,
            "dividends_received": report.dividends_received,
            "records_inserted": report.records_inserted,
            "records_duplicate": report.records_duplicate,
            "records_rejected": report.records_rejected,
            "records_failed": report.records_failed,
            "provider_request_failures": report.provider_request_failures,
        },
        "provider_failures": list(report.provider_failures),
        "per_symbol_outcomes": symbol_outcomes,
    }


def main(args: list[str] | None = None) -> None:
    parsed_args = parse_args(args)
    try:
        report = run_corporate_actions_acquisition(parsed_args)
        report_data = format_ca_report_dict(report)

        if parsed_args.json:
            print(json.dumps(report_data, indent=2))
        else:
            print("=" * 60)
            print("CORPORATE ACTIONS ACQUISITION REPORT")
            print("=" * 60)
            print(f"Provider:             {report_data['provider']}")
            print(f"Requested Date Range: {report_data['date_range']['start_date'] or 'ALL'} to {report_data['date_range']['end_date'] or 'ALL'}")
            print(f"Requested Symbols:    {', '.join(report_data['requested_symbols'])}")
            print(f"Successful Symbols:   {', '.join(report_data['successful_symbols'])}")
            print(f"Failed Symbols:       {', '.join(report_data['failed_symbols'] or ['None'])}")
            print("-" * 60)
            summary = report_data['summary']
            print("SUMMARY:")
            print(f"  Splits Received:        {summary['splits_received']}")
            print(f"  Dividends Received:     {summary['dividends_received']}")
            print(f"  Records Inserted:       {summary['records_inserted']}")
            print(f"  Duplicates:             {summary['records_duplicate']}")
            print(f"  Rejections:             {summary['records_rejected']}")
            print(f"  Failures:               {summary['records_failed']}")
            print(f"  Provider Failures:      {summary['provider_request_failures']}")
            print("=" * 60)

    except (ValueError, EnvironmentConfigurationError) as exc:
        print(f"Corporate Actions Acquisition Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
