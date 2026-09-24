from __future__ import annotations

from data.market_data_client import MarketDataClient
from data.corporate_actions_client import CorporateActionsClient
from ingestion.sec_client import SECClient


def test_market_data_client_can_be_created() -> None:
    client = MarketDataClient()

    assert client is not None


def test_corporate_actions_client_can_be_created() -> None:
    client = CorporateActionsClient()

    assert client is not None


def test_sec_client_can_be_created() -> None:
    client = SECClient(
        user_agent="InsiderTradeBotTest/test@example.com"
    )

    assert client is not None
