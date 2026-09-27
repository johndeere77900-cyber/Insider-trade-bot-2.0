from pathlib import Path

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


def test_sec_historical_continuation_file_top_level_rows_are_processed(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "historical_format.sqlite3"
    database_url = f"sqlite:///{database_path}"

    fixture_bytes = FIXTURE.read_bytes()

    # Main SEC submissions response.
    #
    # The current filing history is under filings.recent.
    submissions = {
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0001234567-26-000001",
                ],
                "filingDate": [
                    "2026-09-24",
                ],
                "form": [
                    "4",
                ],
                "primaryDocument": [
                    "form4.xml",
                ],
            },
            "files": [
                {
                    "name": "CIK0001234567-submissions-001.json"
                }
            ],
        }
    }

    # SEC historical continuation files contain the filing-history
    # columns directly at the top level rather than nesting them under
    # filings.recent.
    historical_submissions = {
        "accessionNumber": [
            "0001234567-06-000001",
            "0001234567-06-000002",
        ],
        "filingDate": [
            "2006-09-20",
            "2006-09-21",
        ],
        "form": [
            "4",
            "10-K",
        ],
        "primaryDocument": [
            "historical-form4.xml",
            "10k.htm",
        ],
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

    # The historical continuation file has two top-level rows.
    assert summary.historical_submission_rows == 2

    # One recent Form 4 + one historical Form 4.
    # The historical 10-K must be ignored.
    assert summary.attempted_count == 4
    assert summary.accepted_count == 4

    assert len(retrieval_calls) == 2

    assert {
        call[1]
        for call in retrieval_calls
    } == {
        "0001234567-26-000001",
        "0001234567-06-000001",
    }

    with connect(database_url) as connection:
        rows = connection.execute(
            """
            SELECT
                accession_number,
                form_type,
                insider_name
            FROM insider_transactions
            ORDER BY accession_number, id
            """
        ).fetchall()

    assert len(rows) == 4

    assert {
        row["accession_number"]
        for row in rows
    } == {
        "0001234567-26-000001",
        "0001234567-06-000001",
    }

    assert all(
        row["form_type"] == "4"
        for row in rows
    )

    assert all(
        row["insider_name"] == "Jane Doe"
        for row in rows
)
