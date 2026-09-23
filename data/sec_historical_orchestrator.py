"""
SEC historical-ingestion orchestrator for Insider Trade Bot.

This module coordinates SEC company lookup, SEC submissions retrieval,
historical-record preparation, and controlled ingestion.

It does not bypass validation or write directly to permanent storage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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


class SECHistoricalOrchestratorError(
    Exception
):
    """Raised when SEC historical orchestration fails."""


class SECHistoricalOrchestrator:
    """
    Controlled coordinator for SEC historical insider-data ingestion.
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

    def _load_company(
        self,
        company: SECCompany,
    ) -> SECHistoricalLoadSummary:
        """
        Retrieve the company's SEC submissions and pass them through the
        controlled historical ingestion layer.
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

        try:
            result = load_sec_submissions(
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

        if not isinstance(
            result,
            HistoricalLoadResult,
        ):
            raise SECHistoricalOrchestratorError(
                "SEC historical loader returned an invalid result."
            )

        return SECHistoricalLoadSummary(
            company_cik=company.cik,
            company_ticker=company.ticker,
            company_title=company.title,
            attempted_count=result.attempted_count,
            accepted_count=result.accepted_count,
            record_hashes=result.record_hashes,
  )
