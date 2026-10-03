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

    # Insert market prices
    store_market_price(
        db_url,
        symbol="AAPL",
        price_date="2024-01-15",
        open_price=150.0,
        high=152.0,
        low=149.0,
        close=150.0,
        adjusted_close=150.0,
        volume=100000.0,
        source="TEST",
        raw_payload={"close": 150.0},
    )
    store_market_price(
        db_url,
        symbol="AAPL",
        price_date="2024-01-16",
        open_price=155.0,
        high=157.0,
        low=154.0,
        close=155.0,
        adjusted_close=155.0,
        volume=100000.0,
        source="TEST",
        raw_payload={"close": 155.0},
    )
    store_market_price(
        db_url,
        symbol="AAPL",
        price_date="2024-01-17",
        open_price=160.0,
        high=162.0,
        low=159.0,
        close=160.0,
        adjusted_close=160.0,
        volume=100000.0,
        source="TEST",
        raw_payload={"close": 160.0},
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


def test_event_study_and_backtest_conversion(test_db):
    txs = query_insider_transactions(test_db, accession_numbers=["000001"])
    adapter_res = prepare_event_study_inputs(test_db, txs, horizon_days=1)

    es_payloads = convert_events_to_event_study_payloads(adapter_res.valid_events)
    returns, summary = run_event_study(es_payloads, horizon_days=1)

    assert summary.event_count == 1
    assert len(returns) == 1
    assert returns[0].event_price == 150.0
    assert returns[0].future_price == 155.0

    bt_trades = convert_events_to_backtest_trades(adapter_res.valid_events, holding_periods=1)
    assert len(bt_trades) == 1
    assert bt_trades[0]["symbol"] == "AAPL"
    assert bt_trades[0]["entry_price"] == 150.0
