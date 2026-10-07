from __future__ import annotations

import zipfile
import pytest

from archive import ArchiveError, FilesystemSECArchive
from data.acquisition_state import AcquisitionStateManager
from data.sec_dataset_pipeline import NormalizedBulkTransaction
from database.connection import initialize_database
from research.event_study import EventStudyEngine
from research.insider_adapter import prepare_event_study_inputs
from research.research_data_access import (
    PeriodNotFoundError,
    check_market_data_coverage,
    get_historical_transactions,
    get_market_prices_for_ticker,
    resolve_period_storage_location,
)
from storage.repository import store_bulk_insider_transactions, store_market_price


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


def test_research_archive_storage_error_propagates(tmp_path):
    db_file = tmp_path / "archive_error.db"
    db_url = f"sqlite:///{db_file}"

    class FailingArchive:
        def exists(self, period):
            raise ArchiveError("R2 storage unavailable")

    with pytest.raises(ArchiveError, match="R2 storage unavailable"):
        resolve_period_storage_location(
            db_url,
            FailingArchive(),
            "2020-Q1",
            reference_period="2020-Q1",
        )


def test_research_retention_runtime_error_propagates(tmp_path, monkeypatch):
    db_file = tmp_path / "research_retention_error.db"
    db_url = f"sqlite:///{db_file}"

    class FailingArchive:
        def exists(self, period):
            raise AssertionError("archive.exists must not be reached")

    def fail_retention(*args, **kwargs):
        raise RuntimeError("authoritative retention reference unavailable")

    monkeypatch.setattr(
        "research.research_data_access.AcquisitionStateManager.is_within_operational_retention",
        fail_retention,
    )

    with pytest.raises(
        RuntimeError,
        match="authoritative retention reference unavailable",
    ):
        resolve_period_storage_location(
            db_url,
            FailingArchive(),
            "2020-Q1",
        )


def test_resolve_period_storage_location_and_get_historical_transactions(tmp_path):
    db_file = tmp_path / "res_test.db"
    db_url = f"sqlite:///{db_file}"
    archive_dir = tmp_path / "archive"

    archive = FilesystemSECArchive(base_path=str(archive_dir))

    # 1. Period missing from both
    assert resolve_period_storage_location(db_url, archive, "2006-Q1", reference_period="2006-Q1") == "MISSING"

    with pytest.raises(PeriodNotFoundError) as exc_info:
        get_historical_transactions(db_url, archive, "2006-Q1", "2006-Q1", reference_period="2006-Q1")
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
    assert resolve_period_storage_location(db_url, archive, "2006-Q1", reference_period="2006-Q1") == "R2"

    # Fetch 2006-Q1 from R2 fallback
    txs_r2 = get_historical_transactions(db_url, archive, "2006-Q1", "2006-Q1", tickers="AAPL", reference_period="2006-Q1")
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
    assert resolve_period_storage_location(db_url, archive, "2006-Q2", reference_period="2006-Q2") == "R2"

    # Mark 2006-Q2 as COMPLETED -> now resolves to NEON
    state_mgr.record_period_completion("2006-Q2", 1, 1, 0, 0, 0, status="COMPLETED")
    assert resolve_period_storage_location(db_url, archive, "2006-Q2", reference_period="2006-Q2") == "NEON"

    # Query range across both Neon and R2 (2006-Q1 in R2, 2006-Q2 in Neon)
    txs_combined = get_historical_transactions(db_url, archive, "2006-Q1", "2006-Q2", tickers=["AAPL"], reference_period="2006-Q2")
    assert len(txs_combined) == 2
    assert txs_combined[0].accession_number == "0000000001-06-000001"  # 2006-Q1 from R2
    assert txs_combined[1].accession_number == "0000000002-06-000002"  # 2006-Q2 from Neon


def test_series_isolation_no_silent_fallback(tmp_path):
    db_file = tmp_path / "series_iso.db"
    db_url = f"sqlite:///{db_file}"
    initialize_database(db_url)

    # Store a record with raw close=100.0, adjusted_close=None
    store_market_price(
        db_url, symbol="AAPL", price_date="2023-01-01",
        open_price=100.0, high=105.0, low=99.0, close=100.0,
        adjusted_close=None, volume=1000.0, source="src"
    )
    # Store a record with raw close=None, adjusted_close=105.0
    store_market_price(
        db_url, symbol="AAPL", price_date="2023-01-02",
        open_price=100.0, high=105.0, low=99.0, close=None,
        adjusted_close=105.0, volume=1000.0, source="src"
    )

    # 1. Raw close requested -> ONLY 2023-01-01 returned
    raw_prices = get_market_prices_for_ticker(db_url, "AAPL", use_adjusted_close=False)
    assert list(raw_prices.keys()) == ["2023-01-01"]
    assert raw_prices["2023-01-01"] == 100.0

    # 2. Adjusted close requested -> ONLY 2023-01-02 returned (no silent fallback to raw close)
    adj_prices = get_market_prices_for_ticker(db_url, "AAPL", use_adjusted_close=True)
    assert list(adj_prices.keys()) == ["2023-01-02"]
    assert adj_prices["2023-01-02"] == 105.0


def test_strengthened_coverage_reporting(tmp_path):
    db_file = tmp_path / "cov_test.db"
    db_url = f"sqlite:///{db_file}"
    initialize_database(db_url)

    # 1. No data in DB
    report_empty = check_market_data_coverage(db_url, "AAPL", start_date="2023-01-01", end_date="2023-01-10")
    assert report_empty.observation_count == 0
    assert report_empty.missing_requested_range is True

    # 2. Add prices from 2023-01-05 to 2023-01-08
    for d, c in [("2023-01-05", 100.0), ("2023-01-06", 101.0), ("2023-01-07", 102.0), ("2023-01-08", 103.0)]:
        store_market_price(db_url, symbol="AAPL", price_date=d, open_price=c, high=c+1, low=c-1, close=c, adjusted_close=c, volume=100.0, source="src")

    # Range starts before available data
    rep_early = check_market_data_coverage(db_url, "AAPL", start_date="2023-01-01", end_date="2023-01-07")
    assert rep_early.starts_before_available is True
    assert rep_early.missing_requested_range is True

    # Range ends after available data
    rep_late = check_market_data_coverage(db_url, "AAPL", start_date="2023-01-05", end_date="2023-01-10")
    assert rep_late.ends_after_available is True
    assert rep_late.missing_requested_range is True

    # Covered range
    rep_ok = check_market_data_coverage(db_url, "AAPL", start_date="2023-01-05", end_date="2023-01-08")
    assert rep_ok.starts_before_available is False
    assert rep_ok.ends_after_available is False
    assert rep_ok.is_range_covered_boundary_level is True
    assert rep_ok.missing_requested_range is False


def test_point_in_time_price_rule_and_amendment_handling(tmp_path, monkeypatch):
    db_file = tmp_path / "pit_test.db"
    db_url = f"sqlite:///{db_file}"

    from database.connection import connect
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

    assert len(adapter_res.valid_events) == 1
    assert len(adapter_res.rejections) == 1
    assert adapter_res.rejections[0].reason == "REJECTED_AMENDMENT_UNRESOLVED_ORIGINAL"

    event = adapter_res.valid_events[0]
    assert event.event_date == "2026-02-11"
    assert event.event_price == 195.0
