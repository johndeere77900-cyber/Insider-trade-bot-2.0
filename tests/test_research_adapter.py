"""
Unit tests for read-only research data-access layer and insider research adapter.
"""

from __future__ import annotations

import pytest

from data.sec_dataset_pipeline import NormalizedBulkTransaction
from database.connection import connect, initialize_database
from research.insider_adapter import (
    REJECTION_INSUFFICIENT_OBSERVATIONS,
    REJECTION_MISSING_DATE,
    REJECTION_MISSING_PRICE,
    REJECTION_MISSING_TICKER,
    convert_events_to_backtest_trades,
    convert_events_to_event_study_payloads,
    prepare_event_study_inputs,
)
from research.research.event_study import run_event_study
from research.research_data_access import (
    get_market_prices_for_ticker,
    query_insider_transactions,
)
from storage.repository import store_bulk_insider_transactions, store_market_price


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "research_test.db"
    db_url = f"sqlite:///{db_file}"
    initialize_database(db_url)

    # Insert market prices for dates 2024-01-15, 2024-01-16, 2024-01-17, 2024-01-18
    for d, p in [
        ("2024-01-15", 150.0),
        ("2024-01-16", 155.0),
        ("2024-01-17", 160.0),
        ("2024-01-18", 165.0),
    ]:
        store_market_price(
            db_url,
            symbol="AAPL",
            price_date=d,
            open_price=p,
            high=p + 2.0,
            low=p - 1.0,
            close=p,
            adjusted_close=p,
            volume=100000.0,
            source="TEST",
            raw_payload={"close": p},
        )

    # Insert transactions
    tx1 = NormalizedBulkTransaction(
        accession_number="000001",
        issuer_cik="0000320193",
        issuer_name="Apple Inc.",
        ticker="AAPL",
        reporting_owner_name="Cook Tim",
        reporting_owner_cik="0001214156",
        transaction_date="2024-01-15",
        filing_date="2024-01-16",
        transaction_code="S",
        security_title="Common Stock",
        shares=1000.0,
        price_per_share=150.0,
        transaction_type="non_derivative",
        acquired_disposed="D",
        ownership_type="D",
        ownership_nature="Direct",
        source_url="https://sec.gov",
        is_amendment=False,
        date_of_orig_submission=None,
        raw_payload={},
        source="SEC",
        record_hash="hash1",
        form_type="4",
    )

    tx2 = NormalizedBulkTransaction(
        accession_number="000002",
        issuer_cik="0000320193",
        issuer_name="Apple Inc.",
        ticker="AAPL",
        reporting_owner_name="Cook Tim",
        reporting_owner_cik="0001214156",
        transaction_date="2024-01-16",
        filing_date="2024-01-17",
        transaction_code="P",
        security_title="Common Stock",
        shares=500.0,
        price_per_share=155.0,
        transaction_type="non_derivative",
        acquired_disposed="A",
        ownership_type="D",
        ownership_nature="Direct",
        source_url="https://sec.gov",
        is_amendment=False,
        date_of_orig_submission=None,
        raw_payload={},
        source="SEC",
        record_hash="hash2",
        form_type="4",
    )

    store_bulk_insider_transactions(db_url, [tx1, tx2])

    return db_url


def test_query_insider_transactions(test_db):
    results = query_insider_transactions(test_db, tickers=["AAPL"])
    assert len(results) == 2
    assert results[0].ticker == "AAPL"

    results_filtered = query_insider_transactions(
        test_db,
        start_date="2024-01-16",
        transaction_codes=["P"],
    )
    assert len(results_filtered) == 1
    assert results_filtered[0].accession_number == "000002"


def test_get_market_prices_for_ticker(test_db):
    prices = get_market_prices_for_ticker(test_db, "AAPL")
    assert prices["2024-01-15"] == 150.0
    assert prices["2024-01-16"] == 155.0
    assert prices["2024-01-17"] == 160.0


def test_prepare_event_study_inputs_and_rejections(test_db):
    tx_valid = query_insider_transactions(test_db, accession_numbers=["000001"])[0]

    # Missing ticker tx
    tx_no_ticker = NormalizedBulkTransaction(
        accession_number="000003",
        issuer_cik="0000320193",
        issuer_name="Apple Inc.",
        ticker=None,
        reporting_owner_name="Cook Tim",
        reporting_owner_cik="0001214156",
        transaction_date="2024-01-15",
        filing_date="2024-01-16",
        transaction_code="S",
        security_title="Common Stock",
        shares=100.0,
        price_per_share=150.0,
        transaction_type="non_derivative",
        acquired_disposed="D",
        ownership_type="D",
        ownership_nature=None,
        source_url="https://sec.gov",
        is_amendment=False,
        date_of_orig_submission=None,
        raw_payload={},
        source="SEC",
        record_hash="hash3",
        form_type="4",
    )

    # Missing price tx
    tx_no_price = NormalizedBulkTransaction(
        accession_number="000004",
        issuer_cik="0000320193",
        issuer_name="Apple Inc.",
        ticker="AAPL",
        reporting_owner_name="Cook Tim",
        reporting_owner_cik="0001214156",
        transaction_date="2020-01-01",  # No prices stored for 2020
        filing_date="2020-01-02",
        transaction_code="S",
        security_title="Common Stock",
        shares=100.0,
        price_per_share=100.0,
        transaction_type="non_derivative",
        acquired_disposed="D",
        ownership_type="D",
        ownership_nature=None,
        source_url="https://sec.gov",
        is_amendment=False,
        date_of_orig_submission=None,
        raw_payload={},
        source="SEC",
        record_hash="hash4",
        form_type="4",
    )

    adapter_res = prepare_event_study_inputs(
        test_db,
        [tx_valid, tx_no_ticker, tx_no_price],
        horizon_days=1,
    )

    assert len(adapter_res.valid_events) == 1
    assert adapter_res.valid_events[0].symbol == "AAPL"

    reasons = [r.reason for r in adapter_res.rejections]
    assert REJECTION_MISSING_TICKER in reasons
    assert REJECTION_MISSING_PRICE in reasons


def test_point_in_time_safety_and_acquired_disposed_filter(test_db):
    # Verify point-in-time filing_date safety: event_date MUST be filing_date (2024-01-16), not transaction_date (2024-01-15)
    txs_d = query_insider_transactions(test_db, acquired_disposed="D")
    assert len(txs_d) == 1
    assert txs_d[0].accession_number == "000001"

    txs_a = query_insider_transactions(test_db, acquired_disposed="A")
    assert len(txs_a) == 1
    assert txs_a[0].accession_number == "000002"

    adapter_res = prepare_event_study_inputs(test_db, txs_d, horizon_days=1)
    event = adapter_res.valid_events[0]

    # Point-in-time safety check: event_date uses public filing_date 2024-01-16, event_price is 155.0
    assert event.event_date == "2024-01-16"
    assert event.event_price == 155.0
    assert event.transaction.transaction_date == "2024-01-15"


def test_amendment_supersession_deduplication_and_same_day_legitimate_txs(test_db):
    orig = NormalizedBulkTransaction(
        accession_number="000010-ORIG",
        issuer_cik="0000320193",
        issuer_name="Apple Inc.",
        ticker="AAPL",
        reporting_owner_name="Cook Tim",
        reporting_owner_cik="0001214156",
        transaction_date="2024-01-15",
        filing_date="2024-01-16",
        transaction_code="S",
        security_title="Common Stock",
        shares=1000.0,
        price_per_share=150.0,
        transaction_type="non_derivative",
        acquired_disposed="D",
        ownership_type="D",
        ownership_nature="Direct",
        source_url="https://sec.gov",
        is_amendment=False,
        date_of_orig_submission=None,
        raw_payload={},
        source="SEC",
        record_hash="hash_orig",
        form_type="4",
    )

    amend = NormalizedBulkTransaction(
        accession_number="000010-AMEND",
        issuer_cik="0000320193",
        issuer_name="Apple Inc.",
        ticker="AAPL",
        reporting_owner_name="Cook Tim",
        reporting_owner_cik="0001214156",
        transaction_date="2024-01-15",
        filing_date="2024-01-17",
        transaction_code="S",
        security_title="Common Stock",
        shares=1200.0,  # Amended shares count
        price_per_share=150.0,
        transaction_type="non_derivative",
        acquired_disposed="D",
        ownership_type="D",
        ownership_nature="Direct",
        source_url="https://sec.gov",
        is_amendment=True,
        date_of_orig_submission="2024-01-16",
        raw_payload={},
        source="SEC",
        record_hash="hash_amend",
        form_type="4/A",
    )

    # 1. Store both in database
    store_bulk_insider_transactions(test_db, [orig, amend])

    # 2. Verify date_of_orig_submission survives database storage -> research query retrieval
    queried_txs = query_insider_transactions(test_db, accession_numbers=["000010-AMEND", "000010-ORIG"])
    assert len(queried_txs) == 2
    amend_queried = [t for t in queried_txs if t.accession_number == "000010-AMEND"][0]
    assert amend_queried.is_amendment is True
    assert amend_queried.date_of_orig_submission == "2024-01-16"

    # 3. Adapter deduplication: selects only 1 effective research event (the amendment)
    adapter_res = prepare_event_study_inputs(test_db, queried_txs, horizon_days=1)
    assert len(adapter_res.valid_events) == 1
    assert adapter_res.valid_events[0].transaction.record_hash == "hash_amend"
    assert adapter_res.valid_events[0].transaction.shares == 1200.0

    rejections = adapter_res.rejections
    assert len(rejections) == 1
    assert rejections[0].reason == "REJECTED_AMENDMENT_SUPERSEDED"
    assert rejections[0].record_hash == "hash_orig"

    # 4. Verify two legitimate same-day non-amended transactions are NOT incorrectly collapsed
    legit_tx1 = NormalizedBulkTransaction(
        accession_number="000020",
        issuer_cik="0000320193",
        issuer_name="Apple Inc.",
        ticker="AAPL",
        reporting_owner_name="Cook Tim",
        reporting_owner_cik="0001214156",
        transaction_date="2024-01-15",
        filing_date="2024-01-16",
        transaction_code="S",
        security_title="Common Stock",
        shares=500.0,
        price_per_share=150.0,
        transaction_type="non_derivative",
        acquired_disposed="D",
        ownership_type="D",
        ownership_nature="Direct",
        source_url="https://sec.gov",
        is_amendment=False,
        date_of_orig_submission=None,
        raw_payload={},
        source="SEC",
        record_hash="hash_legit1",
        form_type="4",
    )

    legit_tx2 = NormalizedBulkTransaction(
        accession_number="000021",
        issuer_cik="0000320193",
        issuer_name="Apple Inc.",
        ticker="AAPL",
        reporting_owner_name="Cook Tim",
        reporting_owner_cik="0001214156",
        transaction_date="2024-01-15",
        filing_date="2024-01-16",
        transaction_code="S",
        security_title="Common Stock",
        shares=300.0,
        price_per_share=150.0,
        transaction_type="non_derivative",
        acquired_disposed="D",
        ownership_type="D",
        ownership_nature="Direct",
        source_url="https://sec.gov",
        is_amendment=False,
        date_of_orig_submission=None,
        raw_payload={},
        source="SEC",
        record_hash="hash_legit2",
        form_type="4",
    )

    legit_res = prepare_event_study_inputs(test_db, [legit_tx1, legit_tx2], horizon_days=1)
    assert len(legit_res.valid_events) == 2
    assert len(legit_res.rejections) == 0


def test_event_study_and_backtest_conversion(test_db):
    txs = query_insider_transactions(test_db, accession_numbers=["000001"])
    adapter_res = prepare_event_study_inputs(test_db, txs, horizon_days=1)

    es_payloads = convert_events_to_event_study_payloads(adapter_res.valid_events)
    returns, summary = run_event_study(es_payloads, horizon_days=1)

    assert summary.event_count == 1
    assert len(returns) == 1
    # Point-in-time safety: filing_date is 2024-01-16 (price 155.0), next horizon price is 2024-01-17 (price 160.0)
    assert returns[0].event_price == 155.0
    assert returns[0].future_price == 160.0

    bt_trades = convert_events_to_backtest_trades(adapter_res.valid_events, holding_periods=1)
    assert len(bt_trades) == 1
    assert bt_trades[0]["symbol"] == "AAPL"
    assert bt_trades[0]["entry_price"] == 155.0
