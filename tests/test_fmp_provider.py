"""
Comprehensive unit tests for FMP Market Data Provider, Factory, Ticker Universe,
Acquisition CLI Workflows, and Corporate Actions Pipeline.

All network requests are mocked. No real external API requests.
"""

from __future__ import annotations

import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from config.environment import EnvironmentConfigurationError, load_environment
from data.corporate_actions_acquisition import (
    CorporateActionsAcquisitionService,
)
from data.corporate_actions_client import (
    CorporateActionsRequestError,
    CorporateActionsResponseError,
)
from data.corporate_actions_loader import (
    CorporateActionsLoadError,
    load_corporate_actions,
    load_corporate_actions_detailed,
)
from data.market_data_client import (
    MarketDataRequestError,
    MarketDataResponseError,
)
from data.market_data_provider_factory import get_market_data_provider
from data.providers.fmp_corporate_actions import FMPCorporateActionsProvider
from data.providers.fmp_market_data import FMPMarketDataProvider
from database.connection import connect, initialize_database, is_postgresql_url
from research.ticker_universe import get_ticker_universe
from scripts.acquire_corporate_actions import (
    parse_args as parse_ca_args,
    run_corporate_actions_acquisition,
)
from scripts.acquire_market_data import parse_args, run_acquisition
from storage.repository import count_records, store_corporate_action


# ==============================================================================
# 1. FMP MARKET DATA PROVIDER TESTS
# ==============================================================================

def test_fmp_provider_source_and_batch_properties() -> None:
    provider = FMPMarketDataProvider(api_key="test_key")
    assert provider.source == "fmp"
    assert provider.supports_batch is False


def test_fmp_provider_requires_api_key() -> None:
    provider = FMPMarketDataProvider(api_key="")
    with pytest.raises(MarketDataRequestError, match="FMP_API_KEY is required"):
        provider.get_historical_prices(symbol="AAPL")


def test_fmp_provider_endpoint_and_url_construction() -> None:
    """Verifies market-data request uses /historical-price-eod/non-split-adjusted."""
    provider = FMPMarketDataProvider(api_key="SECRET_KEY_123")
    with patch("data.providers.fmp_market_data.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps([
            {"symbol": "AAPL", "date": "2024-01-02", "open": 180.0, "high": 185.0, "low": 179.0, "close": 184.0, "volume": 1000}
        ]).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        records = provider.get_historical_prices(
            symbol="aapl",
            start_date="2024-01-01",
            end_date="2024-01-05",
        )

        assert len(records) == 1
        req = mock_urlopen.call_args[0][0]
        assert "symbol=AAPL" in req.full_url
        assert "from=2024-01-01" in req.full_url
        assert "to=2024-01-05" in req.full_url
        assert "apikey=SECRET_KEY_123" in req.full_url
        assert "/historical-price-eod/non-split-adjusted" in req.full_url


def test_fmp_provider_unadjusted_close_and_no_adjusted_close_substitution() -> None:
    """Verifies close is taken as unadjusted close and adjusted_close is NOT invented when absent."""
    provider = FMPMarketDataProvider(api_key="dummy_key")
    raw_json = json.dumps({
        "symbol": "MSFT",
        "historical": [
            {"date": "2024-01-02", "open": 370.0, "high": 375.0, "low": 369.0, "close": 374.0, "volume": 5000}
        ]
    }).encode("utf-8")

    with patch("data.providers.fmp_market_data.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = raw_json
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        records = provider.get_historical_prices(symbol="MSFT")
        assert len(records) == 1
        assert records[0]["symbol"] == "MSFT"
        assert records[0]["price_date"] == "2024-01-02"
        assert records[0]["open"] == 370.0
        assert records[0]["close"] == 374.0
        assert records[0]["adjusted_close"] is None


def test_fmp_provider_explicit_adjusted_close_preserved() -> None:
    """Verifies explicit adjusted-close data remains separate when supplied."""
    provider = FMPMarketDataProvider(api_key="dummy_key")
    raw_json = json.dumps([
        {"symbol": "AAPL", "date": "2024-01-02", "open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "adjClose": 103.5, "volume": 1000}
    ]).encode("utf-8")

    with patch("data.providers.fmp_market_data.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = raw_json
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        records = provider.get_historical_prices(symbol="AAPL")
        assert records[0]["close"] == 104.0
        assert records[0]["adjusted_close"] == 103.5


def test_fmp_provider_valid_empty_response() -> None:
    provider = FMPMarketDataProvider(api_key="dummy_key")

    with patch("data.providers.fmp_market_data.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"[]"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        records = provider.get_historical_prices(symbol="UNKNOWN")
        assert records == []


def test_fmp_provider_error_payload_rejection() -> None:
    provider = FMPMarketDataProvider(api_key="dummy_key")
    error_json = json.dumps({"Error Message": "Invalid API KEY."}).encode("utf-8")

    with patch("data.providers.fmp_market_data.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = error_json
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with pytest.raises(MarketDataResponseError, match="FMP provider error"):
            provider.get_historical_prices(symbol="AAPL")


def test_fmp_provider_http_failure_and_key_masking() -> None:
    secret_key = "TOP_SECRET_API_KEY_999"
    provider = FMPMarketDataProvider(api_key=secret_key)

    with patch("data.providers.fmp_market_data.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = HTTPError(
            url=f"https://financialmodelingprep.com/stable/historical-price-eod/non-split-adjusted?symbol=AAPL&apikey={secret_key}",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=None,
        )

        with pytest.raises(MarketDataRequestError) as exc_info:
            provider.get_historical_prices(symbol="AAPL")

        err_msg = str(exc_info.value)
        assert secret_key not in err_msg
        assert "HTTP 401" in err_msg


def test_fmp_provider_invalid_json() -> None:
    provider = FMPMarketDataProvider(api_key="dummy_key")

    with patch("data.providers.fmp_market_data.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<html>404 Not Found</html>"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with pytest.raises(MarketDataResponseError, match="not valid JSON"):
            provider.get_historical_prices(symbol="AAPL")


def test_fmp_provider_batch_not_implemented() -> None:
    provider = FMPMarketDataProvider(api_key="dummy_key")
    with pytest.raises(NotImplementedError, match="does not support batch"):
        provider.get_historical_prices_batch(symbols=["AAPL", "MSFT"])


# ==============================================================================
# 2. PROVIDER FACTORY TESTS
# ==============================================================================

def test_provider_factory_fmp_selection() -> None:
    settings = load_environment({"SEC_USER_AGENT": "test/1.0", "FMP_API_KEY": "fmp_key_abc"})
    provider = get_market_data_provider("fmp", settings=settings)
    assert isinstance(provider, FMPMarketDataProvider)
    assert provider.source == "fmp"
    assert provider.api_key == "fmp_key_abc"


def test_provider_factory_unknown_provider_rejection() -> None:
    with pytest.raises(ValueError, match="Unknown or unsupported market data provider"):
        get_market_data_provider("unknown_vendor")


# ==============================================================================
# 3. TICKER UNIVERSE HELPER TESTS
# ==============================================================================

def test_ticker_universe_normalization_deduplication_ordering(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/ticker_test.db"
    initialize_database(db_url)

    with connect(db_url) as conn:
        conn.execute("""
            INSERT INTO insider_transactions (source, accession_number, issuer_cik, ticker, filing_date, transaction_date, record_hash, created_at)
            VALUES
                ('sec', 'acc1', 'cik1', ' msft ', '2006-01-05', '2006-01-04', 'hash1', 'now'),
                ('sec', 'acc2', 'cik2', 'AAPL', '2006-01-06', '2006-01-05', 'hash2', 'now'),
                ('sec', 'acc3', 'cik3', 'aapl', '2006-01-07', '2006-01-06', 'hash3', 'now'),
                ('sec', 'acc4', 'cik4', NULL, '2006-01-08', '2006-01-07', 'hash4', 'now'),
                ('sec', 'acc5', 'cik5', '  ', '2006-01-09', '2006-01-08', 'hash5', 'now'),
                ('sec', 'acc6', 'cik6', 'GOOG', '2006-02-01', '2006-02-01', 'hash6', 'now')
        """)
        conn.commit()

    res = get_ticker_universe(db_url, start_date="2006-01-01", end_date="2006-01-10")
    assert res.tickers == ("AAPL", "MSFT")
    assert res.unique_ticker_count == 2
    assert res.source_transaction_count == 4


# ==============================================================================
# 4. ACQUISITION WORKFLOW TESTS
# ==============================================================================

def test_acquisition_workflow_controlled_symbols(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/acq_cli_test.db"
    initialize_database(db_url)

    mock_provider = MagicMock()
    mock_provider.source = "fmp"
    mock_provider.supports_batch = False
    mock_provider.get_historical_prices.return_value = [
        {"symbol": "AAPL", "date": "2006-01-03", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.5, "volume": 1000}
    ]

    args = parse_args([
        "--provider", "fmp",
        "--symbols", "AAPL",
        "--start-date", "2006-01-03",
        "--end-date", "2006-01-10",
        "--database-url", db_url,
    ])

    env = load_environment({"SEC_USER_AGENT": "test/1.0", "FMP_API_KEY": "test_key"})

    with patch("scripts.acquire_market_data.load_environment", return_value=env):
        with patch("scripts.acquire_market_data.get_market_data_provider", return_value=mock_provider):
            report, count = run_acquisition(args)

            assert report.records_received == 1
            assert report.records_inserted == 1
            assert report.requested_symbols == ("AAPL",)
            assert report.successful_symbols == ("AAPL",)


def test_acquisition_workflow_date_validation() -> None:
    args = parse_args([
        "--start-date", "2024-01-10",
        "--end-date", "2024-01-01",
        "--symbols", "AAPL",
    ])
    with patch("scripts.acquire_market_data.load_environment") as mock_env:
        mock_env.return_value = load_environment({"SEC_USER_AGENT": "test/1.0", "FMP_API_KEY": "key"})
        with pytest.raises(ValueError, match="cannot be later than"):
            run_acquisition(args)


# ==============================================================================
# 5. STORAGE-LEVEL CORPORATE ACTION TESTS
# ==============================================================================

class MockConnectionWrapper:
    """Wrapper around a real database connection to simulate specific execution errors."""

    def __init__(self, real_conn, err_to_raise=None):
        self._conn = real_conn
        self._err = err_to_raise

    def execute(self, sql, params=()):
        if "INSERT INTO corporate_actions" in sql and self._err is not None:
            raise self._err
        return self._conn.execute(sql, params)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._conn.__exit__(exc_type, exc_val, exc_tb)


def test_store_corporate_action_outcomes(tmp_path) -> None:
    """Storage-level tests for store_corporate_action (INSERTED, DUPLICATE, CONFLICT)."""
    db_url = f"sqlite:///{tmp_path}/ca_storage_test.db"
    initialize_database(db_url)

    raw1 = {"symbol": "AAPL", "action_type": "split", "action_date": "2020-08-31", "ratio": "4:1", "source": "fmp"}
    raw2 = {"symbol": "AAPL", "action_type": "split", "action_date": "2020-08-31", "ratio": "5:1", "source": "fmp"}

    # 1. New identity -> INSERTED
    hash1, outcome1 = store_corporate_action(
        db_url,
        symbol="AAPL",
        action_type="split",
        action_date="2020-08-31",
        ratio="4:1",
        cash_amount=None,
        source="fmp",
        raw_payload=raw1,
    )
    assert outcome1 == "INSERTED"
    assert count_records(db_url, "corporate_actions") == 1

    # 2. Same identity + same content -> DUPLICATE
    hash2, outcome2 = store_corporate_action(
        db_url,
        symbol="AAPL",
        action_type="split",
        action_date="2020-08-31",
        ratio="4:1",
        cash_amount=None,
        source="fmp",
        raw_payload=raw1,
    )
    assert outcome2 == "DUPLICATE"
    assert hash1 == hash2
    assert count_records(db_url, "corporate_actions") == 1

    # 3. Same identity + different content -> CONFLICT
    hash3, outcome3 = store_corporate_action(
        db_url,
        symbol="AAPL",
        action_type="split",
        action_date="2020-08-31",
        ratio="5:1",
        cash_amount=None,
        source="fmp",
        raw_payload=raw2,
    )
    assert outcome3 == "CONFLICT"
    assert count_records(db_url, "corporate_actions") == 1  # Row count remains strictly 1!


def test_store_corporate_action_unique_constraint_race_cases(tmp_path) -> None:
    """
    Tests unique-constraint race condition handling:
      - Case A (same content): raises IntegrityError -> returns DUPLICATE
      - Case B (different content): raises IntegrityError -> returns CONFLICT
    """
    db_url = f"sqlite:///{tmp_path}/ca_race_cases_test.db"
    initialize_database(db_url)

    raw1 = {"symbol": "AAPL", "action_type": "split", "action_date": "2020-08-31", "ratio": "4:1", "source": "fmp"}

    # Seed initial row
    hash1, outcome1 = store_corporate_action(
        db_url,
        symbol="AAPL",
        action_type="split",
        action_date="2020-08-31",
        ratio="4:1",
        cash_amount=None,
        source="fmp",
        raw_payload=raw1,
    )
    assert outcome1 == "INSERTED"

    # Case A: Simulated race on exact same payload raising IntegrityError
    real_connect = connect
    integrity_err = sqlite3.IntegrityError("UNIQUE constraint failed: corporate_actions.symbol, corporate_actions.action_type, corporate_actions.action_date, corporate_actions.source")

    def mock_connect_a(url):
        return MockConnectionWrapper(real_connect(url), err_to_raise=integrity_err)

    with patch("storage.repository.connect", side_effect=mock_connect_a):
        hash_res_a, outcome_a = store_corporate_action(
            db_url,
            symbol="AAPL",
            action_type="split",
            action_date="2020-08-31",
            ratio="4:1",
            cash_amount=None,
            source="fmp",
            raw_payload=raw1,
        )
        assert outcome_a == "DUPLICATE"
        assert hash_res_a == hash1
        assert count_records(db_url, "corporate_actions") == 1

    # Case B: Simulated race on same identity with DIFFERENT payload raising IntegrityError
    raw_diff = {"symbol": "AAPL", "action_type": "split", "action_date": "2020-08-31", "ratio": "10:1", "source": "fmp"}

    def mock_connect_b(url):
        return MockConnectionWrapper(real_connect(url), err_to_raise=sqlite3.IntegrityError("UNIQUE constraint failed"))

    with patch("storage.repository.connect", side_effect=mock_connect_b):
        hash_res_b, outcome_b = store_corporate_action(
            db_url,
            symbol="AAPL",
            action_type="split",
            action_date="2020-08-31",
            ratio="10:1",
            cash_amount=None,
            source="fmp",
            raw_payload=raw_diff,
        )
        assert outcome_b == "CONFLICT"
        assert count_records(db_url, "corporate_actions") == 1


def test_store_corporate_action_non_integrity_failure_propagates(tmp_path) -> None:
    """Verifies that non-integrity database exceptions (e.g., OperationalError) propagate directly as failures."""
    db_url = f"sqlite:///{tmp_path}/ca_op_err_test.db"
    initialize_database(db_url)

    raw1 = {"symbol": "AAPL", "action_type": "split", "action_date": "2020-08-31", "ratio": "4:1", "source": "fmp"}

    real_connect = connect
    op_err = sqlite3.OperationalError("database is locked")

    def mock_connect_op(url):
        return MockConnectionWrapper(real_connect(url), err_to_raise=op_err)

    with patch("storage.repository.connect", side_effect=mock_connect_op):
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            store_corporate_action(
                db_url,
                symbol="AAPL",
                action_type="split",
                action_date="2020-08-31",
                ratio="4:1",
                cash_amount=None,
                source="fmp",
                raw_payload=raw1,
            )


def test_real_postgres_corporate_action_concurrency() -> None:
    """
    Real PostgreSQL Concurrency Integration Test.
    Executed only if POSTGRES_TEST_URL or DATABASE_URL targeting PostgreSQL is available.
    """
    pg_url = os.getenv("POSTGRES_TEST_URL") or os.getenv("DATABASE_URL", "")
    if not is_postgresql_url(pg_url):
        pytest.skip("PostgreSQL test database not available for live concurrency testing.")

    initialize_database(pg_url)

    # Cleanup any pre-existing test corporate actions for AAPL on 2020-08-31
    with connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM corporate_actions WHERE symbol = %s AND action_date = %s",
                ("AAPL", "2020-08-31")
            )
            cur.execute(
                "DELETE FROM provenance WHERE record_type = %s AND record_id IN (SELECT record_hash FROM corporate_actions WHERE symbol = %s)",
                ("corporate_action", "AAPL")
            )
        conn.commit()

    raw_same = {"symbol": "AAPL", "action_type": "split", "action_date": "2020-08-31", "ratio": "4:1", "source": "fmp"}
    raw_diff = {"symbol": "AAPL", "action_type": "split", "action_date": "2020-08-31", "ratio": "5:1", "source": "fmp"}

    # Case A: Concurrent same content -> 1 INSERTED, 1 DUPLICATE, exactly 1 DB row
    def worker_same():
        return store_corporate_action(
            pg_url,
            symbol="AAPL",
            action_type="split",
            action_date="2020-08-31",
            ratio="4:1",
            cash_amount=None,
            source="fmp",
            raw_payload=raw_same,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker_same)
        f2 = executor.submit(worker_same)
        res1 = f1.result()
        res2 = f2.result()

    outcomes_same = {res1[1], res2[1]}
    assert outcomes_same == {"INSERTED", "DUPLICATE"}

    with connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM corporate_actions WHERE symbol = %s AND action_date = %s", ("AAPL", "2020-08-31"))
            count_row = cur.fetchone()
            assert count_row[0] == 1

    # Case B: Concurrent different content against existing row -> CONFLICT
    def worker_diff():
        return store_corporate_action(
            pg_url,
            symbol="AAPL",
            action_type="split",
            action_date="2020-08-31",
            ratio="5:1",
            cash_amount=None,
            source="fmp",
            raw_payload=raw_diff,
        )

    with ThreadPoolExecutor(max_workers=1) as executor:
        f_diff = executor.submit(worker_diff)
        res_diff = f_diff.result()

    assert res_diff[1] == "CONFLICT"

    with connect(pg_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM corporate_actions WHERE symbol = %s AND action_date = %s", ("AAPL", "2020-08-31"))
            count_row = cur.fetchone()
            assert count_row[0] == 1  # Row count remains strictly 1!

            cur.execute("DELETE FROM corporate_actions WHERE symbol = %s AND action_date = %s", ("AAPL", "2020-08-31"))
        conn.commit()


# ==============================================================================
# 6. CORPORATE ACTIONS PROVIDER & PIPELINE TESTS
# ==============================================================================

def test_fmp_corporate_actions_endpoints_and_normalization() -> None:
    """Verifies corporate split uses /splits and corporate dividend uses /dividends."""
    ca_provider = FMPCorporateActionsProvider(api_key="ca_key")

    splits_json = json.dumps([
        {"symbol": "AAPL", "date": "2020-08-31", "numerator": 4, "denominator": 1}
    ]).encode("utf-8")

    divs_json = json.dumps([
        {"symbol": "AAPL", "date": "2023-11-10", "dividend": 0.24}
    ]).encode("utf-8")

    with patch("data.providers.fmp_corporate_actions.urlopen") as mock_urlopen:
        mock_resp_splits = MagicMock()
        mock_resp_splits.status = 200
        mock_resp_splits.read.return_value = splits_json

        mock_resp_divs = MagicMock()
        mock_resp_divs.status = 200
        mock_resp_divs.read.return_value = divs_json

        mock_urlopen.return_value.__enter__.side_effect = [mock_resp_splits, mock_resp_divs]

        splits = ca_provider.get_splits(symbol="AAPL")
        req_splits = mock_urlopen.call_args_list[0][0][0]
        assert "/splits" in req_splits.full_url
        assert splits[0]["symbol"] == "AAPL"
        assert splits[0]["action_type"] == "split"
        assert splits[0]["action_date"] == "2020-08-31"
        assert splits[0]["ratio"] == "4:1"

        divs = ca_provider.get_dividends(symbol="AAPL")
        req_divs = mock_urlopen.call_args_list[1][0][0]
        assert "/dividends" in req_divs.full_url
        assert divs[0]["symbol"] == "AAPL"
        assert divs[0]["action_type"] == "dividend"
        assert divs[0]["action_date"] == "2023-11-10"


def test_fmp_corporate_actions_strict_tests_a_b_c(tmp_path) -> None:
    """
    Strict Test A, Test B, and Test C for Corporate Actions Acquisition.
    """
    db_url = f"sqlite:///{tmp_path}/ca_strict_test.db"
    initialize_database(db_url)

    ca_provider = FMPCorporateActionsProvider(api_key="ca_key")
    service = CorporateActionsAcquisitionService(ca_provider)

    splits_json_a = json.dumps([
        {"symbol": "AAPL", "date": "2020-08-31", "numerator": 4, "denominator": 1}
    ]).encode("utf-8")

    splits_json_c = json.dumps([
        {"symbol": "AAPL", "date": "2020-08-31", "numerator": 5, "denominator": 1}
    ]).encode("utf-8")

    empty_divs_json = json.dumps([]).encode("utf-8")

    # TEST A — First acquisition
    with patch("data.providers.fmp_corporate_actions.urlopen") as mock_urlopen:
        m1 = MagicMock()
        m1.status = 200
        m1.read.return_value = splits_json_a

        m2 = MagicMock()
        m2.status = 200
        m2.read.return_value = empty_divs_json

        mock_urlopen.return_value.__enter__.side_effect = [m1, m2]

        report_a = service.acquire_corporate_actions(db_url, symbols=["AAPL"])

        assert count_records(db_url, "corporate_actions") == 1
        assert count_records(db_url, "provenance") == 1
        assert report_a.records_inserted == 1
        assert report_a.records_duplicate == 0
        assert report_a.records_conflict == 0

    # TEST B — Exact repeat acquisition
    with patch("data.providers.fmp_corporate_actions.urlopen") as mock_urlopen:
        m1 = MagicMock()
        m1.status = 200
        m1.read.return_value = splits_json_a

        m2 = MagicMock()
        m2.status = 200
        m2.read.return_value = empty_divs_json

        mock_urlopen.return_value.__enter__.side_effect = [m1, m2]

        report_b = service.acquire_corporate_actions(db_url, symbols=["AAPL"])

        assert count_records(db_url, "corporate_actions") == 1  # Row count remains strictly 1!
        assert count_records(db_url, "provenance") == 1       # Provenance count remains strictly 1!
        assert report_b.records_inserted == 0
        assert report_b.records_duplicate == 1
        assert report_b.records_conflict == 0

    # TEST C — Same identity, changed content
    with patch("data.providers.fmp_corporate_actions.urlopen") as mock_urlopen:
        m1 = MagicMock()
        m1.status = 200
        m1.read.return_value = splits_json_c

        m2 = MagicMock()
        m2.status = 200
        m2.read.return_value = empty_divs_json

        mock_urlopen.return_value.__enter__.side_effect = [m1, m2]

        report_c = service.acquire_corporate_actions(db_url, symbols=["AAPL"])

        assert count_records(db_url, "corporate_actions") == 1  # Row count remains strictly 1!
        assert count_records(db_url, "provenance") == 1       # Provenance count remains strictly 1!
        assert report_c.records_inserted == 0
        assert report_c.records_duplicate == 0
        assert report_c.records_conflict == 1


def test_fmp_corporate_actions_test_d_irrelevant_provider_payload_difference(tmp_path) -> None:
    """
    TEST D — Two provider payloads with irrelevant extra fields producing the exact same normalized corporate action.
    """
    db_url = f"sqlite:///{tmp_path}/ca_test_d.db"
    initialize_database(db_url)

    ca_provider = FMPCorporateActionsProvider(api_key="ca_key")
    service = CorporateActionsAcquisitionService(ca_provider)

    # First payload: basic fields
    splits_json_1 = json.dumps([
        {"symbol": "AAPL", "date": "2020-08-31", "numerator": 4, "denominator": 1}
    ]).encode("utf-8")

    # Second payload: includes extra/irrelevant provider response fields (e.g. "label", "fetched_at")
    splits_json_2 = json.dumps([
        {"symbol": "AAPL", "date": "2020-08-31", "numerator": 4, "denominator": 1, "label": "4 for 1", "fetched_at": "12345"}
    ]).encode("utf-8")

    empty_divs_json = json.dumps([]).encode("utf-8")

    # 1. First acquisition
    with patch("data.providers.fmp_corporate_actions.urlopen") as mock_urlopen:
        m1 = MagicMock()
        m1.status = 200
        m1.read.return_value = splits_json_1
        m2 = MagicMock()
        m2.status = 200
        m2.read.return_value = empty_divs_json
        mock_urlopen.return_value.__enter__.side_effect = [m1, m2]

        report1 = service.acquire_corporate_actions(db_url, symbols=["AAPL"])
        assert report1.records_inserted == 1
        assert count_records(db_url, "corporate_actions") == 1

    # 2. Second acquisition with extra raw provider fields
    with patch("data.providers.fmp_corporate_actions.urlopen") as mock_urlopen:
        m1 = MagicMock()
        m1.status = 200
        m1.read.return_value = splits_json_2
        m2 = MagicMock()
        m2.status = 200
        m2.read.return_value = empty_divs_json
        mock_urlopen.return_value.__enter__.side_effect = [m1, m2]

        report2 = service.acquire_corporate_actions(db_url, symbols=["AAPL"])
        assert report2.records_inserted == 0
        assert report2.records_duplicate == 1
        assert count_records(db_url, "corporate_actions") == 1  # Normalized content hash match = DUPLICATE!


def test_fmp_corporate_actions_malformed_response_rejected(tmp_path) -> None:
    """Malformed provider response rejected without storage."""
    db_url = f"sqlite:///{tmp_path}/ca_malformed_test.db"
    initialize_database(db_url)

    ca_provider = FMPCorporateActionsProvider(api_key="ca_key")

    with patch("data.providers.fmp_corporate_actions.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"Error Message": "Invalid key"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with pytest.raises(CorporateActionsResponseError, match="Invalid key"):
            ca_provider.get_splits(symbol="AAPL")

        assert count_records(db_url, "corporate_actions") == 0


def test_fmp_corporate_actions_http_failure_reported(tmp_path) -> None:
    """Provider HTTP failure reported in acquisition service."""
    db_url = f"sqlite:///{tmp_path}/ca_fail_test.db"
    initialize_database(db_url)

    ca_provider = FMPCorporateActionsProvider(api_key="ca_key")

    with patch("data.providers.fmp_corporate_actions.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = HTTPError(
            url="https://financialmodelingprep.com/stable/splits?symbol=AAPL&apikey=ca_key",
            code=500,
            msg="Server Error",
            hdrs={},
            fp=None,
        )

        service = CorporateActionsAcquisitionService(ca_provider)
        report = service.acquire_corporate_actions(db_url, symbols=["AAPL"])

        assert report.provider_request_failures == 2
        assert len(report.failed_symbols) == 1


def test_corporate_actions_cli_empty_symbols_rejected() -> None:
    """Empty symbol list is rejected."""
    args = parse_ca_args(["--symbols", "  "])
    env = load_environment({"SEC_USER_AGENT": "test/1.0", "FMP_API_KEY": "key"})

    with patch("scripts.acquire_corporate_actions.load_environment", return_value=env):
        with pytest.raises(ValueError, match="non-empty --symbols argument is required"):
            run_corporate_actions_acquisition(args)
