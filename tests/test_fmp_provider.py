"""
Comprehensive unit tests for FMP Market Data Provider, Factory, Ticker Universe,
Acquisition CLI Workflow, and Corporate Actions Provider.

All network requests are mocked. No real external API requests.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from config.environment import EnvironmentConfigurationError, load_environment
from data.corporate_actions_client import (
    CorporateActionsRequestError,
    CorporateActionsResponseError,
)
from data.market_data_client import (
    MarketDataRequestError,
    MarketDataResponseError,
)
from data.market_data_provider_factory import get_market_data_provider
from data.providers.fmp_corporate_actions import FMPCorporateActionsProvider
from data.providers.fmp_market_data import FMPMarketDataProvider
from database.connection import connect, initialize_database
from research.ticker_universe import get_ticker_universe
from scripts.acquire_market_data import parse_args, run_acquisition


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


def test_fmp_provider_url_construction_and_params() -> None:
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
        assert "/historical-price-eod/full" in req.full_url


def test_fmp_provider_successful_response_normalization() -> None:
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
        assert records[0]["adjusted_close"] is None  # Must NOT invent adjusted_close from close!


def test_fmp_provider_no_adjusted_close_substitution() -> None:
    provider = FMPMarketDataProvider(api_key="dummy_key")
    # Response has close=100.0 but NO adjClose field
    raw_json = json.dumps([
        {"symbol": "AAPL", "date": "2024-01-02", "open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "volume": 1000}
    ]).encode("utf-8")

    with patch("data.providers.fmp_market_data.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = raw_json
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        records = provider.get_historical_prices(symbol="AAPL")
        assert records[0]["adjusted_close"] is None


def test_fmp_provider_explicit_adjusted_close_preserved() -> None:
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
            url=f"https://financialmodelingprep.com/stable/historical-price-eod/full?symbol=AAPL&apikey={secret_key}",
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
    assert res.source_transaction_count == 5


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
# 5. CORPORATE ACTIONS PROVIDER TESTS
# ==============================================================================

def test_fmp_corporate_actions_splits_and_dividends() -> None:
    ca_provider = FMPCorporateActionsProvider(api_key="ca_key")

    splits_json = json.dumps({
        "historical": [
            {"date": "2020-08-31", "numerator": 4, "denominator": 1}
        ]
    }).encode("utf-8")

    divs_json = json.dumps({
        "historical": [
            {"date": "2023-11-10", "dividend": 0.24}
        ]
    }).encode("utf-8")

    with patch("data.providers.fmp_corporate_actions.urlopen") as mock_urlopen:
        mock_resp_splits = MagicMock()
        mock_resp_splits.status = 200
        mock_resp_splits.read.return_value = splits_json

        mock_resp_divs = MagicMock()
        mock_resp_divs.status = 200
        mock_resp_divs.read.return_value = divs_json

        mock_urlopen.return_value.__enter__.side_effect = [mock_resp_splits, mock_resp_divs]

        splits = ca_provider.get_splits(symbol="AAPL")
        assert len(splits) == 1
        assert splits[0]["action_type"] == "split"
        assert splits[0]["ratio"] == "4:1"

        divs = ca_provider.get_dividends(symbol="AAPL")
        assert len(divs) == 1
        assert divs[0]["action_type"] == "dividend"
        assert divs[0]["cash_amount"] == 0.24


def test_fmp_corporate_actions_malformed_response() -> None:
    ca_provider = FMPCorporateActionsProvider(api_key="ca_key")

    with patch("data.providers.fmp_corporate_actions.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"Error Message": "Invalid key"}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        with pytest.raises(CorporateActionsResponseError, match="Invalid key"):
            ca_provider.get_splits(symbol="AAPL")
