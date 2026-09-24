from __future__ import annotations

from data.market_data_client import MarketDataClient
from data.market_data_loader import MarketDataLoader


def test_market_data_loader_can_be_created() -> None:
    loader = MarketDataLoader()

    assert loader is not None


def test_market_data_client_accepts_configuration() -> None:
    client = MarketDataClient(
        api_key="test-key",
        base_url="https://example.test",
    )

    assert client is not None


def test_market_data_loader_accepts_client() -> None:
    client = MarketDataClient(
        api_key="test-key",
        base_url="https://example.test",
    )

    loader = MarketDataLoader(client=client)

    assert loader is not None
