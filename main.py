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


def run_historical_acquisition(
    start_period: str,
    end_period: str,
    batch_size: int = 5000,
    force: bool = False,
    reference_period: str | None = None,
) -> int:
    """
    Execute historical SEC dataset acquisition from start_period to end_period
    using temporary disk files and bounded streaming batches to prevent high memory usage.
    """
    import hashlib
    import os
    import tempfile
    import zipfile
    from archive import ArchiveError, ArchiveMetadata, get_archive_backend
    from config.environment import load_environment
    from data.acquisition_state import AcquisitionStateManager, get_latest_available_sec_period
    from data.sec_dataset_pipeline import (
        build_dataset_url,
        download_dataset_zip_to_file,
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
        store_provenance,
    )

    settings = load_environment()
    db_url = settings.database_url
    user_agent = settings.sec_user_agent

    archive_kwargs = {}
    if settings.sec_archive_bucket:
        archive_kwargs["bucket"] = settings.sec_archive_bucket
    if settings.sec_archive_endpoint_url:
        archive_kwargs["endpoint_url"] = settings.sec_archive_endpoint_url
    archive_kwargs["region_name"] = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "auto"

    archive_backend = get_archive_backend(
        backend_type=settings.sec_archive_backend,
        archive_path=settings.sec_archive_path,
        **archive_kwargs,
    )

    state_mgr = AcquisitionStateManager(db_url)
    period_range = state_mgr.parse_period_range(start_period, end_period)

    retention_years = getattr(settings, "sec_operational_retention_years", 3)

    # The retention reference must be explicit for a historical acquisition.
    #
    # Do NOT derive it from the current contents of Neon/R2 here.
    # A fresh database/archive may legitimately contain no authoritative
    # period yet, and deriving the reference from partially populated
    # historical data could incorrectly make an old quarter the retention
    # anchor.
    #
    # The caller/workflow must explicitly provide the authoritative SEC
    # reference period for the acquisition window.
    if not reference_period:
        raise ValueError(
            "reference_period is required for historical acquisition. "
            "Pass --reference-period using the authoritative SEC dataset "
            "period that should anchor the operational retention window."
        )

    retention_ref = AcquisitionStateManager.normalize_period(reference_period)

    periods_processed = 0
    periods_downloaded = 0
    total_parsed = 0
    total_inserted = 0
    total_duplicates = 0
    total_invalid = 0
    total_failures = 0

    print(f"Starting historical acquisition from {start_period} to {end_period} (batch_size={batch_size})...")

    for year, qtr, period_str in period_range:
        periods_processed += 1

        # Check resume state: skip completed periods unless force=True; retry failed/partial/unknown
        if not force and state_mgr.should_skip_period(period_str):
            print(f"Period {period_str}: Already completed. Skipping.")
            continue

        print(f"Processing period {period_str}...")

        # Create temporary file for working ZIP archive
        temp_fd, temp_zip_path = tempfile.mkstemp(suffix=".zip", prefix=f"sec_{period_str}_")
        os.close(temp_fd)

        try:
            dataset_url = build_dataset_url(year, qtr)

            # Step 1: Reuse existing intact archive or recover incomplete archive or download anew
            if archive_backend.exists(period_str):
                print(f"Period {period_str}: Found existing immutable archive. Reusing archive.")
                zip_bytes = archive_backend.get(period_str)
                with open(temp_zip_path, "wb") as f:
                    f.write(zip_bytes)
                saved_meta = archive_backend.metadata(period_str)
            else:
                # Check for partial / incomplete archive recovery.
                #
                # Storage errors MUST propagate. They must never be interpreted as
                # "incomplete data" and must never trigger deletion or a fresh SEC
                # download.
                if archive_backend.is_incomplete(period_str):
                    print(
                        f"Period {period_str}: Found incomplete archive. "
                        f"Attempting reconciliation."
                    )

                    try:
                        zip_bytes = archive_backend.get_incomplete_zip(period_str)

                        with open(temp_zip_path, "wb") as f:
                            f.write(zip_bytes)

                        if not zipfile.is_zipfile(temp_zip_path):
                            raise ValueError(
                                f"Incomplete archive ZIP for period {period_str} is invalid."
                            )

                        hasher = hashlib.sha256()
                        file_size = os.path.getsize(temp_zip_path)

                        with open(temp_zip_path, "rb") as f:
                            while chunk := f.read(1024 * 1024):
                                hasher.update(chunk)

                        zip_checksum = hasher.hexdigest()

                        archive_meta = ArchiveMetadata(
                            period=period_str,
                            source="SEC",
                            source_url=dataset_url,
                            sha256=zip_checksum,
                            validation_status="validated",
                            file_size_bytes=file_size,
                        )

                        saved_meta = archive_backend.put(
                            period=period_str,
                            content=temp_zip_path,
                            metadata=archive_meta,
                        )

                    except ArchiveError:
                        # Storage/auth/network failures are fatal.
                        # Never delete the orphan archive and never fall back to SEC.
                        raise

                    except (zipfile.BadZipFile, ValueError):
                        # Only an actually invalid ZIP may be treated as unrecoverable.
                        archive_backend.delete_incomplete_archive(period_str)

                # Download from SEC if temp ZIP is not available or not valid
                if not os.path.exists(temp_zip_path) or os.path.getsize(temp_zip_path) == 0 or not zipfile.is_zipfile(temp_zip_path):
                    download_dataset_zip_to_file(year, qtr, user_agent=user_agent, target_path=temp_zip_path)
                    periods_downloaded += 1

                # ZIP Validation
                if not zipfile.is_zipfile(temp_zip_path):
                    raise ValueError(f"Downloaded file for period {period_str} is not a valid ZIP archive.")

                # SHA-256 calculation
                hasher = hashlib.sha256()
                file_size = os.path.getsize(temp_zip_path)
                with open(temp_zip_path, "rb") as f:
                    while chunk := f.read(1024 * 1024):
                        hasher.update(chunk)
                zip_checksum = hasher.hexdigest()

                # Immutable Archive persistence
                archive_meta = ArchiveMetadata(
                    period=period_str,
                    source="SEC",
                    source_url=dataset_url,
                    sha256=zip_checksum,
                    validation_status="validated",
                    file_size_bytes=file_size,
                )
                saved_meta = archive_backend.put(
                    period=period_str,
                    content=temp_zip_path,
                    metadata=archive_meta,
                )

            # Dataset Provenance tracking
            store_provenance(
                db_url,
                record_type="dataset_period",
                record_id=period_str,
                source="SEC",
                source_reference=dataset_url,
                checksum=saved_meta.sha256,
                validation_status="validated",
            )

            within_retention = AcquisitionStateManager.is_within_operational_retention(
                period_str,
                reference_period=retention_ref,
                retention_years=retention_years,
            )

            # Normalized Ingestion
            p_parsed = 0
            p_invalid = 0
            p_inserted = 0
            p_duplicates = 0
            batch = []

            for raw_record in parse_dataset_zip(temp_zip_path, source_url=dataset_url):
                p_parsed += 1
                norm_rec = normalize_bulk_record(raw_record)
                val_res = validate_bulk_record(norm_rec)

                if val_res.is_valid:
                    if within_retention:
                        batch.append(norm_rec)
                else:
                    p_invalid += 1

                if within_retention and len(batch) >= batch_size:
                    b_ins, b_dup = store_bulk_insider_transactions(
                        db_url,
                        batch,
                        store_raw_payload=settings.sec_store_raw_payload,
                    )
                    p_inserted += b_ins
                    p_duplicates += b_dup
                    batch.clear()

            # Process final remaining batch for period if within retention window
            if within_retention and batch:
                b_ins, b_dup = store_bulk_insider_transactions(
                    db_url,
                    batch,
                    store_raw_payload=settings.sec_store_raw_payload,
                )
                p_inserted += b_ins
                p_duplicates += b_dup
                batch.clear()

            if not within_retention:
                print(f"Period {period_str}: Outside operational retention window ({retention_years} years relative to {retention_ref}). Archived in R2, skipped Neon transaction insertion.")

            # Mark COMPLETED only after normalized ingestion completes successfully
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

        except SECDatasetDownloadError as exc:
            print(f"Period {period_str}: Download failed ({exc}). Marking FAILED.")
            total_failures += 1
            state_mgr.record_period_completion(
                period_str, 0, 0, 0, 0, 1, status="FAILED"
            )

        except Exception as exc:
            print(f"Period {period_str}: Ingestion error ({exc}). Marking FAILED.")
            total_failures += 1
            state_mgr.record_period_completion(
                period=period_str,
                records_parsed=0,
                records_inserted=0,
                duplicates_count=0,
                invalid_count=0,
                failures_count=1,
                status="FAILED",
            )

        finally:
            # Always clean up temporary ZIP file from disk
            if os.path.exists(temp_zip_path):
                try:
                    os.remove(temp_zip_path)
                except OSError:
                    pass

    # Calculate final database stats
    final_count = count_records(db_url, "insider_transactions")

    earliest_date = None
    latest_date = None

    tx_date_sql = (
        "SELECT MIN(transaction_date), MAX(transaction_date) FROM insider_transactions WHERE transaction_date IS NOT NULL"
        if is_postgresql_url(db_url) else
        "SELECT MIN(transaction_date), MAX(transaction_date) FROM insider_transactions WHERE transaction_date IS NOT NULL AND transaction_date != ''"
    )
    with connect(db_url) as conn:
        cursor = conn.execute(tx_date_sql)
        row = cursor.fetchone()
        if row:
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

    if total_failures > 0:
        print(f"Historical acquisition finished with {total_failures} period failure(s). Returning non-zero exit code.", file=sys.stderr)
        return 1

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

    if len(sys.argv) >= 2 and sys.argv[1] in ("storage_audit", "storage-audit"):
        from scripts.storage_audit import main as audit_main
        sys.argv.pop(1)
        return audit_main()

    if len(sys.argv) >= 2 and sys.argv[1] in ("storage_maintenance", "storage-maintenance"):
        from scripts.storage_maintenance import main as maint_main
        sys.argv.pop(1)
        return maint_main()

    if len(sys.argv) >= 2 and sys.argv[1] in ("historical", "historical_acquisition"):
        # Argument parsing for historical acquisition
        import argparse
        parser = argparse.ArgumentParser(prog="historical acquisition")
        parser.add_argument("cmd", nargs="*")
        parser.add_argument("--start", default="2006-Q1", help="Start period (e.g. 2006-Q1)")
        parser.add_argument("--end", default="2026-Q2", help="End period (e.g. 2026-Q2)")
        parser.add_argument("--batch-size", type=int, default=5000, help="Batch size for database insertion")
        parser.add_argument("--force", action="store_true", help="Force re-processing of completed periods")
        parser.add_argument(
            "--reference-period",
            default=None,
            help=(
                "Authoritative SEC dataset period used as the operational "
                "retention reference (required for historical acquisition). "
                "Example: 2026-Q2"
            ),
        )
        args = parser.parse_args()
        return run_historical_acquisition(args.start, args.end, batch_size=args.batch_size, force=args.force, reference_period=args.reference_period)

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
