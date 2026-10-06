"""
Acquisition State and Resumption Manager for Historical SEC Ingestion.

Tracks completed periods (quarters), records summary statistics per period,
and enables idempotent, resumable execution across runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from database.connection import connect, initialize_database, is_postgresql_url
from storage.repository import _placeholder, _row_value, utc_now


def get_current_sec_period(reference_date: Optional[datetime] = None) -> str:
    """Return the SEC dataset period string ('YYYY-QX') corresponding to reference_date (or current UTC date)."""
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)
    qtr = (reference_date.month - 1) // 3 + 1
    return f"{reference_date.year}-Q{qtr}"


def get_latest_available_sec_period(
    database_url: Optional[str] = None,
    archive_backend: Any = None,
) -> str:
    """
    Determine the latest authoritative SEC dataset period.

    Uses only completed ingestion_state periods and complete archive periods.
    Never falls back to the current calendar quarter.
    Storage/database/archive errors must propagate instead of being treated
    as evidence that no data exists.
    """
    candidates: List[str] = []

    if database_url:
        state_mgr = AcquisitionStateManager(database_url)
        completed = state_mgr.get_completed_periods()
        if completed:
            candidates.extend(completed)

    if archive_backend is not None:
        archived = archive_backend.list()
        if archived:
            candidates.extend(archived)

    if candidates:
        candidates.sort()
        return candidates[-1]

    raise RuntimeError(
        "No authoritative SEC dataset period is available from completed "
        "ingestion state or archive backend."
    )


@dataclass
class PeriodStats:
    period: str
    status: str
    records_parsed: int
    records_inserted: int
    duplicates_count: int
    invalid_count: int
    failures_count: int
    completed_at: str


class AcquisitionStateManager:
    """Manages acquisition state in the ingestion_state database table."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        initialize_database(self.database_url)

    def get_period_status(self, period: str) -> Optional[str]:
        """Return the status of a given period (e.g. COMPLETED, FAILED, PARTIAL, None)."""
        norm_period = self.normalize_period(period)
        placeholder = _placeholder(self.database_url)

        query = f"""
            SELECT status FROM ingestion_state
            WHERE period = {placeholder}
        """

        with connect(self.database_url) as connection:
            cursor = connection.execute(query, (norm_period,))
            row = cursor.fetchone()

        if row is None:
            return None

        status = _row_value(row, "status")
        return str(status) if status else None

    def is_period_completed(self, period: str) -> bool:
        """Check if a quarter is marked as COMPLETED."""
        return self.get_period_status(period) == "COMPLETED"

    def should_skip_period(self, period: str) -> bool:
        """
        Skip if COMPLETED.
        Retry if FAILED, PARTIAL, or UNKNOWN (None).
        """
        status = self.get_period_status(period)
        return status == "COMPLETED"

    def record_period_completion(
        self,
        period: str,
        records_parsed: int,
        records_inserted: int,
        duplicates_count: int,
        invalid_count: int,
        failures_count: int,
        status: str = "COMPLETED",
    ) -> None:
        """Record or update a completed acquisition period."""
        norm_period = self.normalize_period(period)
        placeholder = _placeholder(self.database_url)
        now = utc_now()

        if is_postgresql_url(self.database_url):
            query = f"""
                INSERT INTO ingestion_state (
                    period, status, records_parsed, records_inserted,
                    duplicates_count, invalid_count, failures_count, completed_at
                )
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
                ON CONFLICT (period) DO UPDATE SET
                    status = EXCLUDED.status,
                    records_parsed = EXCLUDED.records_parsed,
                    records_inserted = EXCLUDED.records_inserted,
                    duplicates_count = EXCLUDED.duplicates_count,
                    invalid_count = EXCLUDED.invalid_count,
                    failures_count = EXCLUDED.failures_count,
                    completed_at = EXCLUDED.completed_at
            """
        else:
            query = f"""
                INSERT OR REPLACE INTO ingestion_state (
                    period, status, records_parsed, records_inserted,
                    duplicates_count, invalid_count, failures_count, completed_at
                )
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            """

        values = (
            norm_period,
            status,
            records_parsed,
            records_inserted,
            duplicates_count,
            invalid_count,
            failures_count,
            now,
        )

        with connect(self.database_url) as connection:
            connection.execute(query, values)
            connection.commit()

    def get_completed_periods(self) -> List[str]:
        """Return all completed periods in order."""
        query = "SELECT period FROM ingestion_state WHERE status = 'COMPLETED' ORDER BY period"
        with connect(self.database_url) as connection:
            cursor = connection.execute(query)
            rows = cursor.fetchall()

        return [str(_row_value(r, "period")) for r in rows]

    @staticmethod
    def normalize_period(period: str) -> str:
        """Normalize period string into 'YYYY-QX' format (e.g. '2006-Q1')."""
        cleaned = str(period).strip().upper().replace(" ", "")
        if "Q" in cleaned and "-" not in cleaned:
            # 2006Q1 -> 2006-Q1
            idx = cleaned.find("Q")
            return f"{cleaned[:idx]}-{cleaned[idx:]}"
        return cleaned

    @staticmethod
    def is_within_operational_retention(
        period: str,
        reference_period: Optional[str] = None,
        retention_years: int = 3,
        database_url: Optional[str] = None,
        archive_backend: Any = None,
    ) -> bool:
        """
        Determine if `period` falls within `retention_years` of `reference_period`.
        If `reference_period` is None, calculates the latest available SEC period via
        `get_latest_available_sec_period(database_url, archive_backend)`.

        Deterministic calculation based on SEC quarter indexes:
        diff_quarters = (ref_year * 4 + (ref_qtr - 1)) - (period_year * 4 + (period_qtr - 1))
        Returns True if 0 <= diff_quarters < retention_years * 4.
        """
        if retention_years <= 0:
            return False

        if reference_period is None:
            reference_period = get_latest_available_sec_period(
                database_url=database_url,
                archive_backend=archive_backend,
            )

        norm_period = AcquisitionStateManager.normalize_period(period)
        norm_ref = AcquisitionStateManager.normalize_period(reference_period)

        p_year, p_qtr = int(norm_period[:4]), int(norm_period[-1])
        r_year, r_qtr = int(norm_ref[:4]), int(norm_ref[-1])

        p_idx = p_year * 4 + (p_qtr - 1)
        r_idx = r_year * 4 + (r_qtr - 1)

        diff = r_idx - p_idx
        return 0 <= diff < retention_years * 4

    @staticmethod
    def parse_period_range(start_period: str, end_period: str) -> List[Tuple[int, int, str]]:
        """
        Generate a list of (year, quarter, period_str) tuples from start_period to end_period inclusive.
        e.g. ('2006-Q1', '2006-Q3') -> [(2006, 1, '2006-Q1'), (2006, 2, '2006-Q2'), (2006, 3, '2006-Q3')]
        """
        start_norm = AcquisitionStateManager.normalize_period(start_period)
        end_norm = AcquisitionStateManager.normalize_period(end_period)

        try:
            start_year, start_qtr = int(start_norm[:4]), int(start_norm[-1])
            end_year, end_qtr = int(end_norm[:4]), int(end_norm[-1])
        except (ValueError, IndexError) as exc:
            raise ValueError(f"Invalid period range format: '{start_period}' to '{end_period}'") from exc

        result = []
        curr_year, curr_qtr = start_year, start_qtr

        while (curr_year < end_year) or (curr_year == end_year and curr_qtr <= end_qtr):
            period_str = f"{curr_year}-Q{curr_qtr}"
            result.append((curr_year, curr_qtr, period_str))

            curr_qtr += 1
            if curr_qtr > 4:
                curr_qtr = 1
                curr_year += 1

        return result
