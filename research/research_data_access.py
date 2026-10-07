"""
Read-only data-access layer for research modules.

Provides query functions for normalized insider transactions and market prices
from operational storage without duplicating data or embedding SQL in research logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from data.acquisition_state import AcquisitionStateManager
from data.sec_dataset_pipeline import (
    NormalizedBulkTransaction,
    normalize_bulk_record,
    parse_dataset_zip,
    validate_bulk_record,
)
from database.connection import connect, is_postgresql_url


class PeriodNotFoundError(Exception):
    """Raised when a requested SEC dataset period is missing from both Neon and R2 archive."""


class DatasetIntegrityError(Exception):
    """Raised when a dataset's stored records fail completeness verification."""


@dataclass(frozen=True)
class DatasetCoverage:
    """Read-only coverage summary for a dataset in database storage."""

    dataset_type: str
    period: str
    expected_records: Optional[int]
    actual_records: int
    first_date: Optional[str]
    last_date: Optional[str]
    complete: bool


@dataclass(frozen=True)
class MarketDataCoverageReport:
    """Read-only coverage report for a symbol's historical market data."""

    symbol: str
    first_available_date: Optional[str]
    last_available_date: Optional[str]
    observation_count: int
    requested_start_date: Optional[str]
    requested_end_date: Optional[str]
    missing_requested_range: bool
    starts_before_available: bool
    ends_after_available: bool
    is_range_covered_boundary_level: bool
    has_sufficient_future_observations: bool
    missing_requested_price_field_count: int


def verify_dataset_coverage(
    *,
    database_url: str,
    dataset_type: str,
    period: str,
) -> DatasetCoverage:
    """
    Verify actual rows and metadata in storage for the requested dataset and period.

    Uses parameterized SQL and compares:
    - ingestion_state status
    - expected record count
    - actual record count
    - first date and last date

    Raises DatasetIntegrityError if dataset storage contract is violated.
    """
    norm_type = str(dataset_type).strip().lower()
    norm_period = AcquisitionStateManager.normalize_period(period)
    is_pg = is_postgresql_url(database_url)
    param_placeholder = "%s" if is_pg else "?"

    with connect(database_url) as conn:
        cursor = conn.execute(
            f"SELECT status, records_inserted, records_parsed FROM ingestion_state WHERE period = {param_placeholder}",
            (norm_period,),
        )
        state_row = cursor.fetchone()

        status = state_row["status"] if state_row else None
        expected_records = None
        if state_row:
            if state_row["records_inserted"] is not None:
                expected_records = int(state_row["records_inserted"])
            elif state_row["records_parsed"] is not None:
                expected_records = int(state_row["records_parsed"])

        if norm_type in {"sec", "insider_transactions", "sec_historical"}:
            f_start, f_end = _quarter_date_range(norm_period)
            cursor = conn.execute(
                f"""
                SELECT COUNT(*) as actual_count, MIN(filing_date) as min_date, MAX(filing_date) as max_date
                FROM insider_transactions
                WHERE filing_date >= {param_placeholder} AND filing_date <= {param_placeholder}
                """,
                (f_start, f_end),
            )
            row = cursor.fetchone()
            actual_records = int(row["actual_count"]) if row else 0
            first_date = row["min_date"] if row else None
            last_date = row["max_date"] if row else None

        elif norm_type == "market_prices":
            cursor = conn.execute(
                f"""
                SELECT COUNT(*) as actual_count, MIN(price_date) as min_date, MAX(price_date) as max_date
                FROM market_prices
                WHERE price_date >= {param_placeholder} AND price_date <= {param_placeholder}
                """,
                _quarter_date_range(norm_period),
            )
            row = cursor.fetchone()
            actual_records = int(row["actual_count"]) if row else 0
            first_date = row["min_date"] if row else None
            last_date = row["max_date"] if row else None
        else:
            raise ValueError(f"Unsupported dataset_type '{dataset_type}' for verification.")

    is_complete = (
        status == "COMPLETED"
        and actual_records > 0
        and (expected_records is None or actual_records >= expected_records)
    )

    if not is_complete:
        raise DatasetIntegrityError(
            f"Dataset coverage verification failed for {norm_type} period '{norm_period}': "
            f"status='{status}', expected={expected_records}, actual={actual_records}."
        )

    return DatasetCoverage(
        dataset_type=norm_type,
        period=norm_period,
        expected_records=expected_records,
        actual_records=actual_records,
        first_date=first_date,
        last_date=last_date,
        complete=True,
    )


def _quarter_date_range(period: str) -> tuple[str, str]:
    norm = AcquisitionStateManager.normalize_period(period)
    year, qtr = int(norm[:4]), int(norm[-1])
    if qtr == 1:
        return f"{year}-01-01", f"{year}-03-31"
    elif qtr == 2:
        return f"{year}-04-01", f"{year}-06-30"
    elif qtr == 3:
        return f"{year}-07-01", f"{year}-09-30"
    elif qtr == 4:
        return f"{year}-10-01", f"{year}-12-31"
    raise ValueError(f"Invalid quarter in period '{period}'")


def resolve_period_storage_location(
    database_url: str,
    archive_backend: Any,
    period: str,
    reference_period: Optional[str] = None,
    retention_years: int = 3,
) -> str:
    """
    Determine whether a requested SEC quarter is:
    - 'NEON': period state in ingestion_state is 'COMPLETED' AND inside operational retention window
    - 'R2': quarterly source archive exists in R2 / archive backend
    - 'MISSING': missing from both Neon and R2 archive
    """
    norm_period = AcquisitionStateManager.normalize_period(period)

    within_retention = AcquisitionStateManager.is_within_operational_retention(
        norm_period,
        reference_period=reference_period,
        retention_years=retention_years,
    )

    is_neon_completed = False
    if within_retention:
        state_mgr = AcquisitionStateManager(database_url)
        status = state_mgr.get_period_status(norm_period)
        if status == "COMPLETED":
            is_neon_completed = True

    if is_neon_completed:
        return "NEON"

    if archive_backend is not None:
        if archive_backend.exists(norm_period):
            return "R2"

    return "MISSING"


def query_insider_transactions(
    database_url: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    filing_start_date: Optional[str] = None,
    filing_end_date: Optional[str] = None,
    tickers: Optional[Union[str, List[str]]] = None,
    issuer_ciks: Optional[Union[str, List[str]]] = None,
    transaction_codes: Optional[Union[str, List[str]]] = None,
    acquired_disposed: Optional[str] = None,
    ownership_types: Optional[Union[str, List[str]]] = None,
    source: Optional[str] = None,
    accession_numbers: Optional[Union[str, List[str]]] = None,
    limit: Optional[int] = None,
) -> List[NormalizedBulkTransaction]:
    """
    Retrieve normalized insider transaction records from the operational database.

    Filters records dynamically using parameterized SQL queries.
    Returns domain objects (`NormalizedBulkTransaction`).
    """
    is_pg = is_postgresql_url(database_url)
    param_placeholder = "%s" if is_pg else "?"

    query = """
        SELECT
            accession_number,
            issuer_cik,
            issuer_name,
            ticker,
            insider_name,
            insider_cik,
            transaction_date,
            filing_date,
            form_type,
            transaction_code,
            security_title,
            shares,
            price,
            transaction_type,
            acquired_disposed,
            ownership_type,
            ownership_nature,
            source,
            source_url,
            is_amendment,
            date_of_orig_submission,
            raw_payload,
            record_hash
        FROM insider_transactions
        WHERE 1 = 1
    """

    params: List[Any] = []

    if start_date:
        query += f" AND transaction_date >= {param_placeholder}"
        params.append(start_date)

    if end_date:
        query += f" AND transaction_date <= {param_placeholder}"
        params.append(end_date)

    if filing_start_date:
        query += f" AND filing_date >= {param_placeholder}"
        params.append(filing_start_date)

    if filing_end_date:
        query += f" AND filing_date <= {param_placeholder}"
        params.append(filing_end_date)

    if tickers:
        t_list = [tickers] if isinstance(tickers, str) else list(tickers)
        if t_list:
            placeholders = ", ".join([param_placeholder] * len(t_list))
            query += f" AND UPPER(ticker) IN ({placeholders})"
            params.extend([t.upper() for t in t_list])

    if issuer_ciks:
        c_list = [issuer_ciks] if isinstance(issuer_ciks, str) else list(issuer_ciks)
        if c_list:
            placeholders = ", ".join([param_placeholder] * len(c_list))
            query += f" AND issuer_cik IN ({placeholders})"
            params.extend([c.zfill(10) if c.isdigit() else c for c in c_list])

    if transaction_codes:
        tc_list = [transaction_codes] if isinstance(transaction_codes, str) else list(transaction_codes)
        if tc_list:
            placeholders = ", ".join([param_placeholder] * len(tc_list))
            query += f" AND UPPER(transaction_code) IN ({placeholders})"
            params.extend([code.upper() for code in tc_list])

    if acquired_disposed:
        query += f" AND UPPER(acquired_disposed) = {param_placeholder}"
        params.append(acquired_disposed.strip().upper())

    if ownership_types:
        ot_list = [ownership_types] if isinstance(ownership_types, str) else list(ownership_types)
        if ot_list:
            placeholders = ", ".join([param_placeholder] * len(ot_list))
            query += f" AND UPPER(ownership_type) IN ({placeholders})"
            params.extend([ot.upper() for ot in ot_list])

    if source:
        query += f" AND source = {param_placeholder}"
        params.append(source)

    if accession_numbers:
        acc_list = [accession_numbers] if isinstance(accession_numbers, str) else list(accession_numbers)
        if acc_list:
            placeholders = ", ".join([param_placeholder] * len(acc_list))
            query += f" AND accession_number IN ({placeholders})"
            params.extend(acc_list)

    query += " ORDER BY transaction_date ASC, filing_date ASC"

    if limit is not None and limit > 0:
        query += f" LIMIT {param_placeholder}"
        params.append(limit)

    records: List[NormalizedBulkTransaction] = []

    with connect(database_url) as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

        for row in rows:
            raw_payload_data = {}
            if row["raw_payload"]:
                try:
                    raw_payload_data = json.loads(row["raw_payload"])
                except Exception:
                    raw_payload_data = {}

            acq_disp = row["acquired_disposed"] or raw_payload_data.get("transaction", {}).get("TRANS_ACQUIRED_DISP_CD")
            form_t = row["form_type"] or "4"
            is_amend_val = bool(row["is_amendment"]) if row["is_amendment"] is not None else ("/A" in form_t)
            orig_sub_date = row["date_of_orig_submission"]

            records.append(
                NormalizedBulkTransaction(
                    accession_number=row["accession_number"] or "",
                    issuer_cik=row["issuer_cik"] or "",
                    issuer_name=row["issuer_name"],
                    ticker=row["ticker"],
                    reporting_owner_name=row["insider_name"],
                    reporting_owner_cik=row["insider_cik"],
                    transaction_date=row["transaction_date"],
                    filing_date=row["filing_date"],
                    transaction_code=row["transaction_code"],
                    security_title=row["security_title"],
                    shares=float(row["shares"]) if row["shares"] is not None else None,
                    price_per_share=float(row["price"]) if row["price"] is not None else None,
                    transaction_type=row["transaction_type"],
                    acquired_disposed=acq_disp,
                    ownership_type=row["ownership_type"],
                    ownership_nature=row["ownership_nature"],
                    source_url=row["source_url"] or "",
                    is_amendment=is_amend_val,
                    date_of_orig_submission=orig_sub_date,
                    raw_payload=raw_payload_data,
                    source=row["source"] or "SEC",
                    record_hash=row["record_hash"],
                    form_type=form_t,
                )
            )

    return records


def get_historical_transactions(
    database_url: str,
    archive_backend: Any,
    start_period: str,
    end_period: str,
    *,
    tickers: Optional[Union[str, List[str]]] = None,
    transaction_codes: Optional[Union[str, List[str]]] = None,
    acquired_disposed: Optional[str] = None,
    ownership_types: Optional[Union[str, List[str]]] = None,
    limit: Optional[int] = None,
    reference_period: Optional[str] = None,
    retention_years: int = 3,
) -> List[NormalizedBulkTransaction]:
    """
    Retrieve historical SEC transactions across a range of periods [start_period, end_period].
    """
    period_tuples = AcquisitionStateManager.parse_period_range(start_period, end_period)
    periods = [p[2] for p in period_tuples]

    location_map = {}
    missing_periods = []
    for period in periods:
        loc = resolve_period_storage_location(
            database_url,
            archive_backend,
            period,
            reference_period=reference_period,
            retention_years=retention_years,
        )
        location_map[period] = loc
        if loc == "MISSING":
            missing_periods.append(period)

    if missing_periods:
        raise PeriodNotFoundError(
            f"Requested SEC period(s) {missing_periods} missing from both Neon database and R2 archive."
        )

    all_records: List[NormalizedBulkTransaction] = []

    t_set = set(t.upper() for t in ([tickers] if isinstance(tickers, str) else (tickers or [])))
    tc_set = set(c.upper() for c in ([transaction_codes] if isinstance(transaction_codes, str) else (transaction_codes or [])))
    ad_val = acquired_disposed.strip().upper() if acquired_disposed else None
    ot_set = set(o.upper() for o in ([ownership_types] if isinstance(ownership_types, str) else (ownership_types or [])))

    for period in periods:
        loc = location_map[period]
        f_start, f_end = _quarter_date_range(period)

        if loc == "NEON":
            period_records = query_insider_transactions(
                database_url,
                filing_start_date=f_start,
                filing_end_date=f_end,
                tickers=tickers,
                transaction_codes=transaction_codes,
                acquired_disposed=acquired_disposed,
                ownership_types=ownership_types,
            )
            all_records.extend(period_records)

        elif loc == "R2":
            zip_bytes = archive_backend.get(period)
            for raw_rec in parse_dataset_zip(zip_bytes):
                norm_tx = normalize_bulk_record(raw_rec)
                val_res = validate_bulk_record(norm_tx)
                if not val_res.is_valid:
                    continue

                if t_set and (not norm_tx.ticker or norm_tx.ticker.upper() not in t_set):
                    continue
                if tc_set and (not norm_tx.transaction_code or norm_tx.transaction_code.upper() not in tc_set):
                    continue
                if ad_val and (not norm_tx.acquired_disposed or norm_tx.acquired_disposed.upper() != ad_val):
                    continue
                if ot_set and (not norm_tx.ownership_type or norm_tx.ownership_type.upper() not in ot_set):
                    continue

                all_records.append(norm_tx)

    all_records.sort(key=lambda x: (x.transaction_date or "", x.filing_date or "", x.accession_number or ""))

    if limit is not None and limit > 0:
        return all_records[:limit]

    return all_records


def get_market_prices_for_ticker(
    database_url: str,
    ticker: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    use_adjusted_close: bool = False,
) -> Dict[str, float]:
    """
    Retrieve price records for a ticker symbol from market_prices table as a date -> price mapping.

    Strict Series Isolation:
    - If use_adjusted_close is True, ONLY non-NULL adjusted_close values are returned (no fallback to close).
    - If use_adjusted_close is False, ONLY non-NULL raw close values are returned (no fallback to adjusted_close).
    - Symbol is normalized. Results are ordered chronologically by price_date ASC.
    - No external provider or SEC downloader is contacted.
    """
    if not ticker or not ticker.strip():
        return {}

    norm_ticker = ticker.strip().upper()
    is_pg = is_postgresql_url(database_url)
    param_placeholder = "%s" if is_pg else "?"

    query = f"""
        SELECT price_date, close, adjusted_close
        FROM market_prices
        WHERE UPPER(symbol) = {param_placeholder}
    """
    params: List[Any] = [norm_ticker]

    if start_date:
        query += f" AND price_date >= {param_placeholder}"
        params.append(start_date.strip())

    if end_date:
        query += f" AND price_date <= {param_placeholder}"
        params.append(end_date.strip())

    query += " ORDER BY price_date ASC"

    prices: Dict[str, float] = {}

    with connect(database_url) as conn:
        cursor = conn.execute(query, params)
        rows = cursor.fetchall()
        for row in rows:
            if use_adjusted_close:
                price_val = row["adjusted_close"]
            else:
                price_val = row["close"]

            if price_val is not None:
                prices[row["price_date"]] = float(price_val)

    return prices


def check_market_data_coverage(
    database_url: str,
    symbol: str,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    required_horizon_days: int = 0,
    use_adjusted_close: bool = False,
) -> MarketDataCoverageReport:
    """
    Determine whether market data exists for a symbol across a date range.

    Read-only helper that does not download missing data automatically and does not pretend
    weekends or market holidays are automatic errors.
    """
    norm_symbol = str(symbol).strip().upper() if symbol else ""
    if not norm_symbol:
        return MarketDataCoverageReport(
            symbol="",
            first_available_date=None,
            last_available_date=None,
            observation_count=0,
            requested_start_date=start_date,
            requested_end_date=end_date,
            missing_requested_range=True,
            starts_before_available=False,
            ends_after_available=False,
            is_range_covered_boundary_level=False,
            has_sufficient_future_observations=False,
            missing_requested_price_field_count=0,
        )

    # Query all raw rows for symbol in DB to inspect missing field counts
    is_pg = is_postgresql_url(database_url)
    param_placeholder = "%s" if is_pg else "?"
    query = f"""
        SELECT price_date, close, adjusted_close
        FROM market_prices
        WHERE UPPER(symbol) = {param_placeholder}
    """
    params: List[Any] = [norm_symbol]
    if start_date:
        query += f" AND price_date >= {param_placeholder}"
        params.append(start_date.strip())
    if end_date:
        query += f" AND price_date <= {param_placeholder}"
        params.append(end_date.strip())
    query += " ORDER BY price_date ASC"

    all_rows = []
    with connect(database_url) as conn:
        cursor = conn.execute(query, params)
        all_rows = cursor.fetchall()

    if not all_rows:
        return MarketDataCoverageReport(
            symbol=norm_symbol,
            first_available_date=None,
            last_available_date=None,
            observation_count=0,
            requested_start_date=start_date,
            requested_end_date=end_date,
            missing_requested_range=True if (start_date or end_date) else False,
            starts_before_available=True if start_date else False,
            ends_after_available=True if end_date else False,
            is_range_covered_boundary_level=False,
            has_sufficient_future_observations=False,
            missing_requested_price_field_count=0,
        )

    available_dates = [r["price_date"] for r in all_rows]
    first_avail = available_dates[0]
    last_avail = available_dates[-1]

    # Count missing requested price field across available dates
    missing_field_count = 0
    valid_series_dates = []
    for r in all_rows:
        val = r["adjusted_close"] if use_adjusted_close else r["close"]
        if val is None:
            missing_field_count += 1
        else:
            valid_series_dates.append(r["price_date"])

    obs_count = len(valid_series_dates)

    starts_before = False
    ends_after = False

    if start_date and first_avail > start_date:
        starts_before = True
    if end_date and last_avail < end_date:
        ends_after = True

    missing_requested_range = starts_before or ends_after or (missing_field_count > 0)
    boundary_covered = not starts_before and not ends_after and obs_count > 0

    if start_date:
        future_obs = [d for d in valid_series_dates if d > start_date]
        sufficient_future = len(future_obs) >= required_horizon_days
    else:
        sufficient_future = obs_count >= required_horizon_days

    return MarketDataCoverageReport(
        symbol=norm_symbol,
        first_available_date=first_avail,
        last_available_date=last_avail,
        observation_count=obs_count,
        requested_start_date=start_date,
        requested_end_date=end_date,
        missing_requested_range=missing_requested_range,
        starts_before_available=starts_before,
        ends_after_available=ends_after,
        is_range_covered_boundary_level=boundary_covered,
        has_sufficient_future_observations=sufficient_future,
        missing_requested_price_field_count=missing_field_count,
    )
