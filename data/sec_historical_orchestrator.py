"""
SEC historical-ingestion orchestrator for Insider Trade Bot.

This module coordinates:

    SEC company lookup
        -> SEC submissions retrieval
        -> identification of Form 3/4/5 filings
        -> primary filing-document retrieval
        -> filing parsing
        -> controlled validation/ingestion
        -> provenance

Important:

SEC submissions metadata is NOT treated as insider-transaction data.

The submissions endpoint is used only to discover eligible insider filings.
Actual transaction records are obtained from the individual SEC filing
documents and then passed through the existing controlled ingestion pipeline.
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
from data.sec_filing_client import (
    SECFilingClient,
)
from data.sec_filing_pipeline import (
    SECFilingPipelineError,
    retrieve_and_process_filing,
)
from data.sec_form_parser import (
    SECFormParserError,
)
from ingestion.sec_client import (
    SECClient,
)
from data.ingestion_pipeline import (
    IngestionError,
    ingest_insider_transaction,
)


# SEC insider-reporting forms that contain insider ownership/
# transaction information.
_INSIDER_FORMS = frozenset(
    {
        "3",
        "3/A",
        "4",
        "4/A",
        "5",
        "5/A",
    }
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

    SEC submissions are used as filing indexes.

    For every eligible Form 3/4/5 filing, the orchestrator:

        1. identifies the filing accession number
        2. identifies the primary document
        3. retrieves the actual SEC filing document
        4. parses the filing
        5. sends each parsed transaction through the normal
           normalization/validation/storage/provenance pipeline

    The constructor supports an unconfigured capability-test state.
    Actual SEC ingestion still requires a configured SEC client and
    database URL.
    """

    def __init__(
        self,
        *,
        sec_client: SECClient | None = None,
        database_url: str | None = None,
    ) -> None:
        if sec_client is not None and not isinstance(
            sec_client,
            SECClient,
        ):
            raise TypeError(
                "sec_client must be a SECClient instance."
            )

        if database_url is not None and not str(
            database_url
        ).strip():
            raise ValueError(
                "database_url cannot be empty."
            )

        self.sec_client = sec_client
        self.database_url = database_url

    def _require_configuration(
        self,
    ) -> tuple[SECClient, str]:
        """
        Require dependencies needed for real historical ingestion.
        """

        if self.sec_client is None:
            raise SECHistoricalOrchestratorError(
                "SEC client is not configured."
            )

        if self.database_url is None:
            raise SECHistoricalOrchestratorError(
                "database_url is not configured."
            )

        return (
            self.sec_client,
            self.database_url,
        )

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

        self._require_configuration()

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

        self._require_configuration()

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
    def _extract_recent_submission_rows(
        submissions: Mapping[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        """
        Convert SEC's column-oriented filings.recent structure into
        row-oriented filing dictionaries.
        """

        filings = submissions.get(
            "filings"
        )

        if not isinstance(
            filings,
            Mapping,
        ):
            return ()

        recent = filings.get(
            "recent"
        )

        if not isinstance(
            recent,
            Mapping,
        ):
            return ()

        column_names = tuple(
            recent.keys()
        )

        row_count = max(
            (
                len(values)
                for values in recent.values()
                if isinstance(values, list)
            ),
            default=0,
        )

        rows: list[dict[str, Any]] = []

        for row_index in range(
            row_count
        ):
            row: dict[str, Any] = {}

            for column_name in column_names:
                values = recent.get(
                    column_name
                )

                if not isinstance(
                    values,
                    list,
                ):
                    continue

                if row_index >= len(
                    values
                ):
                    continue

                row[
                    str(column_name)
                ] = values[
                    row_index
                ]

            rows.append(
                row
            )

        return tuple(
            rows
        )

    @staticmethod
    def _extract_historical_filenames(
        submissions: Mapping[str, Any],
    ) -> tuple[str, ...]:
        """
        Extract historical SEC submissions filenames.
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
                "/"
                in normalized
                or "\\"
                in normalized
                or ".."
                in normalized
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

    @staticmethod
    def _get_row_value(
        row: Mapping[str, Any],
        *keys: str,
    ) -> str | None:
        """
        Return the first non-empty value from a filing row.
        """

        for key in keys:
            value = row.get(
                key
            )

            if value is None:
                continue

            normalized = str(
                value
            ).strip()

            if normalized:
                return normalized

        return None

    @classmethod
    def _is_insider_form(
        cls,
        row: Mapping[str, Any],
    ) -> bool:
        """
        Determine whether a submission row represents a Form 3/4/5
        insider filing.
        """

        form_type = cls._get_row_value(
            row,
            "form",
            "formType",
            "form_type",
        )

        if form_type is None:
            return False

        return form_type.upper() in {
            form.upper()
            for form in _INSIDER_FORMS
        }

    @classmethod
    def _extract_filing_identity(
        cls,
        row: Mapping[str, Any],
    ) -> tuple[str, str, str, str]:
        """
        Extract the minimum identity required to retrieve one primary
        SEC filing document.

        Returns:

            accession_number
            document_name
            form_type
            filing_date
        """

        accession_number = cls._get_row_value(
            row,
            "accessionNumber",
            "accession_number",
            "accession",
        )

        document_name = cls._get_row_value(
            row,
            "primaryDocument",
            "primary_document",
            "primaryDocumentName",
            "primary_document_name",
            "documentName",
            "document_name",
        )

        form_type = cls._get_row_value(
            row,
            "form",
            "formType",
            "form_type",
        )

        filing_date = cls._get_row_value(
            row,
            "filingDate",
            "filing_date",
            "filedDate",
        )

        if not accession_number:
            raise SECHistoricalOrchestratorError(
                "Eligible SEC insider filing has no "
                "accession number."
            )

        if not document_name:
            raise SECHistoricalOrchestratorError(
                "Eligible SEC insider filing "
                f"'{accession_number}' has no primary document."
            )

        if not form_type:
            raise SECHistoricalOrchestratorError(
                "Eligible SEC insider filing "
                f"'{accession_number}' has no form type."
            )

        if not filing_date:
            raise SECHistoricalOrchestratorError(
                "Eligible SEC insider filing "
                f"'{accession_number}' has no filing date."
            )

        return (
            accession_number,
            document_name,
            form_type,
            filing_date,
        )

    @staticmethod
    def _build_filing_source_reference(
        filing_client: SECFilingClient,
        *,
        cik: str,
        accession_number: str,
        document_name: str,
    ) -> str:
        """
        Build a deterministic reference to the primary SEC filing
        document used as the ingestion source.
        """

        normalized_cik = str(
            cik
        ).strip().zfill(10)

        normalized_accession = str(
            accession_number
        ).strip()

        archive_accession = (
            normalized_accession.replace(
                "-",
                "",
            )
        )

        base_url = str(
            filing_client.base_url
        ).strip().rstrip("/")

        return (
            f"{base_url}/Archives/edgar/data/"
            f"{int(normalized_cik)}/"
            f"{archive_accession}/"
            f"{document_name}"
        )

    def _create_filing_client(
        self,
    ) -> SECFilingClient:
        """
        Create the filing-document client from the configured SEC client.

        Both clients use the same SEC base URL, User-Agent, and timeout.
        """

        sec_client, _ = self._require_configuration()

        if not sec_client.base_url:
            raise SECHistoricalOrchestratorError(
                "SEC base_url is not configured."
            )

        if not sec_client.user_agent:
            raise SECHistoricalOrchestratorError(
                "SEC_USER_AGENT is not configured."
            )

        return SECFilingClient(
            base_url=sec_client.base_url,
            user_agent=sec_client.user_agent,
            timeout=sec_client.timeout,
        )

    def _ingest_filing(
        self,
        *,
        company: SECCompany,
        filing_client: SECFilingClient,
        row: Mapping[str, Any],
        processed_filings: set[
            tuple[str, str]
        ],
    ) -> tuple[int, int, tuple[str, ...]]:
        """
        Retrieve, parse, validate, store, and provenance-track one
        eligible SEC insider filing.

        Returns:

            attempted transaction count
            accepted transaction count
            record hashes
        """

        if not self._is_insider_form(
            row
        ):
            return (
                0,
                0,
                (),
            )

        (
            accession_number,
            document_name,
            form_type,
            filing_date,
        ) = self._extract_filing_identity(
            row
        )

        filing_identity = (
            accession_number,
            document_name,
        )

        if filing_identity in processed_filings:
            return (
                0,
                0,
                (),
            )

        processed_filings.add(
            filing_identity
        )

        try:
            transactions = (
                retrieve_and_process_filing(
                    filing_client,
                    cik=company.cik,
                    accession_number=accession_number,
                    document_name=document_name,
                    form_type=form_type,
                    issuer_name=company.title,
                    filing_date=filing_date,
                    source="SEC",
                )
            )
        except (
            SECFilingPipelineError,
            SECFormParserError,
            TypeError,
            ValueError,
        ) as exc:
            raise SECHistoricalOrchestratorError(
                "Failed to retrieve or parse SEC insider filing "
                f"{accession_number} "
                f"({form_type}) for {company.ticker}: {exc}"
            ) from exc
        except Exception as exc:
            raise SECHistoricalOrchestratorError(
                "Unexpected failure while processing SEC insider "
                f"filing {accession_number} "
                f"({form_type}) for {company.ticker}: {exc}"
            ) from exc

        attempted_count = len(
            transactions
        )

        if attempted_count == 0:
            raise SECHistoricalOrchestratorError(
                "SEC insider filing "
                f"{accession_number} ({form_type}) produced "
                "no transaction records."
            )

        source_reference = (
            self._build_filing_source_reference(
                filing_client,
                cik=company.cik,
                accession_number=accession_number,
                document_name=document_name,
            )
        )

        hashes: list[str] = []

        for transaction_index, payload in enumerate(
            transactions
        ):
            if not isinstance(
                payload,
                Mapping,
            ):
                raise SECHistoricalOrchestratorError(
                    "SEC filing "
                    f"{accession_number} produced a non-mapping "
                    f"transaction at index {transaction_index}."
                )

            try:
                record_hash = (
                    ingest_insider_transaction(
                        self.database_url,
                        payload,
                        source="SEC",
                        source_reference=source_reference,
                    )
                )
            except (
                IngestionError,
                TypeError,
                ValueError,
            ) as exc:
                raise SECHistoricalOrchestratorError(
                    "SEC insider transaction from filing "
                    f"{accession_number} failed controlled "
                    f"ingestion at transaction index "
                    f"{transaction_index}: {exc}"
                ) from exc

            hashes.append(
                record_hash
            )

        return (
            attempted_count,
            len(hashes),
            tuple(hashes),
        )

    def _process_submission_dataset(
        self,
        *,
        company: SECCompany,
        submissions: Mapping[str, Any],
        filing_client: SECFilingClient,
        processed_filings: set[
            tuple[str, str]
        ],
    ) -> tuple[int, int, tuple[str, ...]]:
        """
        Process all eligible insider filings represented by one SEC
        submissions dataset.
        """

        rows = self._extract_recent_submission_rows(
            submissions
        )

        attempted_count = 0
        accepted_count = 0
        all_hashes: list[str] = []

        for row_index, row in enumerate(
            rows
        ):
            if not self._is_insider_form(
                row
            ):
                continue

            try:
                (
                    row_attempted,
                    row_accepted,
                    row_hashes,
                ) = self._ingest_filing(
                    company=company,
                    filing_client=filing_client,
                    row=row,
                    processed_filings=processed_filings,
                )
            except SECHistoricalOrchestratorError as exc:
                raise SECHistoricalOrchestratorError(
                    "SEC historical processing failed for "
                    f"{company.ticker} at submission row "
                    f"{row_index}: {exc}"
                ) from exc

            attempted_count += row_attempted
            accepted_count += row_accepted
            all_hashes.extend(
                row_hashes
            )

        return (
            attempted_count,
            accepted_count,
            tuple(all_hashes),
        )

    def _load_company(
        self,
        company: SECCompany,
    ) -> SECHistoricalLoadSummary:
        """
        Retrieve SEC submission indexes and process actual Form 3/4/5
        filing documents.
        """

        sec_client, _ = self._require_configuration()

        try:
            submissions = sec_client.get_submissions(
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

        filing_client = self._create_filing_client()

        recent_rows = self._extract_recent_rows(
            submissions
        )

        historical_filenames = (
            self._extract_historical_filenames(
                submissions
            )
        )

        processed_filings: set[
            tuple[str, str]
        ] = set()

        all_hashes: list[str] = []

        attempted_count = 0
        accepted_count = 0

        historical_rows = 0
        sources_processed = 0

        (
            recent_attempted,
            recent_accepted,
            recent_hashes,
        ) = self._process_submission_dataset(
            company=company,
            submissions=submissions,
            filing_client=filing_client,
            processed_filings=processed_filings,
        )

        sources_processed += 1

        attempted_count += recent_attempted
        accepted_count += recent_accepted

        all_hashes.extend(
            recent_hashes
        )

        for filename in historical_filenames:
            try:
                historical_submissions = (
                    sec_client.get_submission_file(
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

            (
                historical_attempted,
                historical_accepted,
                historical_hashes,
            ) = self._process_submission_dataset(
                company=company,
                submissions=historical_submissions,
                filing_client=filing_client,
                processed_filings=processed_filings,
            )

            sources_processed += 1

            attempted_count += historical_attempted
            accepted_count += historical_accepted

            all_hashes.extend(
                historical_hashes
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
