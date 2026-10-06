from __future__ import annotations

from research.event_study import EventStudyEngine


def test_event_study_engine_can_calculate_returns() -> None:
    engine = EventStudyEngine()

    prices = [
        {"date": "2026-01-01", "close": 100.0},
        {"date": "2026-01-02", "close": 105.0},
        {"date": "2026-01-03", "close": 110.0},
    ]

    result = engine.calculate_returns(prices)

    assert result is not None
    assert len(result) == 2
    assert result[0]["return"] == 0.05
    assert result[1]["return"] == (110.0 / 105.0) - 1


def test_event_study_handles_empty_price_data() -> None:
    engine = EventStudyEngine()

    result = engine.calculate_returns([])

    assert result == []


def test_event_study_handles_single_price() -> None:
    engine = EventStudyEngine()

    result = engine.calculate_returns(
        [
            {"date": "2026-01-01", "close": 100.0},
        ]
    )

    assert result == []


import zipfile
import pytest
from archive import FilesystemSECArchive
from data.sec_dataset_pipeline import NormalizedBulkTransaction
from data.acquisition_state import AcquisitionStateManager
from research.research_data_access import (
    PeriodNotFoundError,
    get_historical_transactions,
    resolve_period_storage_location,
)
from research.insider_adapter import prepare_event_study_inputs
from storage.repository import store_bulk_insider_transactions


def test_resolve_period_storage_location_and_get_historical_transactions(tmp_path):
    db_file = tmp_path / "res_test.db"
    db_url = f"sqlite:///{db_file}"
    archive_dir = tmp_path / "archive"

    archive = FilesystemSECArchive(base_path=str(archive_dir))

    # 1. Period missing from both
    assert resolve_period_storage_location(db_url, archive, "2006-Q1") == "MISSING"

    with pytest.raises(PeriodNotFoundError) as exc_info:
        get_historical_transactions(db_url, archive, "2006-Q1", "2006-Q1")
    assert "2006-Q1" in str(exc_info.value)

    # 2. Add archive for 2006-Q1 to R2
    zfile_2006 = tmp_path / "2006Q1.zip"
    with zipfile.ZipFile(zfile_2006, "w") as zf:
        zf.writestr(
            "SUBMISSION.tsv",
            "ACCESSION_NUMBER\tISSUERCIK\tISSUERNAME\tISSUERTRADINGSYMBOL\tFILING_DATE\n"
            "0000000001-06-000001\t0000320193\tApple Inc.\tAAPL\t2006-02-10\n",
        )
        zf.writestr(
            "NONDERIV_TRANS.tsv",
            "ACCESSION_NUMBER\tNONDERIV_TRANS_SK\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tTRANS_ACQUIRED_DISP_CD\tDIRECT_INDIRECT_OWNERSHIP\n"
            "0000000001-06-000001\t1\t2006-02-08\tP\t1000\t50.0\tA\tD\n",
        )

    archive.put("2006-Q1", str(zfile_2006))
    assert resolve_period_storage_location(db_url, archive, "2006-Q1") == "R2"

    # Fetch 2006-Q1 from R2 fallback
    txs_r2 = get_historical_transactions(db_url, archive, "2006-Q1", "2006-Q1", tickers="AAPL")
    assert len(txs_r2) == 1
    assert txs_r2[0].ticker == "AAPL"
    assert txs_r2[0].accession_number == "0000000001-06-000001"
    assert txs_r2[0].shares == 1000.0

    # 3. Add 2006-Q2 directly into Neon DB with FAILED ingestion_state initially
    tx_neon = NormalizedBulkTransaction(
        accession_number="0000000002-06-000002",
        issuer_cik="0000320193",
        issuer_name="Apple Inc.",
        ticker="AAPL",
        reporting_owner_name="Cook Tim",
        reporting_owner_cik="0001214156",
        transaction_date="2006-05-08",
        filing_date="2006-05-10",
        transaction_code="S",
        security_title="Common Stock",
        shares=500.0,
        price_per_share=200.0,
        transaction_type="non_derivative",
        acquired_disposed="D",
        ownership_type="D",
        ownership_nature=None,
        source_url="https://sec.gov",
        is_amendment=False,
        date_of_orig_submission=None,
        raw_payload={},
        source="SEC",
        record_hash="hash_neon_2006q2",
        form_type="4",
    )
    store_bulk_insider_transactions(db_url, [tx_neon], store_raw_payload=False)

    # 3a. Also put R2 archive for 2006-Q2
    zfile_2006q2 = tmp_path / "2006Q2.zip"
    with zipfile.ZipFile(zfile_2006q2, "w") as zf:
        zf.writestr(
            "SUBMISSION.tsv",
            "ACCESSION_NUMBER\tISSUERCIK\tISSUERNAME\tISSUERTRADINGSYMBOL\tFILING_DATE\n"
            "0000000002-06-000002\t0000320193\tApple Inc.\tAAPL\t2006-05-10\n",
        )
        zf.writestr(
            "NONDERIV_TRANS.tsv",
            "ACCESSION_NUMBER\tNONDERIV_TRANS_SK\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tTRANS_ACQUIRED_DISP_CD\tDIRECT_INDIRECT_OWNERSHIP\n"
            "0000000002-06-000002\t1\t2006-05-08\tS\t500\t200.0\tD\tD\n",
        )
    archive.put("2006-Q2", str(zfile_2006q2))

    # Without COMPLETED status in ingestion_state, 2006-Q2 falls back to R2 (NOT partial Neon)
    state_mgr = AcquisitionStateManager(db_url)
    state_mgr.record_period_completion("2006-Q2", 1, 1, 0, 0, 1, status="FAILED")
    assert resolve_period_storage_location(db_url, archive, "2006-Q2") == "R2"

    # Mark 2006-Q2 as COMPLETED -> now resolves to NEON
    state_mgr.record_period_completion("2006-Q2", 1, 1, 0, 0, 0, status="COMPLETED")
    assert resolve_period_storage_location(db_url, archive, "2006-Q2") == "NEON"

    # Query range across both Neon and R2 (2006-Q1 in R2, 2006-Q2 in Neon)
    txs_combined = get_historical_transactions(db_url, archive, "2006-Q1", "2006-Q2", tickers=["AAPL"])
    assert len(txs_combined) == 2
    assert txs_combined[0].accession_number == "0000000001-06-000001"  # 2006-Q1 from R2
    assert txs_combined[1].accession_number == "0000000002-06-000002"  # 2006-Q2 from Neon


def test_point_in_time_price_rule_and_amendment_handling(tmp_path, monkeypatch):
    db_file = tmp_path / "pit_test.db"
    db_url = f"sqlite:///{db_file}"

    # Setup market_prices table
    from database.connection import initialize_database, connect
    initialize_database(db_url)
    with connect(db_url) as conn:
        conn.execute(
            "INSERT INTO market_prices (symbol, price_date, close, source, record_hash, created_at) VALUES "
            "('AAPL', '2026-02-10', 190.0, 'test', 'h1', '2026-02-10'), "
            "('AAPL', '2026-02-11', 195.0, 'test', 'h2', '2026-02-11'), "
            "('AAPL', '2026-02-12', 200.0, 'test', 'h3', '2026-02-12')"
        )

    original_tx = NormalizedBulkTransaction(
        accession_number="0000000001-26-000001",
        issuer_cik="0000320193",
        issuer_name="Apple Inc.",
        ticker="AAPL",
        reporting_owner_name="Cook Tim",
        reporting_owner_cik="0001214156",
        transaction_date="2026-02-08",
        filing_date="2026-02-10",
        transaction_code="P",
        security_title="Common Stock",
        shares=1000.0,
        price_per_share=185.0,
        transaction_type="non_derivative",
        acquired_disposed="A",
        ownership_type="D",
        ownership_nature=None,
        source_url="https://sec.gov",
        is_amendment=False,
        date_of_orig_submission=None,
        raw_payload={},
        source="SEC",
        record_hash="hash_orig",
        form_type="4",
    )

    unresolved_amend_tx = NormalizedBulkTransaction(
        accession_number="0000000002-26-000002",
        issuer_cik="0000320193",
        issuer_name="Apple Inc.",
        ticker="AAPL",
        reporting_owner_name="Cook Tim",
        reporting_owner_cik="0001214156",
        transaction_date="2026-02-08",
        filing_date="2026-02-10",
        transaction_code="P",
        security_title="Common Stock",
        shares=1200.0,
        price_per_share=185.0,
        transaction_type="non_derivative",
        acquired_disposed="A",
        ownership_type="D",
        ownership_nature=None,
        source_url="https://sec.gov",
        is_amendment=True,
        date_of_orig_submission="2026-02-10",
        raw_payload={},
        source="SEC",
        record_hash="hash_amend",
        form_type="4/A",
    )

    adapter_res = prepare_event_study_inputs(db_url, [original_tx, unresolved_amend_tx], horizon_days=1)

    # 1. Verification of amendment handling: original preserved, unresolved amendment rejected
    assert len(adapter_res.valid_events) == 1
    assert len(adapter_res.rejections) == 1
    assert adapter_res.rejections[0].reason == "REJECTED_AMENDMENT_UNRESOLVED_ORIGINAL"

    # 2. Verification of Point-In-Time price rule:
    # event_date MUST be 2026-02-11 (first date STRICTLY AFTER filing_date 2026-02-10)
    # event_price MUST be 195.0 (NEVER 190.0 closing price on filing_date)
    event = adapter_res.valid_events[0]
    assert event.event_date == "2026-02-11"
    assert event.event_price == 195.0


def test_r2_fallback_amendment_pit_download_boundary_integration(tmp_path, monkeypatch):
    """
    End-to-end integration test proving:
    1. Exact quarter resolution (2018-Q2 request fails if only 2018-Q1 exists).
    2. SEC downloader is NEVER called during research access.
    3. R2 ZIP -> parse -> normalize -> research access -> insider adapter -> amendment handling & PIT pricing.
    4. Unified retention decision scenarios (Old -> R2, Recent -> NEON, Partial Neon -> R2).
    """
    db_file = tmp_path / "e2e_res_test.db"
    db_url = f"sqlite:///{db_file}"
    archive_dir = tmp_path / "archive"
    archive = FilesystemSECArchive(base_path=str(archive_dir))

    # Setup market prices in DB
    from database.connection import initialize_database, connect
    initialize_database(db_url)
    with connect(db_url) as conn:
        conn.execute(
            "INSERT INTO market_prices (symbol, price_date, close, source, record_hash, created_at) VALUES "
            "('MSFT', '2018-05-10', 100.0, 'test', 'h1', '2018-05-10'), "  # Filing date price (MUST NOT BE SELECTED)
            "('MSFT', '2018-05-11', 102.0, 'test', 'h2', '2018-05-11'), "  # Entry price (MUST BE SELECTED)
            "('MSFT', '2018-05-12', 105.0, 'test', 'h3', '2018-05-12')"   # Horizon price
        )

    # SEC Downloader safety mock: ensure research NEVER calls SEC download
    def mock_sec_download(*args, **kwargs):
        raise RuntimeError("SEC Downloader MUST NOT be called by research layer!")

    monkeypatch.setattr("data.sec_dataset_pipeline.download_dataset_zip_to_file", mock_sec_download)

    # 1. Exact quarter resolution test: Put 2018-Q1 archive in R2
    zfile_2018q1 = tmp_path / "2018Q1.zip"
    with zipfile.ZipFile(zfile_2018q1, "w") as zf:
        zf.writestr("SUBMISSION.tsv", "ACCESSION_NUMBER\tISSUERCIK\tISSUERNAME\tISSUERTRADINGSYMBOL\tFILING_DATE\n0000000001-18-000001\t0000789019\tMicrosoft\tMSFT\t2018-02-10\n")
        zf.writestr("NONDERIV_TRANS.tsv", "ACCESSION_NUMBER\tNONDERIV_TRANS_SK\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tTRANS_ACQUIRED_DISP_CD\tDIRECT_INDIRECT_OWNERSHIP\n0000000001-18-000001\t1\t2018-02-08\tP\t100\t90.0\tA\tD\n")
    archive.put("2018-Q1", str(zfile_2018q1))

    # Requesting 2018-Q2 when only 2018-Q1 exists MUST raise PeriodNotFoundError (wrong quarter cannot satisfy request)
    with pytest.raises(PeriodNotFoundError, match="2018-Q2"):
        get_historical_transactions(db_url, archive, "2018-Q2", "2018-Q2")

    # 2. Put 2018-Q2 archive in R2 containing an original filing and an unresolved amendment
    zfile_2018q2 = tmp_path / "2018Q2.zip"
    with zipfile.ZipFile(zfile_2018q2, "w") as zf:
        zf.writestr(
            "SUBMISSION.tsv",
            "ACCESSION_NUMBER\tISSUERCIK\tISSUERNAME\tISSUERTRADINGSYMBOL\tFILING_DATE\tDATE_OF_ORIG_SUB\n"
            "0000000001-18-000002\t0000789019\tMicrosoft\tMSFT\t2018-05-10\t\n"
            "0000000002-18-000003\t0000789019\tMicrosoft\tMSFT\t2018-05-10\t2018-05-10\n",
        )
        zf.writestr(
            "NONDERIV_TRANS.tsv",
            "ACCESSION_NUMBER\tNONDERIV_TRANS_SK\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tTRANS_ACQUIRED_DISP_CD\tDIRECT_INDIRECT_OWNERSHIP\n"
            "0000000001-18-000002\t1\t2018-05-08\tP\t5000\t98.0\tA\tD\n"
            "0000000002-18-000003\t1\t2018-05-08\tP\t6000\t98.0\tA\tD\n",
        )
    archive.put("2018-Q2", str(zfile_2018q2))

    # Retrieve historical transactions for 2018-Q2 from R2
    txs_r2 = get_historical_transactions(db_url, archive, "2018-Q2", "2018-Q2", tickers="MSFT")
    assert len(txs_r2) == 2
    assert txs_r2[0].record_hash is not None
    assert txs_r2[1].record_hash is not None

    # Pass R2 retrieved transactions into insider adapter
    adapter_res = prepare_event_study_inputs(db_url, txs_r2, horizon_days=1)

    # Verify amendment rule: original preserved, unresolved amendment rejected
    assert len(adapter_res.valid_events) == 1
    assert len(adapter_res.rejections) == 1
    assert adapter_res.rejections[0].reason == "REJECTED_AMENDMENT_UNRESOLVED_ORIGINAL"

    # Verify Point-In-Time entry pricing:
    # Filing date is 2018-05-10 ($100.0) -> MUST NOT be selected as entry price
    # Entry date is 2018-05-11 ($102.0) -> MUST be selected as entry price
    event = adapter_res.valid_events[0]
    assert event.event_date == "2018-05-11"
    assert event.event_price == 102.0

    # 3. Unified retention decision test (Blocker 13)
    # Scenario A: Old period outside retention -> resolves to R2
    assert resolve_period_storage_location(db_url, archive, "2018-Q2") == "R2"

    # Scenario B: Recent period with completed ingestion_state -> resolves to NEON
    state_mgr = AcquisitionStateManager(db_url)
    state_mgr.record_period_completion("2026-Q1", 10, 10, 0, 0, 0, status="COMPLETED")
    assert resolve_period_storage_location(db_url, archive, "2026-Q1") == "NEON"

    # Scenario C: Partial Neon period (status FAILED/incomplete) + valid R2 -> resolves to R2
    state_mgr.record_period_completion("2018-Q1", 5, 2, 0, 0, 1, status="FAILED")
    assert resolve_period_storage_location(db_url, archive, "2018-Q1") == "R2"
