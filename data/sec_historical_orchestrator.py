"""
SEC historical-ingestion orchestrator for Insider Trade Bot.

This module coordinates SEC company lookup, SEC submissions retrieval,
historical submission-file retrieval, historical-record preparation,
and controlled ingestion.

It does not bypass validation or write directly to permanent storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from data.sec_company_data import (
    SECCompany,
    find_company_by_cik,
    find_company_by_ticker,
    normalize_company_tickers,
)
from data.sec_historical_loader import (
    load_sec_submissions,
)
from data.historical_loader import (
    HistoricalLoadResult,
)
from ingestion.sec_client import (
    SECClient,
)


@dataclass(frozen=True)
class SECHistoricalLoadSummary:
    """
    Summary of one SEC historical-ingestion operation.
    """

    company_cik: str
    company_ticker: str
    company_title: str

    attempted_count: int
    accepted_count: int

    record_hashes: tuple[str, ...]

    submission_sources_processed: int
    recent_submission_rows: int
    historical_submission_rows: int


class SECHistoricalOrchestratorError(
    Exception
):
    """Raised when SEC historical orchestration fails."""


class SECHistoricalOrchestrator:
    """
    Controlled coordinator for SEC historical insider-data ingestion.

    The SEC submissions endpoint provides:
    - a recent filing dataset
    - references to older submission files

    This orchestrator processes both sources through the existing
    controlled historical ingestion pipeline.
    """

    def __init__(
        self,
        *,
        sec_client: SECClient,
        database_url: str,
    ) -> None:
        if not isinstance(
            sec_client,
            SECClient,
        ):
            raise TypeError(
                "sec_client must be a SECClient instance."
            )

        if not str(
            database_url
        ).strip():
            raise ValueError(
                "database_url cannot be empty."
            )

        self.sec_client = sec_client
        self.database_url = database_url

    def load_company_by_cik(
        self,
        *,
        cik: str,
        company_tickers_payload: dict[str, Any],
    ) -> SECHistoricalLoadSummary:
        """
        Retrieve and ingest SEC insider filings for a company identified
        by CIK.
        """

        companies = normalize_company_tickers(
            company_tickers_payload
        )

        company = find_company_by_cik(
            companies,
            cik,
        )

        if company is None:
            raise SECHistoricalOrchestratorError(
                f"No SEC company was found for CIK '{cik}'."
            )

        return self._load_company(
            company
        )

    def load_company_by_ticker(
        self,
        *,
        ticker: str,
        company_tickers_payload: dict[str, Any],
    ) -> SECHistoricalLoadSummary:
        """
        Retrieve and ingest SEC insider filings for a company identified
        by ticker.
        """

        companies = normalize_company_tickers(
            company_tickers_payload
        )

        company = find_company_by_ticker(
            companies,
            ticker,
        )

        if company is None:
            raise SECHistoricalOrchestratorError(
                f"No SEC company was found for ticker '{ticker}'."
            )

        return self._load_company(
            company
        )

    @staticmethod
    def _extract_recent_rows(
        submissions: Mapping[str, Any],
    ) -> int:
        """
        Return the number of filing rows represented by filings.recent.
        """

        filings = submissions.get(
            "filings"
        )

        if not isinstance(
            filings,
            Mapping,
        ):
            return 0

        recent = filings.get(
            "recent"
        )

        if not isinstance(
            recent,
            Mapping,
        ):
            return 0

        lengths = [
            len(values)
            for values in recent.values()
            if isinstance(values, list)
        ]

        return max(
            lengths,
            default=0,
        )

    @staticmethod
    def _extract_historical_filenames(
        submissions: Mapping[str, Any],
    ) -> tuple[str, ...]:
        """
        Extract historical SEC submissions filenames.

        The SEC submissions response may expose older submission files
        under filings.files. Each entry normally identifies a JSON file
        containing older submission records.

        Only plain filenames are returned.
        """

        filings = submissions.get(
            "filings"
        )

        if not isinstance(
            filings,
            Mapping,
        ):
            return ()

        files = filings.get(
            "files"
        )

        if not isinstance(
            files,
            list,
        ):
            return ()

        filenames: list[str] = []

        for index, entry in enumerate(
            files
        ):
            if not isinstance(
                entry,
                Mapping,
            ):
                raise SECHistoricalOrchestratorError(
                    "Invalid SEC historical-file entry "
                    f"at index {index}."
                )

            filename = entry.get(
                "name"
            )

            if filename is None:
                filename = entry.get(
                    "filename"
                )

            if filename is None:
                continue

            normalized = str(
                filename
            ).strip()

            if not normalized:
                continue

            if (
                "/" in normalized
                or "\\" in normalized
                or ".." in normalized
            ):
                raise SECHistoricalOrchestratorError(
                    "SEC historical submission filename "
                    f"contains an unsafe path: {normalized!r}"
                )

            filenames.append(
                normalized
            )

        return tuple(
            filenames
        )

    def _load_submission_dataset(
        self,
        *,
        company: SECCompany,
        submissions: Mapping[str, Any],
    ) -> HistoricalLoadResult:
        """
        Ingest one SEC submissions dataset.
        """

        try:
            return load_sec_submissions(
                self.database_url,
                submissions,
                issuer_cik=company.cik,
                issuer_name=company.title,
            )
        except Exception as exc:
            raise SECHistoricalOrchestratorError(
                f"Failed to ingest SEC submissions for "
                f"{company.ticker}: {exc}"
            ) from exc

    def _load_company(
        self,
        company: SECCompany,
    ) -> SECHistoricalLoadSummary:
        """
        Retrieve and ingest recent and historical SEC submissions.
        """

        try:
            submissions = self.sec_client.get_submissions(
                company.cik
            )
        except Exception as exc:
            raise SECHistoricalOrchestratorError(
                f"Failed to retrieve SEC submissions for "
                f"{company.ticker}: {exc}"
            ) from exc

        if not isinstance(
            submissions,
            dict,
        ):
            raise SECHistoricalOrchestratorError(
                "SEC submissions response must be a JSON object."
            )

        recent_rows = self._extract_recent_rows(
            submissions
        )

        historical_filenames = (
            self._extract_historical_filenames(
                submissions
            )
        )

        all_hashes: list[str] = []
        attempted_count = 0
        accepted_count = 0
        historical_rows = 0
        sources_processed = 0

        recent_result = self._load_submission_dataset(
            company=company,
            submissions=submissions,
        )

        sources_processed += 1
        attempted_count += recent_result.attempted_count
        accepted_count += recent_result.accepted_count
        all_hashes.extend(
            recent_result.record_hashes
        )

        for filename in historical_filenames:
            try:
                historical_submissions = (
                    self.sec_client.get_submission_file(
                        filename
                    )
                )
            except Exception as exc:
                raise SECHistoricalOrchestratorError(
                    f"Failed to retrieve historical SEC "
                    f"submission file '{filename}' for "
                    f"{company.ticker}: {exc}"
                ) from exc

            if not isinstance(
                historical_submissions,
                dict,
            ):
                raise SECHistoricalOrchestratorError(
                    f"Historical SEC submission file "
                    f"'{filename}' did not return a JSON object."
                )

            historical_rows += (
                self._extract_recent_rows(
                    historical_submissions
                )
            )

            historical_result = (
                self._load_submission_dataset(
                    company=company,
                    submissions=historical_submissions,
                )
            )

            sources_processed += 1
            attempted_count += (
                historical_result.attempted_count
            )
            accepted_count += (
                historical_result.accepted_count
            )
            all_hashes.extend(
                historical_result.record_hashes
            )

        return SECHistoricalLoadSummary(
            company_cik=company.cik,
            company_ticker=company.ticker,
            company_title=company.title,
            attempted_count=attempted_count,
            accepted_count=accepted_count,
            record_hashes=tuple(
                all_hashes
            ),
            submission_sources_processed=sources_processed,
            recent_submission_rows=recent_rows,
            historical_submission_rows=historical_rows,
    )
