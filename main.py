from __future__ import annotations

import sys

from application.agent_bootstrap import AgentBootstrap
from application.configuration import ApplicationConfiguration
from config.environment import (
    EnvironmentConfigurationError,
    load_environment,
)
from config.environment_validator import (
    EnvironmentValidationError,
    EnvironmentValidator,
)
from core.logging_config import configure_logging


def run_historical_acquisition(start_period: str, end_period: str) -> int:
    """
    Execute historical SEC dataset acquisition from start_period to end_period.
    """
    import os
    from config.environment import load_environment
    from data.acquisition_state import AcquisitionStateManager
    from data.sec_dataset_pipeline import (
        download_dataset_zip,
        normalize_bulk_record,
        parse_dataset_zip,
        validate_bulk_record,
        SECDatasetDownloadError,
    )
    from database.connection import connect
    from storage.repository import (
        count_records,
        is_postgresql_url,
        store_bulk_insider_transactions,
    )

    settings = load_environment()
    db_url = settings.database_url
    user_agent = settings.sec_user_agent or "InsiderTradeBot/2.0 contact@example.com"

    state_mgr = AcquisitionStateManager(db_url)
    period_range = state_mgr.parse_period_range(start_period, end_period)

    periods_processed = 0
    periods_downloaded = 0
    total_parsed = 0
    total_inserted = 0
    total_duplicates = 0
    total_invalid = 0
    total_failures = 0

    print(f"Starting historical acquisition from {start_period} to {end_period}...")

    for year, qtr, period_str in period_range:
        periods_processed += 1
        if state_mgr.is_period_completed(period_str):
            print(f"Period {period_str}: Already completed. Skipping.")
            continue

        print(f"Processing period {period_str}...")

        try:
            zip_bytes = download_dataset_zip(year, qtr, user_agent=user_agent)
            periods_downloaded += 1
        except SECDatasetDownloadError as exc:
            print(f"Period {period_str}: Download failed ({exc}). Marking failed.")
            total_failures += 1
            state_mgr.record_period_completion(
                period_str, 0, 0, 0, 0, 1, status="FAILED"
            )
            continue
        except Exception as exc:
            print(f"Period {period_str}: Download failed with unexpected error ({exc}).")
            total_failures += 1
            state_mgr.record_period_completion(
                period_str, 0, 0, 0, 0, 1, status="FAILED"
            )
            continue

        valid_records = []
        p_parsed = 0
        p_invalid = 0

        for raw_record in parse_dataset_zip(zip_bytes):
            p_parsed += 1
            norm_rec = normalize_bulk_record(raw_record)
            val_res = validate_bulk_record(norm_rec)

            if val_res.is_valid:
                valid_records.append(norm_rec)
            else:
                p_invalid += 1

        p_inserted, p_duplicates = store_bulk_insider_transactions(
            db_url, valid_records
        )

        state_mgr.record_period_completion(
            period=period_str,
            records_parsed=p_parsed,
            records_inserted=p_inserted,
            duplicates_count=p_duplicates,
            invalid_count=p_invalid,
            failures_count=0,
            status="COMPLETED",
        )

        total_parsed += p_parsed
        total_inserted += p_inserted
        total_duplicates += p_duplicates
        total_invalid += p_invalid

        print(
            f"Period {period_str}: Parsed {p_parsed}, Inserted {p_inserted}, "
            f"Duplicates {p_duplicates}, Invalid {p_invalid}"
        )

    # Calculate final database stats
    final_count = count_records(db_url, "insider_transactions")

    earliest_date = None
    latest_date = None

    with connect(db_url) as conn:
        cursor = conn.execute(
            "SELECT MIN(transaction_date), MAX(transaction_date) FROM insider_transactions WHERE transaction_date IS NOT NULL AND transaction_date != ''"
        )
        row = cursor.fetchone()
        if row:
            if is_postgresql_url(db_url):
                earliest_date, latest_date = row[0], row[1]
            else:
                earliest_date, latest_date = row[0], row[1]

    print("\n================ HISTORICAL ACQUISITION SUMMARY ================")
    print(f"Periods processed: {periods_processed}")
    print(f"Periods downloaded: {periods_downloaded}")
    print(f"Records parsed: {total_parsed}")
    print(f"Records inserted: {total_inserted}")
    print(f"Duplicates: {total_duplicates}")
    print(f"Invalid records: {total_invalid}")
    print(f"Failures: {total_failures}")
    print(f"Final database count: {final_count}")
    print(f"Earliest transaction date: {earliest_date}")
    print(f"Latest transaction date: {latest_date}")
    print("================================================================")

    return 0


def main() -> int:
    """
    Main executable entry point for Insider Trade Bot 2.0.

    Startup order:
        1. Load environment configuration.
        2. Validate configuration.
        3. Configure application logging.
        4. Assemble and start the application runtime.

    Live trading remains controlled by the application's execution
    and safety layers and is disabled by default.
    """

    if len(sys.argv) >= 2 and sys.argv[1] in ("historical", "historical_acquisition"):
        # Argument parsing for historical acquisition
        import argparse
        parser = argparse.ArgumentParser(prog="historical acquisition")
        parser.add_argument("cmd", nargs="*")
        parser.add_argument("--start", default="2006-Q1", help="Start period (e.g. 2006-Q1)")
        parser.add_argument("--end", default="2026-Q1", help="End period (e.g. 2026-Q1)")
        args = parser.parse_args()
        return run_historical_acquisition(args.start, args.end)

    try:
        settings = load_environment()

        EnvironmentValidator().require_valid(settings)

        configure_logging(
            level=settings.log_level,
            logs_directory=settings.log_directory,
        )

        configuration = ApplicationConfiguration(
            environment=settings.environment,
            paper_trading_enabled=settings.paper_trading,
            live_trading_enabled=settings.live_trading,
            telegram_enabled=settings.telegram_enabled,
            historical_data_available=False,
            strict_mode=settings.strict_mode,
        )

        agent = AgentBootstrap(
            configuration=configuration,
        ).build()

        result = agent.entrypoint.start()

    except (
        EnvironmentConfigurationError,
        EnvironmentValidationError,
        ValueError,
    ) as exc:
        print(
            f"Startup configuration error: {exc}",
            file=sys.stderr,
        )
        return 1

    except Exception as exc:
        print(
            f"Agent startup error: {exc}",
            file=sys.stderr,
        )
        return 1

    if not result.success:
        print(
            f"Agent startup failed: {result.message}",
            file=sys.stderr,
        )
        return 1

    print("Insider Trade Bot 2.0 started successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
