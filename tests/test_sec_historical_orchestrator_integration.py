from pathlib import Path

import pytest

from data.sec_filing_client import SECFilingClient
from data.sec_historical_orchestrator import (
    SECHistoricalOrchestrator,
)
from database.connection import connect
from ingestion.sec_client import SECClient


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "form4_realistic.xml"
)


def test_sec_historical_orchestrator_processes_recent_and_historical_filings(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "historical.sqlite3"
    database_url = f"sqlite:///{database_path}"

    fixture_bytes = FIXTURE.read_bytes()

    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0001234567-26-000001",
                    "0001234567-26-000002",
                ],
                "filingDate": [
                    "2026-09-24",
                    "2026-09-24",
                ],
                "form": [
                    "4",
                    "10-K",
                ],
                "primaryDocument": [
                    "form4.xml",
                    "10k.htm",
                ],
            },
            "files": [
                {
                    "name": "CIK0001234567-submissions-001.json"
                }
            ],
        }
    }

    historical_submissions = {
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0001234567-26-000001",
                    "0001234567-26-000003",
                ],
                "filingDate": [
                    "2026-09-24",
                    "2026-09-25",
                ],
                "form": [
                    "4",
                    "4",
                ],
                "primaryDocument": [
                    "form4.xml",
                    "historical-form4.xml",
                ],
            }
        }
    }

    sec_client = SECClient(
        base_url="https://example.test",
        user_agent="Insider Trade Bot test",
    )

    monkeypatch.setattr(
        sec_client,
        "get_submissions",
        lambda cik: submissions,
    )

    monkeypatch.setattr(
        sec_client,
        "get_submission_file",
        lambda filename: historical_submissions,
    )

    retrieval_calls = []

    def fake_get_filing_document(
        self,
        *,
        cik,
        accession_number,
        document_name,
    ):
        retrieval_calls.append(
            (
                cik,
                accession_number,
                document_name,
            )
        )

        return fixture_bytes

    monkeypatch.setattr(
        SECFilingClient,
        "get_filing_document",
        fake_get_filing_document,
    )

    orchestrator = SECHistoricalOrchestrator(
        sec_client=sec_client,
        database_url=database_url,
    )

    company_tickers_payload = {
        "0": {
            "cik_str": 1234567,
            "ticker": "EXMP",
            "title": "Example Holdings Inc.",
        }
    }

    summary = orchestrator.load_company_by_cik(
        cik="1234567",
        company_tickers_payload=company_tickers_payload,
    )

    # Recent dataset contains:
    #   1 eligible Form 4
    #   1 irrelevant Form 10-K
    #
    # Historical dataset contains:
    #   1 duplicate of the recent Form 4
    #   1 unique historical Form 4
    #
    # Each realistic Form 4 fixture contains two transactions.
    assert summary.recent_submission_rows == 2
    assert summary.historical_submission_rows == 2
    assert summary.submission_sources_processed == 2

    # Two unique filings x two transactions each.
    assert summary.attempted_count == 4
    assert summary.accepted_count == 4
    assert len(summary.record_hashes) == 4

    # The 10-K must never reach filing retrieval.
    # The duplicate Form 4 must also be skipped.
    assert len(retrieval_calls) == 2

    retrieved_accessions = {
        call[1]
        for call in retrieval_calls
    }

    assert retrieved_accessions == {
        "0001234567-26-000001",
        "0001234567-26-000003",
    }

    with connect(database_url) as connection:
        insider_rows = connection.execute(
            """
            SELECT
                accession_number,
                form_type,
                insider_name,
                transaction_code,
                shares,
                price,
                ownership_type
            FROM insider_transactions
            ORDER BY accession_number, id
            """
        ).fetchall()

        provenance_rows = connection.execute(
            """
            SELECT
                record_type,
                source,
                source_reference,
                validation_status
            FROM provenance
            ORDER BY id
            """
        ).fetchall()

    # Four accepted transaction records were actually persisted.
    assert len(insider_rows) == 4

    assert {
        row["accession_number"]
        for row in insider_rows
    } == {
        "0001234567-26-000001",
        "0001234567-26-000003",
    }

    assert all(
        row["form_type"] == "4"
        for row in insider_rows
    )

    assert all(
        row["insider_name"] == "Jane Doe"
        for row in insider_rows
    )

    assert {
        row["transaction_code"]
        for row in insider_rows
    } == {
        "P",
        "S",
    }

    assert len(provenance_rows) == 4

    assert all(
        row["record_type"] == "insider_transaction"
        for row in provenance_rows
    )

    assert all(
        row["source"] == "SEC"
        for row in provenance_rows
    )

    assert all(
        row["validation_status"] == "validated"
        for row in provenance_rows
    )

    assert all(
        row["source_reference"].startswith(
            "https://example.test/Archives/edgar/data/"
        )
        for row in provenance_rows
    )


def test_sec_historical_orchestrator_rejects_unsafe_historical_filename():
    orchestrator = SECHistoricalOrchestrator(
        sec_client=SECClient(
            base_url="https://example.test",
            user_agent="Insider Trade Bot test",
        ),
        database_url="sqlite:///unused.sqlite3",
    )

    malicious_submissions = {
        "filings": {
            "recent": {},
            "files": [
                {
                    "name": "../escape.json"
                }
            ],
        }
    }

    with pytest.raises(
        Exception,
        match="unsafe path",
    ):
        orchestrator._extract_historical_filenames(
            malicious_submissions
  )


def test_historical_acquisition_retry_previously_failed_period(
    tmp_path,
    monkeypatch,
):
    """
    Verify historical acquisition can retry a period that previously failed after writing provenance,
    without raising duplicate key error on dataset_period provenance.
    """
    import main
    from data.acquisition_state import AcquisitionStateManager
    from database.connection import connect
    from storage.repository import store_provenance

    db_file = tmp_path / "retry_test.db"
    db_url = f"sqlite:///{db_file}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SEC_USER_AGENT", "InsiderTradeBotTest/1.0 test@example.com")

    # Simulate previous run that failed after writing dataset_period provenance
    store_provenance(
        db_url,
        record_type="dataset_period",
        record_id="2006-Q1",
        source="SEC",
        source_reference="https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/2006q1_form345.zip",
        checksum="failed_checksum_123",
        validation_status="validated",
    )

    state_mgr = AcquisitionStateManager(db_url)
    state_mgr.record_period_completion(
        period="2006-Q1",
        records_parsed=0,
        records_inserted=0,
        duplicates_count=0,
        invalid_count=0,
        failures_count=1,
        status="FAILED",
    )

    from tests.test_sec_bulk_datasets import create_mock_zip_bytes
    mock_zip = create_mock_zip_bytes(case="default")

    def mock_download(year, qtr, user_agent, target_path):
        with open(target_path, "wb") as f:
            f.write(mock_zip)

    monkeypatch.setattr(
        "data.sec_dataset_pipeline.download_dataset_zip_to_file",
        mock_download,
    )

    res = main.run_historical_acquisition(
        start_period="2006-Q1",
        end_period="2006-Q1",
    )

    assert res == 0
    assert state_mgr.get_period_status("2006-Q1") == "COMPLETED"

    # Dataset-period provenance row count remains exactly 1
    with connect(db_url) as conn:
        prov_rows = conn.execute(
            "SELECT record_type, record_id, source, checksum FROM provenance WHERE record_type = 'dataset_period'"
        ).fetchall()

    assert len(prov_rows) == 1
    assert prov_rows[0]["record_id"] == "2006-Q1"
    assert prov_rows[0]["checksum"] != "failed_checksum_123"
