"""
Integrity-checking layer for Insider Trade Bot.

Provides both record-level hash verification and database-level
integrity auditing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Any

from core.hashing import generate_record_hash
from database.connection import connect


@dataclass(frozen=True)
class IntegrityCheckResult:
    """Result of a single record-integrity check."""

    valid: bool
    expected_hash: str
    actual_hash: str


def check_record_integrity(
    *,
    record: Mapping[str, Any],
    expected_hash: str,
) -> IntegrityCheckResult:
    """
    Verify that a record produces the expected deterministic hash.
    """

    actual_hash = generate_record_hash(record)

    normalized_expected = str(
        expected_hash
    ).strip()

    return IntegrityCheckResult(
        valid=(
            bool(normalized_expected)
            and actual_hash == normalized_expected
        ),
        expected_hash=normalized_expected,
        actual_hash=actual_hash,
    )


@dataclass(frozen=True)
class IntegrityIssue:
    """One detected integrity problem."""

    check_name: str
    severity: str
    message: str


@dataclass(frozen=True)
class IntegrityReport:
    """Complete result of an integrity audit."""

    checks_run: int
    issues: tuple[IntegrityIssue, ...]
    passed: bool


class IntegrityError(Exception):
    """Raised when an integrity audit cannot be executed."""


CORE_TABLES = (
    "insider_transactions",
    "market_prices",
    "corporate_actions",
    "research_events",
    "signals",
    "trade_runs",
    "provenance",
)


def _check_required_tables(
    database_url: str,
) -> list[IntegrityIssue]:

    issues: list[IntegrityIssue] = []

    with connect(database_url) as connection:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()

    existing = {
        str(row["name"])
        for row in rows
    }

    for table_name in CORE_TABLES:
        if table_name not in existing:
            issues.append(
                IntegrityIssue(
                    check_name="required_tables",
                    severity="critical",
                    message=(
                        f"Required table '{table_name}' "
                        "does not exist."
                    ),
                )
            )

    return issues


def _check_negative_market_values(
    database_url: str,
) -> list[IntegrityIssue]:

    issues: list[IntegrityIssue] = []

    with connect(database_url) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                symbol,
                price_date
            FROM market_prices
            WHERE
                (open IS NOT NULL AND open < 0)
                OR (high IS NOT NULL AND high < 0)
                OR (low IS NOT NULL AND low < 0)
                OR (close IS NOT NULL AND close < 0)
                OR (
                    adjusted_close IS NOT NULL
                    AND adjusted_close < 0
                )
                OR (volume IS NOT NULL AND volume < 0)
            """
        ).fetchall()

    for row in rows:
        issues.append(
            IntegrityIssue(
                check_name="negative_market_values",
                severity="error",
                message=(
                    f"Market-price record {row['id']} "
                    f"for {row['symbol']} on "
                    f"{row['price_date']} contains "
                    "a negative numeric value."
                ),
            )
        )

    return issues


def _check_duplicate_market_prices(
    database_url: str,
) -> list[IntegrityIssue]:

    issues: list[IntegrityIssue] = []

    with connect(database_url) as connection:
        rows = connection.execute(
            """
            SELECT
                symbol,
                price_date,
                source,
                COUNT(*) AS record_count
            FROM market_prices
            GROUP BY
                symbol,
                price_date,
                source
            HAVING COUNT(*) > 1
            """
        ).fetchall()

    for row in rows:
        issues.append(
            IntegrityIssue(
                check_name="duplicate_market_prices",
                severity="error",
                message=(
                    "Duplicate market-price identity detected: "
                    f"{row['symbol']} / "
                    f"{row['price_date']} / "
                    f"{row['source']} "
                    f"({row['record_count']} records)."
                ),
            )
        )

    return issues


def _check_duplicate_signals(
    database_url: str,
) -> list[IntegrityIssue]:

    issues: list[IntegrityIssue] = []

    with connect(database_url) as connection:
        rows = connection.execute(
            """
            SELECT
                signal_key,
                COUNT(*) AS record_count
            FROM signals
            GROUP BY signal_key
            HAVING COUNT(*) > 1
            """
        ).fetchall()

    for row in rows:
        issues.append(
            IntegrityIssue(
                check_name="duplicate_signals",
                severity="error",
                message=(
                    f"Signal key '{row['signal_key']}' "
                    f"appears {row['record_count']} times."
                ),
            )
        )

    return issues


def _check_invalid_trade_modes(
    database_url: str,
) -> list[IntegrityIssue]:

    issues: list[IntegrityIssue] = []

    with connect(database_url) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                run_id,
                mode
            FROM trade_runs
            WHERE mode NOT IN ('paper', 'live')
            """
        ).fetchall()

    for row in rows:
        issues.append(
            IntegrityIssue(
                check_name="trade_modes",
                severity="critical",
                message=(
                    f"Trade run '{row['run_id']}' "
                    f"has invalid mode '{row['mode']}'."
                ),
            )
        )

    return issues


def _check_provenance_status(
    database_url: str,
) -> list[IntegrityIssue]:

    issues: list[IntegrityIssue] = []

    with connect(database_url) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                record_type,
                record_id
            FROM provenance
            WHERE validation_status IS NULL
               OR TRIM(validation_status) = ''
            """
        ).fetchall()

    for row in rows:
        issues.append(
            IntegrityIssue(
                check_name="provenance_status",
                severity="error",
                message=(
                    f"Provenance record {row['id']} for "
                    f"{row['record_type']}:{row['record_id']} "
                    "has no validation status."
                ),
            )
        )

    return issues


def _check_orphaned_provenance(
    database_url: str,
) -> list[IntegrityIssue]:

    issues: list[IntegrityIssue] = []

    checks = (
        (
            "insider_transaction",
            "insider_transactions",
            "record_hash",
        ),
        (
            "market_price",
            "market_prices",
            "record_hash",
        ),
        (
            "corporate_action",
            "corporate_actions",
            "record_hash",
        ),
    )

    with connect(database_url) as connection:
        for record_type, table_name, column_name in checks:

            rows = connection.execute(
                """
                SELECT
                    id,
                    record_id
                FROM provenance
                WHERE record_type = ?
                """,
                (record_type,),
            ).fetchall()

            for row in rows:

                referenced = connection.execute(
                    f"""
                    SELECT 1
                    FROM {table_name}
                    WHERE {column_name} = ?
                    LIMIT 1
                    """,
                    (row["record_id"],),
                ).fetchone()

                if referenced is None:
                    issues.append(
                        IntegrityIssue(
                            check_name="orphaned_provenance",
                            severity="error",
                            message=(
                                f"Provenance record "
                                f"{row['id']} references "
                                f"missing {record_type} "
                                f"record '{row['record_id']}'."
                            ),
                        )
                    )

    return issues


def run_integrity_audit(
    database_url: str,
    *,
    checks: Iterable[str] | None = None,
) -> IntegrityReport:

    available_checks = {
        "required_tables": _check_required_tables,
        "negative_market_values": (
            _check_negative_market_values
        ),
        "duplicate_market_prices": (
            _check_duplicate_market_prices
        ),
        "duplicate_signals": (
            _check_duplicate_signals
        ),
        "trade_modes": _check_invalid_trade_modes,
        "provenance_status": (
            _check_provenance_status
        ),
        "orphaned_provenance": (
            _check_orphaned_provenance
        ),
    }

    if checks is None:
        selected_checks = list(
            available_checks.keys()
        )
    else:
        selected_checks = [
            str(check).strip()
            for check in checks
        ]

    issues: list[IntegrityIssue] = []

    for check_name in selected_checks:

        if check_name not in available_checks:
            raise IntegrityError(
                f"Unsupported integrity check: {check_name}"
            )

        try:
            issues.extend(
                available_checks[check_name](
                    database_url
                )
            )
        except Exception as exc:
            raise IntegrityError(
                f"Integrity check '{check_name}' "
                f"could not be executed: {exc}"
            ) from exc

    return IntegrityReport(
        checks_run=len(selected_checks),
        issues=tuple(issues),
        passed=not issues,
        )
