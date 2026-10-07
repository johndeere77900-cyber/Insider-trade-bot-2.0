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
from storage.repository import (
    count_records,
    store_corporate_action,
    store_market_price,
)


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


def test_fmp_provider_actual_non_split_adjusted_shape_mapping() -> None:
    """
    Regression test verifying FMP's actual non-split-adjusted endpoint response shape
    containing adjOpen, adjHigh, adjLow, adjClose maps correctly to open, high, low, close
    with adjusted_close remaining None.
    """
    provider = FMPMarketDataProvider(api_key="dummy_key")
    raw_json = json.dumps([
        {
            "symbol": "AAPL",
            "date": "2025-12-31",
            "adjOpen": 273.06,
            "adjHigh": 273.68,
            "adjLow": 271.75,
            "adjClose": 271.86,
            "volume": 27293639,
        }
    ]).encode("utf-8")

    with patch("data.providers.fmp_market_data.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = raw_json
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        records = provider.get_historical_prices(symbol="AAPL")
        assert len(records) == 1
        rec = records[0]
        assert rec["symbol"] == "AAPL"
        assert rec["price_date"] == "2025-12-31"
        assert rec["open"] == 273.06
        assert rec["high"] == 273.68
        assert rec["low"] == 271.75
        assert rec["close"] == 271.86
        assert rec["volume"] == 27293639
        assert rec["adjusted_close"] is None


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


class MockRaceConnectionWrapper:
    """Simulates a race condition where initial SELECT sees nothing, but INSERT raises an error."""

    def __init__(self, real_conn, err_to_raise):
        self._conn = real_conn
        self._err = err_to_raise
        self._select_count = 0

    def execute(self, sql, params=()):
        if "SELECT record_hash" in sql and "FROM corporate_actions" in sql:
            self._select_count += 1
            if self._select_count == 1:
                class EmptyCursor:
                    def fetchone(self):
                        return None
                return EmptyCursor()

        if "INSERT INTO corporate_actions" in sql:
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
        return MockRaceConnectionWrapper(real_connect(url), err_to_raise=integrity_err)

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
        return MockRaceConnectionWrapper(real_connect(url), err_to_raise=sqlite3.IntegrityError("UNIQUE constraint failed: corporate_actions.symbol, corporate_actions.action_type, corporate_actions.action_date, corporate_actions.source"))

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


def test_unrelated_integrity_error_propagates(tmp_path) -> None:
    """
    Proves that an unrelated database IntegrityError (where the identity cannot
    be found post-exception) is NOT automatically converted to DUPLICATE or CONFLICT.
    """
    db_url = f"sqlite:///{tmp_path}/ca_unrelated_integrity_test.db"
    initialize_database(db_url)

    raw = {"symbol": "NEWTICKER", "action_type": "split", "action_date": "2024-01-01", "ratio": "2:1", "source": "fmp"}

    real_connect = connect
    integrity_err = sqlite3.IntegrityError("FOREIGN KEY constraint failed")

    def mock_connect_integrity(url):
        return MockConnectionWrapper(real_connect(url), err_to_raise=integrity_err)

    with patch("storage.repository.connect", side_effect=mock_connect_integrity):
        with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
            store_corporate_action(
                db_url,
                symbol="NEWTICKER",
                action_type="split",
                action_date="2024-01-01",
                ratio="2:1",
                cash_amount=None,
                source="fmp",
                raw_payload=raw,
            )


def test_unrelated_unique_integrity_error_does_not_mask_existing_identity(tmp_path) -> None:
    """
    Regression test proving that when a corporate-action identity ALREADY EXISTS,
    an unrelated IntegrityError (e.g. UNIQUE constraint on an unrelated table or foreign key)
    on a second write attempt is re-raised and NOT converted into DUPLICATE or CONFLICT.
    """
    db_url = f"sqlite:///{tmp_path}/ca_unrelated_unique_mask_test.db"
    initialize_database(db_url)

    raw1 = {"symbol": "AAPL", "action_type": "split", "action_date": "2020-08-31", "ratio": "4:1", "source": "fmp"}

    # 1. Insert a valid corporate action first
    h1, o1 = store_corporate_action(
        db_url,
        symbol="AAPL",
        action_type="split",
        action_date="2020-08-31",
        ratio="4:1",
        cash_amount=None,
        source="fmp",
        raw_payload=raw1,
    )
    assert o1 == "INSERTED"
    assert count_records(db_url, "corporate_actions") == 1

    # 2. Simulate an unrelated UNIQUE IntegrityError (e.g. on another_table.code) during write race
    real_connect = connect
    unrelated_unique_err = sqlite3.IntegrityError("UNIQUE constraint failed: another_table.code")

    def mock_connect_unrelated(url):
        return MockRaceConnectionWrapper(real_connect(url), err_to_raise=unrelated_unique_err)

    with patch("storage.repository.connect", side_effect=mock_connect_unrelated):
        with pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed: another_table.code"):
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

    # 3. Assert existing row remains unchanged
    with connect(db_url) as conn:
        cursor = conn.execute("SELECT ratio FROM corporate_actions WHERE symbol = 'AAPL' AND action_date = '2020-08-31'")
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "4:1"

    assert count_records(db_url, "corporate_actions") == 1


def test_postgresql_unrelated_constraint_on_corporate_actions_table_propagates(tmp_path) -> None:
    """
    Regression test proving that a PostgreSQL-style IntegrityError with table_name == 'corporate_actions'
    but an unrelated constraint_name (e.g. 'corporate_actions_some_other_unique_constraint') re-raises
    and is NOT converted to DUPLICATE or CONFLICT.
    """
    db_url = f"sqlite:///{tmp_path}/ca_pg_unrelated_constraint.db"
    initialize_database(db_url)

    raw1 = {"symbol": "AAPL", "action_type": "split", "action_date": "2020-08-31", "ratio": "4:1", "source": "fmp"}
    store_corporate_action(db_url, symbol="AAPL", action_type="split", action_date="2020-08-31", ratio="4:1", cash_amount=None, source="fmp", raw_payload=raw1)

    class MockPGDiag:
        table_name = "corporate_actions"
        constraint_name = "corporate_actions_some_other_unique_constraint"

    class MockPGUniqueViolation(Exception):
        pgcode = "23505"
        diag = MockPGDiag()

    real_connect = connect

    def mock_connect_pg(url):
        return MockRaceConnectionWrapper(real_connect(url), err_to_raise=MockPGUniqueViolation("Unrelated corporate_actions constraint"))

    with patch("storage.repository.PSYCOPG_INTEGRITY_ERRORS", (MockPGUniqueViolation,)), patch("storage.repository.INTEGRITY_ERRORS", (sqlite3.IntegrityError, MockPGUniqueViolation)):
        with patch("storage.repository.connect", side_effect=mock_connect_pg):
            with pytest.raises(MockPGUniqueViolation):
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

    assert count_records(db_url, "corporate_actions") == 1


def test_postgresql_expected_corporate_actions_identity_key_race_handled(tmp_path) -> None:
    """
    Regression test proving that a PostgreSQL-style UniqueViolation with table_name == 'corporate_actions'
    and constraint_name == 'corporate_actions_identity_key' IS recognized as expected identity race.
    """
    db_url = f"sqlite:///{tmp_path}/ca_pg_expected_race.db"
    initialize_database(db_url)

    raw1 = {"symbol": "AAPL", "action_type": "split", "action_date": "2020-08-31", "ratio": "4:1", "source": "fmp"}
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

    class MockPGDiag:
        table_name = "corporate_actions"
        constraint_name = "corporate_actions_identity_key"

    class MockPGUniqueViolation(Exception):
        pgcode = "23505"
        diag = MockPGDiag()

    real_connect = connect

    def mock_connect_pg(url):
        return MockRaceConnectionWrapper(real_connect(url), err_to_raise=MockPGUniqueViolation("Canonical identity race"))

    with patch("storage.repository.PSYCOPG_INTEGRITY_ERRORS", (MockPGUniqueViolation,)), patch("storage.repository.INTEGRITY_ERRORS", (sqlite3.IntegrityError, MockPGUniqueViolation)):
        with patch("storage.repository.connect", side_effect=mock_connect_pg):
            h_res, o_res = store_corporate_action(
                db_url,
                symbol="AAPL",
                action_type="split",
                action_date="2020-08-31",
                ratio="4:1",
                cash_amount=None,
                source="fmp",
                raw_payload=raw1,
            )
            assert o_res == "DUPLICATE"
            assert h_res == hash1


def test_postgresql_bare_23505_without_diagnostics_propagates(tmp_path) -> None:
    """
    Regression test proving that a PostgreSQL-style IntegrityError with SQLSTATE 23505
    where diag.table_name = None / "" and diag.constraint_name = None / "" re-raises
    and is NOT converted to DUPLICATE or CONFLICT.
    """
    db_url = f"sqlite:///{tmp_path}/ca_pg_bare_23505.db"
    initialize_database(db_url)

    raw1 = {"symbol": "AAPL", "action_type": "split", "action_date": "2020-08-31", "ratio": "4:1", "source": "fmp"}
    store_corporate_action(db_url, symbol="AAPL", action_type="split", action_date="2020-08-31", ratio="4:1", cash_amount=None, source="fmp", raw_payload=raw1)

    class MockPGDiagBare:
        table_name = None
        constraint_name = None

    class MockPGBareUniqueViolation(Exception):
        pgcode = "23505"
        diag = MockPGDiagBare()

    real_connect = connect

    def mock_connect_pg_bare(url):
        return MockRaceConnectionWrapper(real_connect(url), err_to_raise=MockPGBareUniqueViolation("Bare 23505"))

    with patch("storage.repository.PSYCOPG_INTEGRITY_ERRORS", (MockPGBareUniqueViolation,)), patch("storage.repository.INTEGRITY_ERRORS", (sqlite3.IntegrityError, MockPGBareUniqueViolation)):
        with patch("storage.repository.connect", side_effect=mock_connect_pg_bare):
            with pytest.raises(MockPGBareUniqueViolation):
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

    test_symbol = "TESTCONCURRENCY"
    test_date = "2020-08-31"

    def cleanup_test_data():
        with connect(pg_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT record_hash FROM corporate_actions WHERE symbol = %s AND action_date = %s",
                    (test_symbol, test_date)
                )
                rows = cur.fetchall()
                hashes = [r[0] for r in rows if r]

                for h in hashes:
                    cur.execute(
                        "DELETE FROM provenance WHERE record_type = %s AND record_id = %s",
                        ("corporate_action", h)
                    )
                cur.execute(
                    "DELETE FROM corporate_actions WHERE symbol = %s AND action_date = %s",
                    (test_symbol, test_date)
                )
            conn.commit()

            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM corporate_actions WHERE symbol = %s AND action_date = %s",
                    (test_symbol, test_date)
                )
                ca_count = cur.fetchone()[0]
                cur.execute(
                    "SELECT COUNT(*) FROM provenance WHERE record_type = %s AND record_id IN ("
                    "  SELECT record_hash FROM corporate_actions WHERE symbol = %s AND action_date = %s"
                    ")",
                    ("corporate_action", test_symbol, test_date)
                )
                prov_count = cur.fetchone()[0]
                assert ca_count == 0
                assert prov_count == 0

    cleanup_test_data()

    try:
        raw_same = {"symbol": test_symbol, "action_type": "split", "action_date": test_date, "ratio": "4:1", "source": "fmp"}
        raw_diff = {"symbol": test_symbol, "action_type": "split", "action_date": test_date, "ratio": "5:1", "source": "fmp"}

        # Case A: Two workers simultaneously attempt SAME identity + SAME content
        def worker_same():
            return store_corporate_action(
                pg_url,
                symbol=test_symbol,
                action_type="split",
                action_date=test_date,
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

        outcomes_same = sorted([res1[1], res2[1]])
        assert outcomes_same == ["DUPLICATE", "INSERTED"]

        with connect(pg_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM corporate_actions WHERE symbol = %s AND action_date = %s", (test_symbol, test_date))
                count_row = cur.fetchone()
                assert count_row[0] == 1

        # Case B: Two workers simultaneously attempt SAME identity + DIFFERENT content
        cleanup_test_data()

        def worker_diff_a():
            return store_corporate_action(
                pg_url,
                symbol=test_symbol,
                action_type="split",
                action_date=test_date,
                ratio="4:1",
                cash_amount=None,
                source="fmp",
                raw_payload=raw_same,
            )

        def worker_diff_b():
            return store_corporate_action(
                pg_url,
                symbol=test_symbol,
                action_type="split",
                action_date=test_date,
                ratio="5:1",
                cash_amount=None,
                source="fmp",
                raw_payload=raw_diff,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker_diff_a)
            f2 = executor.submit(worker_diff_b)
            res_a = f1.result()
            res_b = f2.result()

        outcomes_diff = sorted([res_a[1], res_b[1]])
        assert outcomes_diff == ["CONFLICT", "INSERTED"]

        with connect(pg_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT ratio FROM corporate_actions WHERE symbol = %s AND action_date = %s", (test_symbol, test_date))
                row = cur.fetchone()
                # Ensure the original stored row was not overwritten by conflicting payload
                assert row[0] in ("4:1", "5:1")

                cur.execute("SELECT COUNT(*) FROM corporate_actions WHERE symbol = %s AND action_date = %s", (test_symbol, test_date))
                count_row = cur.fetchone()
                assert count_row[0] == 1

                cur.execute(
                    "SELECT COUNT(*) FROM provenance WHERE record_type = %s AND record_id IN ("
                    "  SELECT record_hash FROM corporate_actions WHERE symbol = %s AND action_date = %s"
                    ")",
                    ("corporate_action", test_symbol, test_date)
                )
                prov_row = cur.fetchone()
                assert prov_row[0] == 1

    finally:
        cleanup_test_data()


def test_real_postgres_market_price_concurrency() -> None:
    """
    Real PostgreSQL Market Price Concurrency Integration Test.
    Executed only if POSTGRES_TEST_URL or DATABASE_URL targeting PostgreSQL is available.
    """
    pg_url = os.getenv("POSTGRES_TEST_URL") or os.getenv("DATABASE_URL", "")
    if not is_postgresql_url(pg_url):
        pytest.skip("PostgreSQL test database not available for live concurrency testing.")

    initialize_database(pg_url)

    test_symbol = "TESTPRICE"
    test_date = "2024-01-02"
    test_src = "test_src"

    def cleanup_test_data():
        with connect(pg_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM market_prices WHERE symbol = %s AND price_date = %s AND source = %s",
                    (test_symbol, test_date, test_src)
                )
            conn.commit()

    cleanup_test_data()

    try:
        # A. Same-content race
        def worker_same():
            return store_market_price(
                pg_url,
                symbol=test_symbol,
                price_date=test_date,
                open_price=100.0,
                high=105.0,
                low=99.0,
                close=104.0,
                adjusted_close=104.0,
                volume=1000.0,
                source=test_src,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker_same)
            f2 = executor.submit(worker_same)
            res1 = f1.result()
            res2 = f2.result()

        outcomes_same = sorted([res1[1], res2[1]])
        assert outcomes_same == ["DUPLICATE", "INSERTED"]

        with connect(pg_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM market_prices WHERE symbol = %s AND price_date = %s AND source = %s",
                    (test_symbol, test_date, test_src)
                )
                assert cur.fetchone()[0] == 1

        # B. Different-content race
        cleanup_test_data()

        def worker_diff_a():
            return store_market_price(
                pg_url,
                symbol=test_symbol,
                price_date=test_date,
                open_price=100.0,
                high=105.0,
                low=99.0,
                close=104.0,
                adjusted_close=104.0,
                volume=1000.0,
                source=test_src,
            )

        def worker_diff_b():
            return store_market_price(
                pg_url,
                symbol=test_symbol,
                price_date=test_date,
                open_price=100.0,
                high=105.0,
                low=99.0,
                close=120.0,
                adjusted_close=104.0,
                volume=1000.0,
                source=test_src,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(worker_diff_a)
            f2 = executor.submit(worker_diff_b)
            res_a = f1.result()
            res_b = f2.result()

        outcomes_diff = sorted([res_a[1], res_b[1]])
        assert outcomes_diff == ["CONFLICT", "INSERTED"]

        with connect(pg_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM market_prices WHERE symbol = %s AND price_date = %s AND source = %s",
                    (test_symbol, test_date, test_src)
                )
                assert cur.fetchone()[0] == 1

    finally:
        cleanup_test_data()


# ==============================================================================
# 6. CORPORATE ACTIONS PROVIDER & PIPELINE TESTS
# ==============================================================================

def test_mixed_outcome_accounting_equation(tmp_path) -> None:
    """
    Tests load_corporate_actions_detailed with a mixed batch to verify:
      - exactly one outcome per processed record: INSERTED, DUPLICATE, CONFLICT, REJECTED, FAILED
      - inserted + duplicate + conflict + rejected + failed == total_processed_records
      - provider request failures are NOT included in this equation.
    """
    db_url = f"sqlite:///{tmp_path}/ca_mixed_accounting.db"
    initialize_database(db_url)

    # 1. Seed an initial record for AAPL
    store_corporate_action(
        db_url,
        symbol="AAPL",
        action_type="split",
        action_date="2020-08-31",
        ratio="4:1",
        cash_amount=None,
        source="fmp",
        raw_payload={"symbol": "AAPL", "date": "2020-08-31", "ratio": "4:1"},
    )

    # Prepare mixed payload:
    # Record 0: MSFT split -> INSERTED
    # Record 1: AAPL split 4:1 -> DUPLICATE
    # Record 2: AAPL split 5:1 -> CONFLICT
    # Record 3: Invalid record (missing date) -> REJECTED
    # Record 4: Force storage failure -> FAILED
    mixed_payload = [
        {"symbol": "MSFT", "action_type": "split", "action_date": "2023-01-01", "ratio": "2:1"},
        {"symbol": "AAPL", "action_type": "split", "action_date": "2020-08-31", "ratio": "4:1"},
        {"symbol": "AAPL", "action_type": "split", "action_date": "2020-08-31", "ratio": "5:1"},
        {"symbol": "GOOG", "action_type": "split"},  # Missing action_date -> REJECTED
        {"symbol": "FAIL", "action_type": "split", "action_date": "2024-01-01", "ratio": "3:1"},  # Will trigger FAILED
    ]

    original_ingest = load_corporate_actions_detailed.__globals__["ingest_corporate_action"]

    def mock_ingest(db_url, record, source, source_reference):
        if record.get("symbol") == "FAIL":
            raise RuntimeError("Database forced write error")
        return original_ingest(db_url, record, source=source, source_reference=source_reference)

    with patch("data.corporate_actions_loader.ingest_corporate_action", side_effect=mock_ingest):
        outcomes = load_corporate_actions_detailed(
            db_url,
            mixed_payload,
            source="fmp",
            source_reference="test_ref",
        )

    assert len(outcomes) == 5

    inserted = sum(1 for o in outcomes if o.outcome == "INSERTED")
    duplicate = sum(1 for o in outcomes if o.outcome == "DUPLICATE")
    conflict = sum(1 for o in outcomes if o.outcome == "CONFLICT")
    rejected = sum(1 for o in outcomes if o.outcome == "REJECTED")
    failed = sum(1 for o in outcomes if o.outcome == "FAILED")

    assert inserted == 1
    assert duplicate == 1
    assert conflict == 1
    assert rejected == 1
    assert failed == 1

    # Exact accounting invariant
    total_processed = len(mixed_payload)
    assert inserted + duplicate + conflict + rejected + failed == total_processed


def test_corporate_actions_loader_malformed_item_isolated_as_rejected(tmp_path) -> None:
    """
    Regression test proving that a response containing valid, malformed, valid items
    isolates the malformed item as REJECTED without aborting the valid records.
    """
    db_url = f"sqlite:///{tmp_path}/ca_malformed_isolated.db"
    initialize_database(db_url)

    payload = [
        {"symbol": "AAPL", "action_type": "split", "action_date": "2020-08-31", "ratio": "4:1"},
        "NOT_A_DICTIONARY",  # Malformed item
        {"symbol": "MSFT", "action_type": "split", "action_date": "2023-01-01", "ratio": "2:1"},
    ]

    outcomes = load_corporate_actions_detailed(db_url, payload, source="fmp")
    assert len(outcomes) == 3
    assert outcomes[0].outcome == "INSERTED"
    assert outcomes[1].outcome == "REJECTED"
    assert outcomes[2].outcome == "INSERTED"
    assert count_records(db_url, "corporate_actions") == 2


def test_symbol_status_semantics_success_partial_failed(tmp_path) -> None:
    """
    Verifies SUCCESS, PARTIAL, and FAILED symbol status semantics in CorporateActionsAcquisitionService.
    """
    db_url = f"sqlite:///{tmp_path}/ca_status_semantics.db"
    initialize_database(db_url)

    ca_provider = FMPCorporateActionsProvider(api_key="ca_key")
    service = CorporateActionsAcquisitionService(ca_provider)

    splits_ok = json.dumps([{"symbol": "AAPL", "date": "2020-08-31", "numerator": 4, "denominator": 1}]).encode("utf-8")
    empty_json = json.dumps([]).encode("utf-8")

    # 1. SUCCESS: 0 provider failures, 0 record failures/rejections/conflicts
    with patch("data.providers.fmp_corporate_actions.urlopen") as mock_urlopen:
        m1 = MagicMock(status=200, read=MagicMock(return_value=splits_ok))
        m2 = MagicMock(status=200, read=MagicMock(return_value=empty_json))
        mock_urlopen.return_value.__enter__.side_effect = [m1, m2]

        report = service.acquire_corporate_actions(db_url, symbols=["AAPL"])
        assert report.symbol_results[0].status == "SUCCESS"
        assert report.successful_symbols == ("AAPL",)

    # 2. PARTIAL: inserted > 0, but dividends endpoint raises HTTP 500 provider error
    with patch("data.providers.fmp_corporate_actions.urlopen") as mock_urlopen:
        m1 = MagicMock(status=200, read=MagicMock(return_value=splits_ok))
        mock_urlopen.return_value.__enter__.side_effect = [
            m1,
            HTTPError(url="http://test", code=500, msg="Server Error", hdrs={}, fp=None)
        ]

        report = service.acquire_corporate_actions(db_url, symbols=["AAPL"])
        assert report.symbol_results[0].status == "PARTIAL"
        assert report.failed_symbols == ("AAPL",)

    # 3. FAILED: 0 inserted/duplicates, provider error on splits & dividends
    with patch("data.providers.fmp_corporate_actions.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = HTTPError(url="http://test", code=500, msg="Server Error", hdrs={}, fp=None)

        report = service.acquire_corporate_actions(db_url, symbols=["MSFT"])
        assert report.symbol_results[0].status == "FAILED"
        assert report.failed_symbols == ("MSFT",)


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

    splits_json_1 = json.dumps([
        {"symbol": "AAPL", "date": "2020-08-31", "numerator": 4, "denominator": 1}
    ]).encode("utf-8")

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
        assert count_records(db_url, "corporate_actions") == 1


def test_fmp_corporate_actions_provider_vs_storage_failures(tmp_path) -> None:
    """
    Tests separation of provider request failures vs storage/database failures:
      1. Provider fetch HTTP failure -> provider_request_failures += 1, records_failed == 0.
      2. Provider fetch succeeds but database storage fails -> records_failed += 1, provider_request_failures == 0.
    """
    db_url = f"sqlite:///{tmp_path}/ca_boundary_test.db"
    initialize_database(db_url)

    ca_provider = FMPCorporateActionsProvider(api_key="ca_key")
    service = CorporateActionsAcquisitionService(ca_provider)

    # 1. Provider HTTP error
    with patch("data.providers.fmp_corporate_actions.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = HTTPError(
            url="https://financialmodelingprep.com/stable/splits?symbol=AAPL&apikey=ca_key",
            code=500,
            msg="Server Error",
            hdrs={},
            fp=None,
        )

        report1 = service.acquire_corporate_actions(db_url, symbols=["AAPL"])
        assert report1.provider_request_failures == 2  # 1 splits + 1 divs
        assert report1.records_failed == 0
        assert report1.symbol_results[0].status == "FAILED"

    # 2. Provider succeeds, but database store_corporate_action raises OperationalError
    splits_json = json.dumps([
        {"symbol": "AAPL", "date": "2020-08-31", "numerator": 4, "denominator": 1}
    ]).encode("utf-8")
    empty_divs = json.dumps([]).encode("utf-8")

    with patch("data.providers.fmp_corporate_actions.urlopen") as mock_urlopen:
        m1 = MagicMock()
        m1.status = 200
        m1.read.return_value = splits_json
        m2 = MagicMock()
        m2.status = 200
        m2.read.return_value = empty_divs
        mock_urlopen.return_value.__enter__.side_effect = [m1, m2]

        with patch("data.ingestion_pipeline.store_corporate_action", side_effect=sqlite3.OperationalError("disk error")):
            report2 = service.acquire_corporate_actions(db_url, symbols=["AAPL"])
            assert report2.provider_request_failures == 0
            assert report2.records_failed == 1


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


def test_corporate_actions_cli_empty_symbols_rejected() -> None:
    """Empty symbol list is rejected."""
    args = parse_ca_args(["--symbols", "  "])
    env = load_environment({"SEC_USER_AGENT": "test/1.0", "FMP_API_KEY": "key"})

    with patch("scripts.acquire_corporate_actions.load_environment", return_value=env):
        with pytest.raises(ValueError, match="non-empty --symbols argument is required"):
            run_corporate_actions_acquisition(args)
