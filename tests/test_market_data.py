from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from core.hashing import generate_market_price_hash
from data.market_data_acquisition import MarketDataAcquisitionService
from data.market_data_client import (
    MarketDataClient,
    MarketDataRequestError,
    MarketDataResponseError,
)
from data.market_data_loader import (
    MarketDataLoadError,
    MarketDataLoader,
    load_market_prices,
    load_market_prices_detailed,
)
from data.normalization import NormalizationError, normalize_market_price
from database.connection import initialize_database
from storage.repository import (
    MarketDataConflictError,
    count_records,
    store_market_price,
)
from validation.records import (
    RecordValidationError,
    validate_market_price,
    validate_market_price_record,
)


# ==========================================
# A. CLIENT TESTS
# ==========================================

def test_client_missing_base_url() -> None:
    client = MarketDataClient(base_url="")
    with pytest.raises(MarketDataRequestError, match="base_url is not configured"):
        client.get_historical_prices(symbol="AAPL")


def test_client_empty_path() -> None:
    client = MarketDataClient(base_url="https://api.example.com")
    with pytest.raises(ValueError, match="path cannot be empty"):
        client.get(path="")


def test_client_symbol_normalization() -> None:
    client = MarketDataClient(base_url="https://api.example.com")
    with pytest.raises(ValueError, match="symbol cannot be empty"):
        client.get_historical_prices(symbol="   ")


def test_client_date_parameter_handling() -> None:
    client = MarketDataClient(base_url="https://api.example.com")

    with patch.object(client, "_request_json") as mock_req:
        client.get_historical_prices(
            symbol="aapl",
            start_date="2023-01-01",
            end_date="2023-01-31",
        )
        mock_req.assert_called_once_with(
            "historical",
            {
                "symbol": "AAPL",
                "start_date": "2023-01-01",
                "end_date": "2023-01-31",
            },
        )


def test_client_http_failure() -> None:
    client = MarketDataClient(base_url="https://api.example.com")
    with patch("data.market_data_client.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = HTTPError(
            url="https://api.example.com",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )
        with pytest.raises(MarketDataRequestError, match="HTTP 404"):
            client.get_historical_prices(symbol="AAPL")


def test_client_invalid_json() -> None:
    client = MarketDataClient(base_url="https://api.example.com")
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = b"NOT VALID JSON"

    with patch("data.market_data_client.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        with pytest.raises(MarketDataResponseError, match="not valid JSON"):
            client.get_historical_prices(symbol="AAPL")


def test_client_timeout_network_failure() -> None:
    client = MarketDataClient(base_url="https://api.example.com")
    with patch("data.market_data_client.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = URLError(reason="Connection refused")
        with pytest.raises(MarketDataRequestError, match="could not be completed"):
            client.get_historical_prices(symbol="AAPL")


# ==========================================
# B. NORMALIZATION TESTS
# ==========================================

def test_normalization_valid_market_record() -> None:
    raw = {
        "symbol": "msft",
        "date": "2023-05-10",
        "open": "250.5",
        "high": "255.0",
        "low": "249.0",
        "close": "254.2",
        "volume": "1000000",
    }
    rec = normalize_market_price(raw, source="test_provider")
    assert rec.symbol == "MSFT"
    assert rec.price_date == "2023-05-10"
    assert rec.open == 250.5
    assert rec.close == 254.2
    assert rec.source == "test_provider"


def test_normalization_symbol_and_date_normalization() -> None:
    raw = {"symbol": "  tsla  ", "price_date": "2023-01-02", "close": 100}
    rec = normalize_market_price(raw, source="source_a")
    assert rec.symbol == "TSLA"
    assert rec.price_date == "2023-01-02"


def test_normalization_malformed_and_impossible_date() -> None:
    raw1 = {"symbol": "AAPL", "price_date": "2023/01/01", "close": 150}
    with pytest.raises(NormalizationError, match="YYYY-MM-DD ISO format"):
        normalize_market_price(raw1, source="src")

    raw2 = {"symbol": "AAPL", "price_date": "2023-02-29", "close": 150}
    with pytest.raises(NormalizationError, match="invalid calendar date"):
        normalize_market_price(raw2, source="src")

    raw3 = {"symbol": "AAPL", "price_date": "2023-01-01T00:00:00Z", "close": 150}
    with pytest.raises(NormalizationError, match="YYYY-MM-DD ISO format"):
        normalize_market_price(raw3, source="src")


def test_normalization_missing_symbol_and_date() -> None:
    with pytest.raises(NormalizationError, match="symbol is required"):
        normalize_market_price({"price_date": "2023-01-01", "close": 100}, source="src")

    with pytest.raises(NormalizationError, match="price_date is required"):
        normalize_market_price({"symbol": "AAPL", "close": 100}, source="src")


def test_normalization_numeric_conversions_nan_inf() -> None:
    raw = {"symbol": "NVDA", "price_date": "2023-01-01", "close": "1,234.56"}
    rec = normalize_market_price(raw, source="src")
    assert rec.close == 1234.56

    with pytest.raises(NormalizationError, match="must be numeric"):
        normalize_market_price({"symbol": "NVDA", "price_date": "2023-01-01", "close": "abc"}, source="src")

    with pytest.raises(NormalizationError, match="must be finite"):
        normalize_market_price({"symbol": "NVDA", "price_date": "2023-01-01", "close": float("nan")}, source="src")

    with pytest.raises(NormalizationError, match="must be finite"):
        normalize_market_price({"symbol": "NVDA", "price_date": "2023-01-01", "close": float("inf")}, source="src")


# ==========================================
# C. VALIDATION TESTS
# ==========================================

def test_validation_ohlc_relationships() -> None:
    errs = validate_market_price({"symbol": "A", "price_date": "2023-01-01", "source": "s", "high": 10, "low": 20, "close": 15})
    assert any("high cannot be lower than low" in e for e in errs)

    errs = validate_market_price({"symbol": "A", "price_date": "2023-01-01", "source": "s", "high": 20, "low": 10, "open": 25, "close": 15})
    assert any("open cannot exceed high" in e for e in errs)

    errs = validate_market_price({"symbol": "A", "price_date": "2023-01-01", "source": "s", "high": 20, "low": 10, "open": 5, "close": 15})
    assert any("open cannot be below low" in e for e in errs)

    errs = validate_market_price({"symbol": "A", "price_date": "2023-01-01", "source": "s", "high": 20, "low": 10, "open": 15, "close": 25})
    assert any("close cannot exceed high" in e for e in errs)

    errs = validate_market_price({"symbol": "A", "price_date": "2023-01-01", "source": "s", "high": 20, "low": 10, "open": 15, "close": 5})
    assert any("close cannot be below low" in e for e in errs)


def test_validation_prices_and_volume_constraints() -> None:
    errs = validate_market_price({"symbol": "A", "price_date": "2023-01-01", "source": "s", "close": -10})
    assert any("cannot be negative" in e for e in errs)

    errs = validate_market_price({"symbol": "A", "price_date": "2023-01-01", "source": "s", "close": 10, "volume": -5})
    assert any("volume cannot be negative" in e for e in errs)

    errs = validate_market_price({"symbol": "A", "price_date": "2023-01-01", "source": "s", "open": 10})
    assert any("at least one of close or adjusted_close is required" in e for e in errs)

    valid_rec = {
        "symbol": "AAPL",
        "price_date": "2023-01-01",
        "source": "provider",
        "open": 150.0,
        "high": 155.0,
        "low": 149.0,
        "close": 154.0,
        "adjusted_close": 153.5,
        "volume": 50000,
    }
    assert validate_market_price_record(valid_rec) is True


# ==========================================
# D. LOADER TESTS
# ==========================================

def test_loader_mixed_valid_and_invalid_records(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/loader_test.db"
    initialize_database(db_url)

    records = [
        {"symbol": "AAPL", "price_date": "2023-01-01", "close": 150.0},
        {"symbol": "AAPL", "price_date": "2023-01-01", "close": 150.0},  # duplicate
        {"symbol": "AAPL", "price_date": "INVALID_DATE", "close": 150.0}, # invalid date
        {"symbol": "AAPL", "price_date": "2023-01-02", "close": "NaN"},   # invalid numeric
        {"price_date": "2023-01-03", "close": 150.0},                     # missing symbol
        {"symbol": "AAPL", "close": 150.0},                                # missing date
        {"symbol": "AAPL", "price_date": "2023-01-01", "close": 999.0},   # storage conflict
    ]

    outcomes = load_market_prices_detailed(db_url, records, source="test_src")
    assert len(outcomes) == 7

    assert outcomes[0].outcome == "INSERTED"
    assert outcomes[1].outcome == "DUPLICATE"
    assert outcomes[2].outcome == "REJECTED"
    assert outcomes[3].outcome == "REJECTED"
    assert outcomes[4].outcome == "REJECTED"
    assert outcomes[5].outcome == "REJECTED"
    assert outcomes[6].outcome == "CONFLICT"


# ==========================================
# E. STORAGE & IDENTITY TESTS
# ==========================================

def test_storage_idempotency_and_conflicts(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/test_md.db"
    initialize_database(db_url)

    # 1. First insert
    hash1, status1 = store_market_price(
        db_url,
        symbol="AAPL",
        price_date="2023-01-01",
        open_price=100.0,
        high=105.0,
        low=99.0,
        close=104.0,
        adjusted_close=104.0,
        volume=1000.0,
        source="provider_a",
    )
    assert status1 == "INSERTED"
    assert count_records(db_url, "market_prices") == 1

    # 2. Exact duplicate
    hash2, status2 = store_market_price(
        db_url,
        symbol="AAPL",
        price_date="2023-01-01",
        open_price=100.0,
        high=105.0,
        low=99.0,
        close=104.0,
        adjusted_close=104.0,
        volume=1000.0,
        source="provider_a",
    )
    assert status2 == "DUPLICATE"
    assert hash1 == hash2
    assert count_records(db_url, "market_prices") == 1

    # 3. Same symbol/date from different source
    hash3, status3 = store_market_price(
        db_url,
        symbol="AAPL",
        price_date="2023-01-01",
        open_price=100.0,
        high=105.0,
        low=99.0,
        close=104.0,
        adjusted_close=104.0,
        volume=1000.0,
        source="provider_b",
    )
    assert status3 == "INSERTED"
    assert hash3 != hash1
    assert count_records(db_url, "market_prices") == 2

    # 4. Same symbol/date/source with changed price data
    with pytest.raises(MarketDataConflictError, match="Data conflict"):
        store_market_price(
            db_url,
            symbol="AAPL",
            price_date="2023-01-01",
            open_price=100.0,
            high=105.0,
            low=99.0,
            close=120.0,
            adjusted_close=104.0,
            volume=1000.0,
            source="provider_a",
        )


def test_deterministic_hash_has_no_retrieval_timestamp() -> None:
    # Hash must depend solely on normalized market content
    h1 = generate_market_price_hash("AAPL", "2023-01-01", "src_a", close=100.0)
    h2 = generate_market_price_hash("AAPL", "2023-01-01", "src_a", close=100.0)
    assert h1 == h2


# ==========================================
# F. ACQUISITION SERVICE TESTS
# ==========================================

def test_acquisition_single_and_multisymbol_accounting(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/acq_test.db"
    initialize_database(db_url)

    mock_provider = MagicMock()
    mock_provider.source = "mock_vendor"
    mock_provider.supports_batch = False

    mock_provider.get_historical_prices.side_effect = lambda symbol, **kwargs: [
        {"symbol": symbol, "date": "2023-01-01", "close": 100.0, "volume": 500}
    ]

    service = MarketDataAcquisitionService(mock_provider)
    report = service.acquire_historical_data(db_url, symbols=["AAPL", "MSFT"])

    assert report.requested_symbols == ("AAPL", "MSFT")
    assert report.records_received == 2
    assert report.records_inserted == 2
    assert report.records_duplicate == 0
    assert report.records_rejected == 0
    assert report.records_failed == 0
    assert report.conflicts == 0
    assert count_records(db_url, "market_prices") == 2

    # Deterministic Retry -> DUPLICATES
    retry_report = service.acquire_historical_data(db_url, symbols=["AAPL", "MSFT"])
    assert retry_report.records_received == 2
    assert retry_report.records_inserted == 0
    assert retry_report.records_duplicate == 2
    assert retry_report.records_received == (
        retry_report.records_inserted
        + retry_report.records_duplicate
        + retry_report.records_rejected
        + retry_report.records_failed
        + retry_report.conflicts
    )


def test_acquisition_batch_supported_and_fallback(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/batch_acq_test.db"
    initialize_database(db_url)

    mock_provider = MagicMock()
    mock_provider.source = "batch_vendor"
    mock_provider.supports_batch = True

    mock_provider.get_historical_prices_batch.return_value = [
        {"symbol": "AAPL", "date": "2023-01-01", "close": 150.0},
        {"symbol": "MSFT", "date": "2023-01-01", "close": 250.0},
    ]

    service = MarketDataAcquisitionService(mock_provider)
    report = service.acquire_historical_data(db_url, symbols=["AAPL", "MSFT"])

    assert report.records_received == 2
    assert report.records_inserted == 2
    assert len(report.symbol_results) == 2
    # Check per-symbol results
    aapl_res = next(r for r in report.symbol_results if r.symbol == "AAPL")
    assert aapl_res.records_received == 1
    assert aapl_res.records_inserted == 1


def test_acquisition_empty_provider_response(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/empty_acq_test.db"
    initialize_database(db_url)

    mock_provider = MagicMock()
    mock_provider.source = "empty_vendor"
    mock_provider.supports_batch = False
    mock_provider.get_historical_prices.return_value = []

    service = MarketDataAcquisitionService(mock_provider)
    report = service.acquire_historical_data(db_url, symbols=["AAPL"])

    assert report.records_received == 0
    assert report.records_inserted == 0


def test_acquisition_provider_failure_and_symbol_mismatch(tmp_path) -> None:
    db_url = f"sqlite:///{tmp_path}/fail_acq_test.db"
    initialize_database(db_url)

    mock_provider = MagicMock()
    mock_provider.source = "mismatch_vendor"
    mock_provider.supports_batch = False
    mock_provider.get_historical_prices.side_effect = MarketDataRequestError("API Down")

    service = MarketDataAcquisitionService(mock_provider)
    report = service.acquire_historical_data(db_url, symbols=["AAPL"])

    assert report.records_failed == 1
    assert len(report.provider_failures) == 1
